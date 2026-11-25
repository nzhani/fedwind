"""
Telegram alerts.

People connect Telegram from their account menu: a one-time code in a t.me link; when they press
Start, the bot learns their chat id. Then:

  operators  their plant approved / rejected / suspended / resumed / revoked / kit re-issued,
             online for the first time, offline (no heartbeat for 3 × HEARTBEAT_S) and back online
  admins     a new plant waiting for approval, a plant going offline
             (plus SUPPORT_CHAT_ID, the team chat the feedback board already uses)

Plant events come from the audit log, which every decision already writes in its own transaction,
so nothing in the decision paths changes. A background loop (start_background) turns new audit
entries and connection changes into queued messages (table notifications) and sends them with
retries. Without BOT_TOKEN nothing is queued or sent; the rest of the platform works the same.
Messages carry plant names, states, reasons and links only: never measurements.

Updates from Telegram (/start <code>, /stop) arrive by polling getUpdates (laptops have no public
address) or, when a webhook is configured, through the feedback webhook.
"""

import hashlib
import logging
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional

import requests

from app.db import DatabaseUnavailable, connect

log = logging.getLogger("fedwind.notifications")

LINK_TTL = timedelta(minutes=15)
MAX_ATTEMPTS = 5


class TelegramError(Exception):
    pass


class Telegram:
    """The few Bot API calls we use. Tests replace `client()` with a fake."""

    def __init__(self, token: str, session: Optional[requests.Session] = None):
        self.token, self.http = token, session or requests.Session()
        self._me: Optional[dict] = None

    def call(self, method: str, http_timeout: float = 15, **params) -> dict:
        # params go to Telegram as they are (getUpdates has its own `timeout`)
        try:
            r = self.http.post(f"https://api.telegram.org/bot{self.token}/{method}", json=params, timeout=http_timeout)
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            raise TelegramError(f"{method}: {type(e).__name__}") from None
        if not data.get("ok"):
            raise TelegramError(f"{method}: {data.get('error_code')} {data.get('description', '')}".strip())
        return data["result"]

    def username(self) -> str:
        if self._me is None:
            self._me = self.call("getMe")
        return self._me["username"]

    def send(self, chat_id: str, text: str) -> None:
        self.call("sendMessage", chat_id=chat_id, text=text, disable_web_page_preview=True)


_client: Optional[Telegram] = None


def client() -> Optional[Telegram]:
    """The bot, or None when BOT_TOKEN isn't set (alerts are then simply off)."""
    global _client
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        return None
    if _client is None or _client.token != token:
        _client = Telegram(token)
    return _client


def web_url(path: str = "") -> str:
    return os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/") + path


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# -- linking ----------------------------------------------------------------------------------------

def status(user_id: int) -> dict:
    bot = client()
    with connect() as conn:
        row = conn.execute("SELECT tg_username, linked_at FROM telegram_links WHERE user_id = %s", (user_id,)).fetchone()
    out = {"configured": bot is not None, "linked": row is not None,
           "telegram_username": row["tg_username"] if row else None,
           "linked_at": row["linked_at"].isoformat() if row else None, "bot_username": None}
    if bot:
        try:
            out["bot_username"] = bot.username()
        except TelegramError:
            pass
    return out


def start_link(user_id: int) -> dict:
    """A t.me link with a one-time code; pressing Start in Telegram connects the account."""
    bot = client()
    if bot is None:
        raise LookupError("Telegram isn't configured on this server (BOT_TOKEN)")
    username = bot.username()
    code = secrets.token_urlsafe(18)
    expires = _now() + LINK_TTL
    with connect() as conn:
        conn.execute("DELETE FROM telegram_link_codes WHERE user_id = %s AND used_at IS NULL", (user_id,))
        conn.execute("INSERT INTO telegram_link_codes (code_hash, user_id, expires_at) VALUES (%s, %s, %s)",
                     (_hash(code), user_id, expires))
    return {"url": f"https://t.me/{username}?start={code}", "expires_at": expires.isoformat()}


def unlink(user_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM telegram_links WHERE user_id = %s", (user_id,))


def handle_update(update: dict) -> bool:
    """/start <code> connects, /stop disconnects. True when the update was ours."""
    msg = update.get("message") or {}
    text = (msg.get("text") or "").strip()
    chat = msg.get("chat") or {}
    if not text.startswith(("/start", "/stop")) or chat.get("type", "private") != "private":
        return False
    chat_id = str(chat.get("id"))
    username = (msg.get("from") or {}).get("username")
    with connect() as conn:
        if text.startswith("/stop"):
            conn.execute("DELETE FROM telegram_links WHERE chat_id = %s", (chat_id,))
            _queue(conn, [chat_id], "ArqauQuat alerts are off for this chat. Connect again from your account menu.", "link")
            return True
        parts = text.split(maxsplit=1)
        code = parts[1] if len(parts) > 1 else ""
        row = conn.execute(
            "UPDATE telegram_link_codes SET used_at = now() WHERE code_hash = %s AND used_at IS NULL AND expires_at > now()"
            " RETURNING user_id", (_hash(code),)).fetchone() if code else None
        if row is None:
            _queue(conn, [chat_id], "This link is used or expired. Open ArqauQuat → your account menu → Telegram alerts "
                                    "to get a new one.", "link")
            return True
        user = conn.execute("SELECT name, role FROM users WHERE id = %s AND active", (row["user_id"],)).fetchone()
        if user is None:
            return True
        conn.execute("INSERT INTO telegram_links (user_id, chat_id, tg_username) VALUES (%s, %s, %s)"
                     " ON CONFLICT (user_id) DO UPDATE SET chat_id = EXCLUDED.chat_id,"
                     " tg_username = EXCLUDED.tg_username, linked_at = now()", (row["user_id"], chat_id, username))
        what = ("new plants waiting for approval and plants going offline" if user["role"] == "admin"
                else "your plants: approval, kit, online and offline")
        _queue(conn, [chat_id], f"Connected, {user['name']}. ArqauQuat will tell you about {what}. Send /stop to turn it off.",
               "link")
    return True


# -- turning events into messages ---------------------------------------------------------------

def _queue(conn, chat_ids: Iterable[str], text: str, event: str) -> int:
    ids = sorted({c for c in chat_ids if c})
    for c in ids:
        conn.execute("INSERT INTO notifications (chat_id, text, event) VALUES (%s, %s, %s)", (c, text, event))
    return len(ids)


def _org_chats(conn, org_id) -> List[str]:
    if org_id is None:
        return []
    return [r["chat_id"] for r in conn.execute(
        "SELECT l.chat_id FROM telegram_links l JOIN users u ON u.id = l.user_id"
        " WHERE u.org_id = %s AND u.active AND u.role <> 'viewer'", (org_id,)).fetchall()]


def _admin_chats(conn) -> List[str]:
    chats = [r["chat_id"] for r in conn.execute(
        "SELECT l.chat_id FROM telegram_links l JOIN users u ON u.id = l.user_id"
        " WHERE u.role = 'admin' AND u.active").fetchall()]
    support = os.environ.get("SUPPORT_CHAT_ID", "").strip()
    return chats + ([support] if support else [])


def _mw(kw) -> str:
    if kw is None:
        return "?"
    return f"{kw / 1000:.0f} MW" if kw >= 10000 else f"{kw / 1000:.1f} MW"


def _event_message(conn, entry: dict):
    """(chat ids, text) for an audit entry, or None if nobody is told about it."""
    action, site_id = entry["action"], entry["target"]
    if not action.startswith("site.") or not site_id:
        return None
    site = conn.execute("SELECT s.*, o.name AS org_name FROM sites s LEFT JOIN organizations o ON o.id = s.org_id"
                        " WHERE s.id = %s", (site_id,)).fetchone()
    if site is None or site["kind"] != "plant":
        return None
    name, note = site["name"], ((entry["details"] or {}).get("note") or "").strip()
    reason = f"\nReason: “{note}”" if note else ""
    page = web_url(f"/sites/{site_id}")
    if action == "site.register":
        return _admin_chats(conn), (f"🆕 New plant waiting for approval: {name}\n{site['energy_type'].title()} · "
                                    f"{_mw(site['capacity_kw'])} · {site['org_name']}\nReview: {web_url('/admin/approvals')}")
    texts = {
        "site.approve": f"✅ {name} is approved. Download the site kit and install it at the plant:\n{page}",
        "site.reject": f"❌ {name} was not approved.{reason}\n{page}",
        "site.suspend": f"⏸ {name} is suspended by the ArqauQuat team.{reason}\n{page}",
        "site.resume": f"▶️ {name} is active again.\n{page}",
        "site.revoke": f"⛔ {name} was removed from the federation.{reason}\n{page}",
        "site.reissue": f"🔑 A new site kit can be downloaded for {name}.{reason}\n{page}",
        "site.online": f"🟢 {name} is online. Its power forecast:\n"
                       + web_url(f"/forecast?energy={site['energy_type']}&site={site_id}"),
    }
    if action not in texts:
        return None
    return _org_chats(conn, site["org_id"]), texts[action]


def process_events(conn) -> int:
    """New audit entries since the last call -> queued messages. The first call only sets the cursor."""
    row = conn.execute("SELECT value FROM notify_state WHERE key = 'audit_cursor' FOR UPDATE").fetchone()
    newest = conn.execute("SELECT coalesce(max(id), 0) AS m FROM audit_log").fetchone()["m"]
    if row is None:
        conn.execute("INSERT INTO notify_state (key, value) VALUES ('audit_cursor', %s)", (str(newest),))
        return 0
    queued = 0
    for e in conn.execute("SELECT id, action, target, details FROM audit_log WHERE id > %s AND id <= %s"
                          " AND action LIKE 'site.%%' ORDER BY id", (int(row["value"]), newest)).fetchall():
        m = _event_message(conn, e)
        if m:
            queued += _queue(conn, m[0], m[1], e["action"])
    conn.execute("UPDATE notify_state SET value = %s WHERE key = 'audit_cursor'", (str(newest),))
    return queued


def check_connections(conn) -> int:
    """Online -> offline and back: one message per change. Plants seen for the first time are only recorded."""
    from app.services.site_connection import connections

    rows = conn.execute("SELECT s.*, o.name AS org_name FROM sites s LEFT JOIN organizations o ON o.id = s.org_id"
                        " WHERE s.kind = 'plant' AND s.status = 'active'").fetchall()
    if not rows:
        return 0
    now_state = connections(conn, rows)
    known = {r["site_id"]: r["state"] for r in conn.execute(
        "SELECT site_id, state FROM site_alert_state WHERE site_id = ANY(%s)", ([r["id"] for r in rows],)).fetchall()}
    queued = 0
    for site in rows:
        state = now_state[site["id"]].state
        if state not in ("online", "offline"):
            continue
        before = known.get(site["id"])
        if before == state:
            continue
        conn.execute("INSERT INTO site_alert_state (site_id, state) VALUES (%s, %s) ON CONFLICT (site_id)"
                     " DO UPDATE SET state = EXCLUDED.state, at = now()", (site["id"], state))
        if before is None:
            continue
        page = web_url(f"/sites/{site['id']}")
        if state == "offline":
            minutes = max(1, round(3 * now_state[site["id"]].heartbeat_s / 60))
            text = (f"🔴 {site['name']} is offline: no heartbeat for over {minutes} min. Check the plant's computer "
                    f"and network.\n{page}")
            queued += _queue(conn, _org_chats(conn, site["org_id"]) + _admin_chats(conn), text, "site.offline")
        else:
            queued += _queue(conn, _org_chats(conn, site["org_id"]), f"🟢 {site['name']} is back online.\n{page}",
                             "site.back_online")
    return queued


def send_pending(bot: Telegram, limit: int = 30) -> int:
    with connect() as conn:
        rows = conn.execute("SELECT id, chat_id, text, attempts FROM notifications WHERE sent_at IS NULL"
                            " AND attempts < %s ORDER BY id LIMIT %s", (MAX_ATTEMPTS, limit)).fetchall()
    sent = 0
    for r in rows:
        try:
            bot.send(r["chat_id"], r["text"])
            err = None
            sent += 1
        except TelegramError as e:
            err = str(e)[:300]
        with connect() as conn:
            if err is None:
                conn.execute("UPDATE notifications SET sent_at = now(), attempts = attempts + 1 WHERE id = %s", (r["id"],))
            else:
                conn.execute("UPDATE notifications SET attempts = attempts + 1, last_error = %s WHERE id = %s",
                             (err, r["id"]))
    return sent


def poll_updates(bot: Telegram) -> int:
    """getUpdates (no public address needed). Telegram refuses it while a webhook is set: then the webhook handles them."""
    with connect() as conn:
        row = conn.execute("SELECT value FROM notify_state WHERE key = 'tg_offset'").fetchone()
    offset = int(row["value"]) if row else 0
    try:
        updates = bot.call("getUpdates", offset=offset, timeout=0, allowed_updates=["message"])
    except TelegramError as e:
        if " 409 " in f" {e} ":
            return 0
        raise
    handled = 0
    for u in updates:
        if handle_update(u):
            handled += 1
        offset = max(offset, u["update_id"] + 1)
    if updates:
        with connect() as conn:
            conn.execute("INSERT INTO notify_state (key, value) VALUES ('tg_offset', %s)"
                         " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (str(offset),))
    return handled


def tick(bot: Optional[Telegram]) -> None:
    """One round of the background loop."""
    if bot is None:
        return
    with connect() as conn:
        process_events(conn)
        check_connections(conn)
    poll_updates(bot)
    send_pending(bot)


def start_background(interval_s: float = 5.0) -> Optional[threading.Thread]:
    """Daemon thread running tick(); off with NOTIFY_LOOP=off (tests) or without BOT_TOKEN."""
    if os.environ.get("NOTIFY_LOOP", "on").lower() in ("off", "0", "false") or client() is None:
        return None

    def loop():
        while True:
            try:
                tick(client())
            except DatabaseUnavailable:
                pass
            except Exception as e:  # never let alerts take the API down
                log.warning("notifications: %s: %s", type(e).__name__, e)
            time.sleep(interval_s)

    t = threading.Thread(target=loop, name="fedwind-notifications", daemon=True)
    t.start()
    return t
