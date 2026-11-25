"""
Accounts (SITE_NETWORK_PLAN.md §3): organizations, users, roles, sessions, audit log.

  passwords   argon2id (argon2-cffi defaults); never stored or logged in clear
  sessions    random 256-bit token in an httpOnly cookie; only its SHA-256 is stored;
              each session has its own CSRF token for state-changing requests
  throttling  10 failed logins per email in 15 minutes -> 429 (counted from the audit log)
"""

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.db import connect

ROLES = ("admin", "operator", "viewer")
SESSION_TTL = timedelta(hours=12)
MAX_FAILED_LOGINS = 10
FAILED_LOGIN_WINDOW = timedelta(minutes=15)
MIN_PASSWORD_LENGTH = 10

_hasher = PasswordHasher()
# Verifying against this keeps unknown-email logins as slow as wrong-password ones
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


class AccountError(Exception):
    """A request the user can fix (shown as 4xx with this message)."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class User:
    id: int
    email: str
    name: str
    role: str
    org_id: Optional[int]
    org_name: Optional[str]
    active: bool

    def public(self) -> dict:
        return {"id": self.id, "email": self.email, "name": self.name, "role": self.role,
                "organization": {"id": self.org_id, "name": self.org_name} if self.org_id else None,
                "active": self.active}


@dataclass(frozen=True)
class Session:
    user: User
    csrf_token: str
    expires_at: datetime


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _user(row: dict) -> User:
    return User(id=row["id"], email=row["email"], name=row["name"], role=row["role"],
                org_id=row["org_id"], org_name=row.get("org_name"), active=row["active"])


_USER_SELECT = (
    "SELECT u.id, u.email, u.name, u.role, u.org_id, u.active, u.password_hash, o.name AS org_name "
    "FROM users u LEFT JOIN organizations o ON o.id = u.org_id "
)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def normalize_email(email: str) -> str:
    email = (email or "").strip().lower()
    local, _, domain = email.partition("@")
    if not local or "." not in domain or len(email) > 254 or any(c.isspace() for c in email):
        raise AccountError(422, "Enter a valid email address")
    return email


def check_password(password: str) -> None:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise AccountError(422, f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > 256:
        raise AccountError(422, "Password is too long")


def check_role(role: str) -> None:
    if role not in ROLES:
        raise AccountError(422, f"role must be one of {list(ROLES)}")


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def audit(conn, action: str, *, actor_type: str = "system", actor_id: Any = None, target: Any = None,
          details: Optional[dict] = None, ip: Optional[str] = None) -> None:
    conn.execute(
        "INSERT INTO audit_log (actor_type, actor_id, action, target, details, ip) VALUES (%s, %s, %s, %s, %s, %s)",
        (actor_type, None if actor_id is None else str(actor_id), action,
         None if target is None else str(target), json.dumps(details or {}), ip),
    )


def record(action: str, user: Optional["User"] = None, target: Any = None, details: Optional[dict] = None,
           ip: Optional[str] = None) -> None:
    """Audit an action done elsewhere (runs, models); never fails the request it describes."""
    try:
        with connect() as conn:
            audit(conn, action, actor_type="user" if user else "system", actor_id=user.id if user else None,
                  target=target, details=details, ip=ip)
    except Exception:  # noqa: BLE001 - the action already happened; losing one audit line is logged below
        import logging
        logging.getLogger(__name__).exception("audit record failed: %s %s", action, target)


def list_audit(limit: int = 200, action: Optional[str] = None, target: Optional[str] = None,
               actor: Optional[str] = None, before: Optional[int] = None) -> dict:
    """Newest first. action: prefix ("site." for every site event); before: id cursor for older pages."""
    limit = min(max(limit, 1), 1000)
    where, params = [], []
    if action:
        where.append("a.action LIKE %s")
        params.append(action.replace("%", "").replace("_", r"\_") + "%")
    if target:
        where.append("a.target = %s")
        params.append(target)
    if actor:
        where.append("a.actor_id = %s")
        params.append(actor)
    if before:
        where.append("a.id < %s")
        params.append(before)
    # actor_name: the user's name for people, so the log reads "Admin approved ..." not "user 3"
    sql = ("SELECT a.id, a.at, a.actor_type, a.actor_id, u.name AS actor_name, a.action, a.target, a.details, a.ip "
           "FROM audit_log a LEFT JOIN users u ON a.actor_type = 'user' AND u.id::text = a.actor_id "
           + ("WHERE " + " AND ".join(where) + " " if where else "") + "ORDER BY a.id DESC LIMIT %s")
    with connect() as conn:
        rows = conn.execute(sql, (*params, limit + 1)).fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    return {"entries": [{**r, "at": r["at"].isoformat()} for r in rows],
            "next_before": rows[-1]["id"] if more and rows else None}


# ---------------------------------------------------------------------------
# Users and organizations
# ---------------------------------------------------------------------------

def create_user(email: str, password: str, name: str, role: str, org_name: Optional[str] = None,
                *, actor: Optional[User] = None, ip: Optional[str] = None, via_cli: bool = False) -> User:
    """New user; with org_name, a new organization they belong to (names are unique)."""
    email = normalize_email(email)
    check_password(password)
    check_role(role)
    name = (name or "").strip()
    if not name or len(name) > 200:
        raise AccountError(422, "Enter your name")
    org_name = (org_name or "").strip() or None
    if role == "operator" and not org_name:
        raise AccountError(422, "Operators belong to an organization: enter its name")
    if org_name and len(org_name) > 200:
        raise AccountError(422, "Organization name is too long")

    with connect() as conn:
        if conn.execute("SELECT 1 FROM users WHERE lower(email) = %s", (email,)).fetchone():
            raise AccountError(409, "An account with this email already exists")
        org_id = None
        if org_name:
            if conn.execute("SELECT 1 FROM organizations WHERE lower(name) = lower(%s)", (org_name,)).fetchone():
                raise AccountError(409, "This organization is already registered; ask its contact to add you")
            org_id = conn.execute("INSERT INTO organizations (name) VALUES (%s) RETURNING id", (org_name,)).fetchone()["id"]
        row = conn.execute(
            "INSERT INTO users (org_id, email, name, password_hash, role) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (org_id, email, name, _hasher.hash(password), role),
        ).fetchone()
        audit(conn, "user.create", actor_type="user" if actor else "system" if via_cli else "anonymous",
              actor_id=actor.id if actor else None, target=row["id"],
              details={"email": email, "role": role, "organization": org_name, **({"via": "cli"} if via_cli else {})}, ip=ip)
        return _user(conn.execute(_USER_SELECT + "WHERE u.id = %s", (row["id"],)).fetchone())


def get_user(user_id: int) -> Optional[User]:
    with connect() as conn:
        row = conn.execute(_USER_SELECT + "WHERE u.id = %s", (user_id,)).fetchone()
    return _user(row) if row else None


def list_users() -> list[User]:
    with connect() as conn:
        rows = conn.execute(_USER_SELECT + "ORDER BY u.created_at, u.id").fetchall()
    return [_user(r) for r in rows]


def update_user(user_id: int, *, role: Optional[str] = None, active: Optional[bool] = None,
                actor: User, ip: Optional[str] = None) -> User:
    if role is not None:
        check_role(role)
    if user_id == actor.id and (role not in (None, "admin") or active is False):
        raise AccountError(422, "You can't remove your own admin role or disable yourself")
    with connect() as conn:
        row = conn.execute(_USER_SELECT + "WHERE u.id = %s FOR UPDATE OF u", (user_id,)).fetchone()
        if row is None:
            raise AccountError(404, "User not found")
        changes = {}
        if role is not None and role != row["role"]:
            if role == "operator" and row["org_id"] is None:
                raise AccountError(422, "Operators need an organization")
            changes["role"] = [row["role"], role]
            conn.execute("UPDATE users SET role = %s WHERE id = %s", (role, user_id))
        if active is not None and active != row["active"]:
            changes["active"] = [row["active"], active]
            conn.execute("UPDATE users SET active = %s WHERE id = %s", (active, user_id))
            if not active:
                conn.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
        if changes:
            audit(conn, "user.update", actor_type="user", actor_id=actor.id, target=user_id, details=changes, ip=ip)
        return _user(conn.execute(_USER_SELECT + "WHERE u.id = %s", (user_id,)).fetchone())


def set_password(user_id: int, password: str) -> None:
    check_password(password)
    with connect() as conn:
        conn.execute("UPDATE users SET password_hash = %s WHERE id = %s", (_hasher.hash(password), user_id))
        conn.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
        audit(conn, "user.password", actor_type="system", target=user_id)


# ---------------------------------------------------------------------------
# Login and sessions
# ---------------------------------------------------------------------------

def login(email: str, password: str, *, ip: Optional[str] = None, user_agent: Optional[str] = None) -> tuple[str, Session]:
    """(raw session token for the cookie, session). Same message for unknown email and wrong password."""
    try:
        email = normalize_email(email)
    except AccountError:
        raise AccountError(401, "Wrong email or password")
    # Failures are recorded (committed) before the error is raised: the throttle counts them.
    error: Optional[AccountError] = None
    with connect() as conn:
        failed = conn.execute(
            "SELECT count(*) AS n FROM audit_log WHERE action = 'login.failed' AND target = %s AND at > %s",
            (email, _now() - FAILED_LOGIN_WINDOW),
        ).fetchone()["n"]
        row = None
        if failed >= MAX_FAILED_LOGINS:
            audit(conn, "login.throttled", actor_type="anonymous", target=email, ip=ip)
            error = AccountError(429, "Too many failed attempts; try again in 15 minutes")
        else:
            row = conn.execute(_USER_SELECT + "WHERE lower(u.email) = %s", (email,)).fetchone()
            try:
                ok = _hasher.verify(row["password_hash"] if row else _DUMMY_HASH, password or "")
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                ok = False
            if not row or not ok or not row["active"]:
                audit(conn, "login.failed", actor_type="anonymous", target=email,
                      details={"reason": "inactive" if row and ok else "credentials"}, ip=ip)
                error = AccountError(401, "Wrong email or password")
        if error is None:
            result = _start_session(conn, row, password, ip, user_agent)
    if error is not None:
        raise error
    return result


def _start_session(conn, row: dict, password: str, ip: Optional[str], user_agent: Optional[str]) -> tuple[str, Session]:
    if _hasher.check_needs_rehash(row["password_hash"]):
        conn.execute("UPDATE users SET password_hash = %s WHERE id = %s", (_hasher.hash(password), row["id"]))
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    expires = _now() + SESSION_TTL
    conn.execute(
        "INSERT INTO sessions (id_hash, user_id, csrf_token, expires_at, ip, user_agent) VALUES (%s, %s, %s, %s, %s, %s)",
        (_token_hash(token), row["id"], csrf, expires, ip, (user_agent or "")[:300]),
    )
    conn.execute("UPDATE users SET last_login_at = now() WHERE id = %s", (row["id"],))
    conn.execute("DELETE FROM sessions WHERE expires_at < now()")
    audit(conn, "login.success", actor_type="user", actor_id=row["id"], target=row["email"], ip=ip)
    return token, Session(user=_user(row), csrf_token=csrf, expires_at=expires)


def session_from_token(token: Optional[str]) -> Optional[Session]:
    """The live session for a cookie value, or None (expired, unknown, or user disabled)."""
    if not token or len(token) > 200:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT s.csrf_token, s.expires_at, s.last_seen_at, u.id, u.email, u.name, u.role, u.org_id, u.active, "
            "o.name AS org_name FROM sessions s JOIN users u ON u.id = s.user_id "
            "LEFT JOIN organizations o ON o.id = u.org_id WHERE s.id_hash = %s",
            (_token_hash(token),),
        ).fetchone()
        if row is None or row["expires_at"] <= _now() or not row["active"]:
            return None
        if _now() - row["last_seen_at"] > timedelta(minutes=5):
            conn.execute("UPDATE sessions SET last_seen_at = now() WHERE id_hash = %s", (_token_hash(token),))
    return Session(user=_user(row), csrf_token=row["csrf_token"], expires_at=row["expires_at"])


def logout(token: Optional[str], user: Optional[User] = None, ip: Optional[str] = None) -> None:
    if not token:
        return
    with connect() as conn:
        conn.execute("DELETE FROM sessions WHERE id_hash = %s", (_token_hash(token),))
        if user:
            audit(conn, "logout", actor_type="user", actor_id=user.id, ip=ip)
