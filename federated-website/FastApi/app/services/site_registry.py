"""
Site registry (SITE_NETWORK_PLAN.md §4, M2).

With DATABASE_URL: sites live in Postgres (table `sites`). The lab's simulated plants are imported
from deploy/seed/sites.json at start (kind "builtin", never overwritten afterwards); operators register
real plants (kind "plant") that an admin approves.
Without DATABASE_URL (local development, route tests): read-only from sites.json, as before.

Lifecycle:  registered -> approved | rejected ; approved -> active (enrollment, M3) | revoked ;
            active <-> suspended ; active | suspended -> revoked.  Only "active" sites train and forecast.
"""

import json
import os
import re
import secrets
import unicodedata
from typing import List, Optional

from app.db import DatabaseUnavailable, connect
from app.platform_schemas import (
    EnergyType,
    Site,
    SiteDetail,
    SiteHistoryEntry,
    SiteRegistration,
)
from app.services.accounts import AccountError, User, audit
from app.settings import Settings

# admin action -> (allowed from, new status)
TRANSITIONS = {
    "approve": ({"registered"}, "approved"),
    "reject": ({"registered"}, "rejected"),
    "suspend": ({"active"}, "suspended"),
    "resume": ({"suspended"}, "active"),
    "revoke": ({"approved", "active", "suspended"}, "revoked"),
}
EDITABLE = {"registered"}

_TRANSLIT = str.maketrans({
    "а": "a", "ә": "a", "б": "b", "в": "v", "г": "g", "ғ": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "i", "к": "k", "қ": "q", "л": "l", "м": "m", "н": "n", "ң": "n", "о": "o",
    "ө": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ұ": "u", "ү": "u", "ф": "f", "х": "kh",
    "һ": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "і": "i", "ь": "", "э": "e",
    "ю": "yu", "я": "ya",
})


def _db_mode() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


def new_site_id(name: str) -> str:
    """URL-safe id from the name (Kazakh/Russian transliterated) + a random suffix, e.g. zhanatas-wind-3f9a."""
    s = unicodedata.normalize("NFKD", name.lower().translate(_TRANSLIT)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40].strip("-")
    if not s or not s[0].isalpha():
        s = f"site-{s}".strip("-")
    return f"{s}-{secrets.token_hex(2)}"


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------

_SELECT = (
    "SELECT s.*, o.name AS org_name FROM sites s LEFT JOIN organizations o ON o.id = s.org_id "
)


def _iso(v) -> Optional[str]:
    return v.isoformat() if v is not None else None


def _site(row: dict, train: Optional[tuple] = None) -> Site:
    from app.services.site_connection import can_train

    ok, note = can_train(row, train)
    return Site(id=row["id"], name=row["name"], energy_type=row["energy_type"], kind=row["kind"],
                partition_id=row["partition_id"], lat=row["lat"], lon=row["lon"], timezone=row["timezone"],
                capacity_kw=row["capacity_kw"], status=row["status"], coordinates_source=row["coordinates_source"],
                can_train=ok, train_note=note,
                # Lab sites are public; a plant only if it consented to public forecasts
                forecast_public=row["kind"] != "plant" or bool((row.get("consents") or {}).get("public_forecasts")))


def _detail(row: dict, history: Optional[List[SiteHistoryEntry]] = None, train: Optional[tuple] = None,
            **extra) -> SiteDetail:
    return SiteDetail(**_site(row, train).model_dump(), org_id=row["org_id"], org_name=row.get("org_name"),
                      equipment=row["equipment"] or {}, data_source=row["data_source"], contact=row["contact"],
                      consents=row["consents"] or {}, decision_note=row["decision_note"],
                      created_at=_iso(row["created_at"]), decided_at=_iso(row["decided_at"]), history=history or [],
                      **extra)


def _full_detail(conn, site_id: str) -> SiteDetail:
    """Detail with history, connection (incl. 7-day quality), progress and kit state."""
    from app.services import site_connection as sc

    row = conn.execute(_SELECT + "WHERE s.id = %s", (site_id,)).fetchone()
    train = sc.training_status(conn, [row]).get(site_id)
    return _detail(row, _history(conn, site_id), train,
                   connection=sc.connections(conn, [row], with_quality=True)[site_id],
                   progress=sc.progress(conn, row), kit=sc.kit_state(conn, row))


def _history(conn, site_id: str) -> List[SiteHistoryEntry]:
    rows = conn.execute(
        "SELECT a.at, a.action, a.details, u.name AS actor FROM audit_log a "
        "LEFT JOIN users u ON a.actor_type = 'user' AND u.id::text = a.actor_id "
        "WHERE a.target = %s AND a.action LIKE 'site.%%' ORDER BY a.at, a.id",
        (site_id,),
    ).fetchall()
    return [SiteHistoryEntry(at=r["at"].isoformat(), action=r["action"].removeprefix("site."), actor=r["actor"],
                             note=(r["details"] or {}).get("note")) for r in rows]


# ---------------------------------------------------------------------------
# Public reads (used by runs, forecasts and the federation)
# ---------------------------------------------------------------------------

def _from_file(settings: Settings) -> List[Site]:
    with open(settings.sites_seed, encoding="utf-8") as f:
        raw = json.load(f)
    return [Site(**s) for s in raw["sites"]]


def list_sites(settings: Settings, energy_type: Optional[EnergyType] = None,
               statuses: Optional[set] = None) -> List[Site]:
    if _db_mode():
        from app.services.site_connection import training_status

        with connect() as conn:
            rows = conn.execute(_SELECT + "ORDER BY s.partition_id NULLS LAST, s.created_at, s.id").fetchall()
            train = training_status(conn, rows)
        sites = [_site(r, train.get(r["id"])) for r in rows]
    else:
        sites = [s.model_copy(update={"can_train": s.status == "active" and s.partition_id is not None})
                 for s in _from_file(settings)]
    if energy_type is not None:
        sites = [s for s in sites if s.energy_type == energy_type]
    if statuses is not None:
        sites = [s for s in sites if s.status in statuses]
    return sites


def get_site(settings: Settings, site_id: str) -> Optional[Site]:
    return next((s for s in list_sites(settings) if s.id == site_id), None)


def active_site_ids(settings: Settings, energy_type: EnergyType) -> List[str]:
    return [s.id for s in list_sites(settings, energy_type, {"active"})]


def trainable_site_ids(settings: Settings, energy_type: EnergyType) -> List[str]:
    """Active sites with a Flower connection: the only ones a training run can use."""
    return [s.id for s in list_sites(settings, energy_type, {"active"}) if s.can_train]


def seed_from_file(settings: Settings) -> int:
    """Import the builtin sites from sites.json once; later changes in the database win."""
    inserted = 0
    with connect() as conn:
        for s in _from_file(settings):
            cur = conn.execute(
                "INSERT INTO sites (id, kind, name, energy_type, lat, lon, timezone, capacity_kw, coordinates_source,"
                " partition_id, status, consents) VALUES (%s, 'builtin', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (id) DO NOTHING",
                (s.id, s.name, s.energy_type.value, s.lat, s.lon, s.timezone, s.capacity_kw, s.coordinates_source,
                 s.partition_id, "active" if s.status == "active" else "suspended",
                 json.dumps({"train": True, "public_forecasts": True})),
            )
            if cur.rowcount:
                inserted += 1
                audit(conn, "site.import", target=s.id, details={"from": "sites.json"})
    return inserted


# ---------------------------------------------------------------------------
# Operators and admins
# ---------------------------------------------------------------------------

def _require_db() -> None:
    if not _db_mode():
        raise DatabaseUnavailable("Site registration needs the database: DATABASE_URL is not set")


def register_site(user: User, req: SiteRegistration, ip: Optional[str] = None) -> SiteDetail:
    _require_db()
    if user.role != "operator" or user.org_id is None:
        raise AccountError(403, "Only plant operators register sites (for their own organization)")
    with connect() as conn:
        if conn.execute("SELECT 1 FROM sites WHERE org_id = %s AND lower(name) = lower(%s)",
                        (user.org_id, req.name)).fetchone():
            raise AccountError(409, f"Your organization already has a site named '{req.name}'")
        site_id = new_site_id(req.name)
        conn.execute(
            "INSERT INTO sites (id, kind, org_id, name, energy_type, lat, lon, timezone, capacity_kw, equipment,"
            " data_source, contact, consents, coordinates_source, status, created_by)"
            " VALUES (%s, 'plant', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'operator', 'registered', %s)",
            (site_id, user.org_id, req.name, req.energy_type.value, req.lat, req.lon, req.timezone, req.capacity_kw,
             json.dumps(req.equipment), req.data_source, req.contact, json.dumps(req.consents.model_dump()), user.id),
        )
        audit(conn, "site.register", actor_type="user", actor_id=user.id, target=site_id,
              details={"name": req.name, "energy_type": req.energy_type.value, "org_id": user.org_id}, ip=ip)
        return _full_detail(conn, site_id)


def _visible(user: User, row: Optional[dict]) -> bool:
    return row is not None and (user.role == "admin" or (row["org_id"] is not None and row["org_id"] == user.org_id))


def list_my_sites(user: User) -> List[SiteDetail]:
    """Admins: every site. Operators: their organization's sites. Viewers: none."""
    from app.services import site_connection as sc

    _require_db()
    with connect() as conn:
        if user.role == "admin":
            rows = conn.execute(_SELECT + "ORDER BY s.kind DESC, s.created_at DESC, s.id").fetchall()
        elif user.org_id is not None:
            rows = conn.execute(_SELECT + "WHERE s.org_id = %s ORDER BY s.created_at DESC", (user.org_id,)).fetchall()
        else:
            rows = []
        conns = sc.connections(conn, rows)
        train = sc.training_status(conn, rows)
    return [_detail(r, train=train.get(r["id"]), connection=conns[r["id"]]) for r in rows]


def get_site_detail(user: User, site_id: str) -> SiteDetail:
    _require_db()
    with connect() as conn:
        row = conn.execute(_SELECT + "WHERE s.id = %s", (site_id,)).fetchone()
        if not _visible(user, row):
            raise AccountError(404, "Site not found")  # same answer for "not yours" and "doesn't exist"
        return _full_detail(conn, site_id)


def update_registration(user: User, site_id: str, req: SiteRegistration, ip: Optional[str] = None) -> SiteDetail:
    _require_db()
    with connect() as conn:
        row = conn.execute(_SELECT + "WHERE s.id = %s FOR UPDATE OF s", (site_id,)).fetchone()
        if not _visible(user, row) or row["kind"] != "plant":
            raise AccountError(404, "Site not found")
        if row["status"] not in EDITABLE:
            raise AccountError(409, f"The site is {row['status']}; details can only change while it waits for approval")
        if req.energy_type.value != row["energy_type"]:
            raise AccountError(422, "The energy type can't change; register a new site instead")
        conn.execute(
            "UPDATE sites SET name = %s, lat = %s, lon = %s, timezone = %s, capacity_kw = %s, equipment = %s,"
            " data_source = %s, contact = %s, consents = %s, updated_at = now() WHERE id = %s",
            (req.name, req.lat, req.lon, req.timezone, req.capacity_kw, json.dumps(req.equipment), req.data_source,
             req.contact, json.dumps(req.consents.model_dump()), site_id),
        )
        audit(conn, "site.edit", actor_type="user", actor_id=user.id, target=site_id, ip=ip)
        return _full_detail(conn, site_id)


def decide(admin: User, site_id: str, action: str, note: Optional[str], ip: Optional[str] = None) -> SiteDetail:
    """Admin decision on a site: approve, reject, suspend, resume, revoke."""
    _require_db()
    if action not in TRANSITIONS:
        raise AccountError(404, f"Unknown action '{action}'")
    note = (note or "").strip() or None
    if action in ("reject", "revoke", "suspend") and not note:
        raise AccountError(422, f"Say why ({action} needs a note; the operator sees it)")
    allowed_from, new_status = TRANSITIONS[action]
    with connect() as conn:
        row = conn.execute(_SELECT + "WHERE s.id = %s FOR UPDATE OF s", (site_id,)).fetchone()
        if row is None:
            raise AccountError(404, "Site not found")
        if row["status"] not in allowed_from:
            raise AccountError(409, f"Can't {action} a site that is {row['status']}")
        conn.execute(
            "UPDATE sites SET status = %s, decision_note = %s, decided_by = %s, decided_at = now(), updated_at = now()"
            " WHERE id = %s",
            (new_status, note, admin.id, site_id),
        )
        revoked = 0
        if action == "revoke":
            from app.services.site_connection import revoke_credentials

            revoked = revoke_credentials(conn, site_id)  # the site agent's key stops working at once
        audit(conn, f"site.{action}", actor_type="user", actor_id=admin.id, target=site_id,
              details={"from": row["status"], "to": new_status, **({"note": note} if note else {}),
                       **({"credentials_revoked": revoked} if revoked else {})}, ip=ip)
        detail = _full_detail(conn, site_id)
    if revoked:
        from app.services.site_connection import apply_revocations

        apply_revocations()  # CRL + Flower unregister, after the commit
    return detail
