#!/usr/bin/env python3
"""
Create N simulated plants through the website's own API, exactly as people would
(SITE_NETWORK_PLAN.md M9): an operator registers each plant, an admin approves it, the operator
downloads its site kit. deploy/dev/spawn_sites.sh then starts every kit as a simulated plant.

  python3 deploy/dev/spawn_sites.py 20 --api http://localhost:8001 --admin you@org.kz
  python3 deploy/dev/spawn_sites.py 20 --api https://arqauquat.kz --admin you@org.kz --energy solar

The admin password is asked at a hidden prompt (or ADMIN_PASSWORD). The simulation operator
(sim-operator@arqauquat.test, organization "ArqauQuat simulation") is created on first use with a
random password kept only in deploy/dev/.sim-operator (0600). Kits go to deploy/dev/kits/.
Plants sit at real wind and solar regions of Kazakhstan (approximate coordinates), with a small
offset per copy so 20 plants don't share one point. Standard library only.
"""

import argparse
import getpass
import http.cookiejar
import json
import os
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CRED = HERE / ".sim-operator"
OPERATOR = "sim-operator@arqauquat.test"

# name, energy, lat, lon, timezone, capacity kW (approximate regions of existing or planned plants)
REGIONS = [
    ("Ereymentau Wind", "wind", 51.62, 73.10, "Asia/Almaty", 50_000),
    ("Zhanatas Wind", "wind", 43.57, 69.75, "Asia/Almaty", 100_000),
    ("Shokpar Wind", "wind", 43.83, 74.95, "Asia/Almaty", 100_000),
    ("Kordai Wind", "wind", 43.04, 74.70, "Asia/Almaty", 21_000),
    ("Fort-Shevchenko Wind", "wind", 44.52, 50.26, "Asia/Aqtau", 48_000),
    ("Ybyrai Wind", "wind", 53.15, 69.10, "Asia/Almaty", 50_000),
    ("Abay Wind", "wind", 49.98, 82.60, "Asia/Almaty", 30_000),
    ("Burnoye Solar", "solar", 42.60, 70.80, "Asia/Almaty", 100_000),
    ("Saran Solar", "solar", 49.79, 72.84, "Asia/Almaty", 100_000),
    ("Kapshagay Solar", "solar", 43.88, 77.07, "Asia/Almaty", 100_000),
    ("Shu Valley Solar", "solar", 43.60, 73.76, "Asia/Almaty", 50_000),
    ("Nura Solar", "solar", 50.65, 69.20, "Asia/Almaty", 100_000),
    ("Kyzylorda Solar", "solar", 44.85, 65.51, "Asia/Qyzylorda", 50_000),
    ("Turkistan Solar", "solar", 43.30, 68.27, "Asia/Almaty", 50_000),
]
EQUIPMENT = {"wind": {"turbine_model": "Generic 2.5 MW", "turbine_count": 20, "hub_height_m": 100},
             "solar": {"module_type": "Mono PERC", "tilt_deg": 35, "azimuth_deg": 180, "tracking": "fixed"}}


class Client:
    def __init__(self, api: str):
        self.api = api.rstrip("/")
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf = None

    def call(self, method: str, path: str, body=None, raw: bool = False):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.api + path, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.csrf and method != "GET":
            req.add_header("X-CSRF-Token", self.csrf)
        try:
            with self.opener.open(req, timeout=60) as r:
                payload = r.read()
                return payload if raw else (json.loads(payload) if payload else {})
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            raise SystemExit(f"{method} {path}: HTTP {e.code} {detail}") from None

    def login(self, email: str, password: str):
        self.csrf = self.call("POST", "/api/auth/login", {"email": email, "password": password})["csrf_token"]


def operator(api: str) -> Client:
    c = Client(api)
    if CRED.is_file():
        c.login(OPERATOR, CRED.read_text().strip())
        return c
    password = secrets.token_urlsafe(18)
    try:
        r = c.call("POST", "/api/auth/register", {"email": OPERATOR, "password": password,
                                                  "name": "Simulation Operator", "organization": "ArqauQuat simulation"})
    except SystemExit as e:
        raise SystemExit(f"{e}\nRegistration must be open (ALLOW_REGISTRATION=true) for the first run.")
    fd = os.open(CRED, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(password + "\n")
    c.csrf = r.get("csrf_token")
    if not c.csrf:
        c.login(OPERATOR, password)
    return c


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("count", type=int)
    p.add_argument("--api", default="http://localhost:8001", help="API (lab) or the website (central server)")
    p.add_argument("--admin", required=True, help="an admin account's e-mail")
    p.add_argument("--energy", choices=["wind", "solar", "both"], default="both")
    p.add_argument("--no-window", action="store_true", help="plants don't share a window (local-mode forecasts)")
    p.add_argument("--out", default=str(HERE / "kits"))
    args = p.parse_args()

    regions = [r for r in REGIONS if args.energy in ("both", r[1])]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    op = operator(args.api)
    admin = Client(args.api)
    admin.login(args.admin, os.environ.get("ADMIN_PASSWORD") or getpass.getpass(f"Password for {args.admin}: "))

    for i in range(args.count):
        name, energy, lat, lon, tz, cap = regions[i % len(regions)]
        copy = i // len(regions)
        site = op.call("POST", "/api/sites", {
            "name": f"Sim {name}" + (f" {copy + 1}" if copy else ""), "energy_type": energy,
            "lat": round(lat + 0.05 * copy, 4), "lon": round(lon + 0.05 * copy, 4), "timezone": tz,
            "capacity_kw": cap, "equipment": EQUIPMENT[energy], "data_source": "csv",
            "contact": "simulation@arqauquat.test",
            "consents": {"train": True, "share_forecast_window": not args.no_window, "public_forecasts": False}})
        admin.call("POST", f"/api/admin/sites/{site['id']}/approve", {"note": "M9 simulation"})
        kit = op.call("POST", f"/api/my/sites/{site['id']}/kit", raw=True)
        path = out / f"fedwind-site-{site['id']}.zip"
        path.write_bytes(kit)
        print(f"{i + 1:>3}  {site['id']:<40} {energy:<5}  {path}")
    print(f"\n{args.count} kits in {out}. Start them with: deploy/dev/spawn_sites.sh --start {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
