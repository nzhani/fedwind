"""
Admin commands for the platform database (run inside the api container).

  python -m app.cli migrate
  python -m app.cli create-admin --email you@org.kz --name "Your Name"
  python -m app.cli set-role --email someone@org.kz --role admin
  python -m app.cli set-password --email someone@org.kz
  python -m app.cli list-users
  python -m app.cli demo-reset [--yes] [--promote <run_id> ...] [--keep <site_id> ...]   local demo only
  python -m app.cli sim-plants spawn --count 20 --energy wind --out /data/sim-kits   test servers only (M9)
  python -m app.cli sim-plants status
  python -m app.cli sim-plants join --site <id>        dev mode: this plant's Flower client runs here
  python -m app.cli start-run --energy wind --rounds 3 --horizon 1 [--data-percent 5] [--min-clients 15]
  python -m app.cli run-status <run_id> [--json]
  python -m app.cli import-run /data/import/<run folder> [--run-id ID] [--promote]   runs trained elsewhere

Passwords are typed at a hidden prompt, or read from FEDWIND_NEW_PASSWORD for scripted setups;
never as a command-line argument (it would land in shell history and `ps`).
"""

import argparse
import getpass
import os
import sys

from app.db import migrate
from app.services import accounts
from app.services.accounts import AccountError


def _password() -> str:
    pw = os.environ.get("FEDWIND_NEW_PASSWORD")
    if pw:
        return pw
    pw = getpass.getpass("Password: ")
    if pw != getpass.getpass("Repeat password: "):
        sys.exit("Passwords don't match")
    return pw


def _user_by_email(email: str) -> accounts.User:
    email = accounts.normalize_email(email)
    for u in accounts.list_users():
        if u.email == email:
            return u
    sys.exit(f"No user with email {email}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    a = sub.add_parser("create-admin")
    a.add_argument("--email", required=True)
    a.add_argument("--name", required=True)
    r = sub.add_parser("set-role")
    r.add_argument("--email", required=True)
    r.add_argument("--role", required=True, choices=accounts.ROLES)
    s = sub.add_parser("set-password")
    s.add_argument("--email", required=True)
    sub.add_parser("list-users")
    d = sub.add_parser("demo-reset", help="remove demo plants, organizations and non-admin users")
    d.add_argument("--yes", action="store_true", help="really do it (without it: only show what would go)")
    d.add_argument("--promote", action="append", default=[], metavar="RUN_ID",
                   help="promote this finished run afterwards (repeatable), e.g. the demo's run A")
    d.add_argument("--keep", action="append", default=[], metavar="SITE_ID",
                   help="keep this plant with its organization and that organization's accounts (repeatable)")
    sp = sub.add_parser("sim-plants", help="simulated plants for scale tests (not on production)")
    sp.add_argument("action", choices=["spawn", "status", "join", "leave"])
    sp.add_argument("--site", help="join/leave: the plant whose Flower client runs on this computer (dev mode)")
    sp.add_argument("--count", type=int, default=20)
    sp.add_argument("--energy", choices=["wind", "solar"], default="wind")
    sp.add_argument("--out", default="/data/sim-kits")
    sp.add_argument("--no-window", action="store_true", help="plants keep their window (local forecasting)")
    sr = sub.add_parser("start-run", help="start a federated run on every site that can train")
    sr.add_argument("--energy", choices=["wind", "solar"], default="wind")
    sr.add_argument("--rounds", type=int, default=3)
    sr.add_argument("--horizon", type=int, default=1)
    sr.add_argument("--local-epochs", type=int, default=1)
    sr.add_argument("--data-percent", type=int, default=100)
    sr.add_argument("--min-clients", type=int, default=2)
    sr.add_argument("--round-timeout", type=int, default=1800)
    sr.add_argument("--sites", default="", help="comma-separated (default: every site that can train now)")
    ir = sub.add_parser("import-run", help="add a run trained elsewhere (e.g. Irgetas) to the website")
    ir.add_argument("folder", help="the run folder (result.json, checkpoints/, metrics.jsonl), inside the container")
    ir.add_argument("--run-id", default=None)
    ir.add_argument("--note", default=None)
    ir.add_argument("--promote", action="store_true", help="also make it the model that serves forecasts")
    rs = sub.add_parser("run-status", help="a run's state and per-round participation")
    rs.add_argument("run_id")
    rs.add_argument("--json", action="store_true")
    c = sub.add_parser("site-ca", help="site CA: create it, show it, re-publish the CRL")
    c.add_argument("action", choices=["init", "show", "crl"])
    args = p.parse_args(argv)

    try:
        if args.cmd == "migrate":
            print("applied:", migrate() or "nothing (up to date)")
        elif args.cmd == "create-admin":
            migrate()
            u = accounts.create_user(args.email, _password(), args.name, "admin", via_cli=True)
            print(f"admin {u.email} created (id {u.id})")
        elif args.cmd == "set-role":
            u = _user_by_email(args.email)
            with accounts.connect() as conn:
                conn.execute("UPDATE users SET role = %s WHERE id = %s", (args.role, u.id))
                accounts.audit(conn, "user.update", target=u.id, details={"role": [u.role, args.role], "via": "cli"})
            print(f"{u.email}: {u.role} -> {args.role}")
        elif args.cmd == "set-password":
            u = _user_by_email(args.email)
            accounts.set_password(u.id, _password())
            print(f"password changed for {u.email}; their sessions were closed")
        elif args.cmd == "sim-plants":
            sim_plants_command(args)
        elif args.cmd == "start-run":
            start_run_command(args)
        elif args.cmd == "import-run":
            import_run_command(args)
        elif args.cmd == "run-status":
            run_status_command(args.run_id, args.json)
        elif args.cmd == "site-ca":
            site_ca_command(args.action)
        elif args.cmd == "demo-reset":
            demo_reset(args.yes, args.promote, args.keep)
        elif args.cmd == "list-users":
            for u in accounts.list_users():
                print(f"{u.id:>4}  {u.role:<8}  {'active' if u.active else 'disabled':<8}  {u.email}  {u.org_name or ''}")
    except AccountError as e:
        sys.exit(e.message)


def sim_plants_command(args) -> None:
    from pathlib import Path

    from app.services import sim_plants

    migrate()
    if args.action in ("join", "leave"):
        if not args.site:
            sys.exit("--site is required")
        r = sim_plants.set_joined(args.site, args.action == "join")
        print(f"{r['site_id']}: {'can be selected for training runs' if r['joined'] else 'left training'}")
        return
    if args.action == "spawn":
        for p in sim_plants.spawn(args.count, args.energy, Path(args.out), share_window=not args.no_window):
            print(f"{p['site_id']}\t{p['kit']}")
    else:
        rows = sim_plants.status()
        for r in rows:
            print(f"{r['site_id']:<40} {r['energy']:<6} {r['status']:<10} {r['connection'] or '-':<8} "
                  f"hours={r['train_hours'] or 0:<6} {'CAN TRAIN' if r['can_train'] else r['why_not']}")
        print(f"{sum(r['can_train'] for r in rows)} of {len(rows)} can train")


def start_run_command(args) -> None:
    from app.platform_schemas import ExperimentConfig
    from app.services import run_launcher
    from app.services.federation_client import get_federation
    from app.settings import get_settings

    config = ExperimentConfig(energy_type=args.energy, rounds=args.rounds, horizon=args.horizon,
                              local_epochs=args.local_epochs, data_percent=args.data_percent,
                              min_train_clients=args.min_clients, round_timeout_s=args.round_timeout,
                              sites=[s for s in args.sites.split(",") if s] or None)
    try:
        run = run_launcher.launch(get_settings(), config, get_federation())
    except run_launcher.LaunchError as e:
        sys.exit(f"not started ({e.status}): {e.message}")
    with accounts.connect() as conn:
        accounts.audit(conn, "run.start", target=run.run_id, details={"via": "cli", "sites": run.config.get("sites")})
    print(run.run_id)


def import_run_command(args) -> None:
    from pathlib import Path

    from app.services import model_registry, run_import
    from app.settings import get_settings

    settings = get_settings()
    run = run_import.import_run(settings, Path(args.folder), args.run_id, args.note)
    real = ((run.result or {}).get("metrics") or {}).get("real") or {}
    print(f"imported {run.run_id}: {run.config.get('energy_type')} {run.horizon} h, {len(run.sites)} sites,"
          f" {run.current_round} rounds, skill {real.get('skill_vs_persistence')}")
    with accounts.connect() as conn:
        accounts.audit(conn, "run.import", target=run.run_id, details={"from": args.folder, "via": "cli"})
    if args.promote:
        m = model_registry.promote(settings, run, promoted_by="import (cli)")
        print(f"promoted: {m.energy_type.value} {m.horizon} h" + (f" v{m.version}" if m.version else ""))


def run_status_command(run_id: str, as_json: bool) -> None:
    import json

    from app.services import run_store
    from app.settings import get_settings

    run = run_store.get_run(get_settings(), run_id)
    if run is None:
        sys.exit(f"no run {run_id}")
    rounds = []
    for h in run.history:
        counts = {}
        for c in h.clients:
            counts[c.status] = counts.get(c.status, 0) + 1
        rounds.append({"round": h.round, "duration_s": h.duration_s, "uplink_bytes": h.uplink_bytes, **counts,
                       "rejected_sites": [c.site for c in h.clients if c.status == "rejected"],
                       "dropped_sites": [c.site for c in h.clients if c.status == "dropped"]})
    out = {"run_id": run.run_id, "status": run.status, "round": run.current_round, "total_rounds": run.total_rounds,
           "sites": len(run.sites), "rounds": rounds}
    if as_json:
        print(json.dumps(out, indent=2))
        return
    print(f"{run.run_id}: {run.status}, round {run.current_round}/{run.total_rounds}, {len(run.sites)} sites")
    for r in rounds:
        print(f"  round {r['round']}: replied {r.get('replied', 0)}, dropped {r.get('dropped', 0)}"
              f" {r['dropped_sites'] or ''}, rejected {r.get('rejected', 0)} {r['rejected_sites'] or ''}")


def site_ca_command(action: str) -> None:
    """init: create the CA if missing. show: where it is, its validity, the CRL. crl: re-publish the
    CRL and retry pending Flower unregistrations (the API also does this every hour)."""
    from app.services import site_ca

    if action == "init":
        created = site_ca.init_ca()
        print(f"site CA {'created' if created else 'already exists'} in {site_ca.ca_dir()}")
        print("Back up ca.key offline: losing it means every plant has to enroll again.")
    elif action == "crl":
        migrate()
        from app.services.site_connection import apply_revocations

        print(apply_revocations())
    if action in ("init", "show"):
        if not site_ca.exists():
            sys.exit(f"no site CA in {site_ca.ca_dir()} (create it: python -m app.cli site-ca init)")
        from cryptography import x509

        cert = x509.load_pem_x509_certificate(site_ca.ca_cert_pem().encode())
        print(f"CA:  {cert.subject.rfc4514_string()}  valid until {cert.not_valid_after_utc:%Y-%m-%d}")
        crl = site_ca.read_crl()
        if crl is not None:
            print(f"CRL: {len(list(crl))} revoked, next update {crl.next_update_utc:%Y-%m-%d %H:%M} UTC")


def demo_reset(really: bool, promote: list, keep: list = ()) -> None:
    """
    Back to the start of the demo (DEMO_DAY_PLAN.md §2 F): every registered plant (kind 'plant')
    with its kit tokens, credentials, heartbeats, quality and forecast windows; every non-admin
    user with their sessions; organizations nobody is left in. Kept: admins, the lab sites, all
    training runs, the audit log (append-only; the reset itself is logged as demo.reset), and any
    plant named with --keep together with its organization and that organization's accounts.
    Refused when ENV=production.
    """
    if os.environ.get("ENV", "").lower() == "production":
        sys.exit("demo-reset is for the local demo database only (ENV=production)")
    keep = list(keep)
    with accounts.connect() as conn:
        found = conn.execute("SELECT id, org_id FROM sites WHERE kind = 'plant' AND id = ANY(%s)", (keep,)).fetchall()
        missing = sorted(set(keep) - {r["id"] for r in found})
        if missing:
            sys.exit(f"No such plant to keep: {', '.join(missing)}")
        kept_orgs = sorted({r["org_id"] for r in found})
        plants = [r["id"] for r in conn.execute(
            "SELECT id FROM sites WHERE kind = 'plant' AND NOT id = ANY(%s) ORDER BY id", (keep,)).fetchall()]
        users = [r["email"] for r in conn.execute(
            "SELECT email FROM users WHERE role <> 'admin' AND (org_id IS NULL OR NOT org_id = ANY(%s)) ORDER BY id",
            (kept_orgs,)).fetchall()]
        orgs = [r["name"] for r in conn.execute(
            "SELECT name FROM organizations o WHERE NOT id = ANY(%s) AND NOT EXISTS "
            "(SELECT 1 FROM users u WHERE u.org_id = o.id AND u.role = 'admin') ORDER BY id", (kept_orgs,)).fetchall()]
        admins = conn.execute("SELECT count(*) AS n FROM users WHERE role = 'admin'").fetchone()["n"]
        print(f"plants:        {len(plants)}  {', '.join(plants)}")
        print(f"users:         {len(users)}  {', '.join(users)}")
        print(f"organizations: {len(orgs)}  {', '.join(orgs)}")
        print(f"kept:          {admins} admin(s), lab sites, runs, audit log"
              + (f"; plants {', '.join(keep)} with their organization" if keep else ""))
        if not really:
            print("Nothing changed (dry run). Add --yes to remove the above.")
            return
        if not admins:
            sys.exit("No admin account: create one first (create-admin), or nobody could log in afterwards")
        # Revoke first: certificates stay in the CRL and Flower nodes get unregistered after the
        # sites are gone (site_revocations has no foreign key). Cascades remove the rest (migration 003).
        from app.services.site_connection import revoke_credentials

        for site_id in plants:
            revoke_credentials(conn, site_id)
        conn.execute("DELETE FROM sites WHERE kind = 'plant' AND NOT id = ANY(%s)", (keep,))
        conn.execute("DELETE FROM users WHERE role <> 'admin' AND (org_id IS NULL OR NOT org_id = ANY(%s))", (kept_orgs,))
        conn.execute("DELETE FROM organizations o WHERE NOT id = ANY(%s) AND NOT EXISTS "
                     "(SELECT 1 FROM users u WHERE u.org_id = o.id)", (kept_orgs,))
        accounts.audit(conn, "demo.reset", details={"plants": len(plants), "users": len(users),
                                                     "organizations": len(orgs), "kept": keep, "via": "cli"})
    print("removed.")
    from app.services.site_connection import apply_revocations

    apply_revocations()
    if promote:
        from app.services import model_registry, run_store
        from app.settings import get_settings

        settings = get_settings()
        for run_id in promote:
            run = run_store.get_run(settings, run_id)
            if run is None or run.status != "done":
                sys.exit(f"Run {run_id} not found or not finished")
            m = model_registry.promote(settings, run, promoted_by="ArqauQuat team")
            with accounts.connect() as conn:
                accounts.audit(conn, "model.promote", target=run_id,
                               details={"energy_type": m.energy_type, "horizon": m.horizon, "via": "demo-reset"})
            print(f"promoted {run_id}: {m.energy_type} {m.horizon} h")


if __name__ == "__main__":
    main()
