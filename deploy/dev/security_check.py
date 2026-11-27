#!/usr/bin/env python3
"""
Security checks against a running central deployment (SITE_NETWORK_PLAN.md §2.4, M9). Run from a
machine outside the server; prints one line per check and exits 1 if any fails.

  python3 deploy/dev/security_check.py --address 203.0.113.10 --web-host arqauquat.kz --sites-host sites.arqauquat.kz
  # optional, to test a real plant certificate and a revoked one (files from a test plant's secrets/):
  ... --plant-cert site.crt --plant-key site-tls.key --revoked-cert old.crt --revoked-key old.key
  # placeholder (self-signed) server certificates before Let's Encrypt: add --insecure

Checks
  ports          only 80 and 443 answer (5432, 8000, 8001, 3000, 9091-9094 closed)
  no cert        site API and Flower Fleet API refuse a client without a certificate (403)
  other CA       a certificate from another CA is refused (400)
  revoked        a revoked plant certificate is refused (400)            [with --revoked-*]
  valid plant    a valid plant certificate reaches the site API; the Flower Control API is not routed (404)
  web host       /site-api is not served to browsers; identity headers sent by a browser are ignored
  tokens         an invalid enrollment token is refused (401); repeated attempts are rate-limited (429)
  login          repeated failed logins are rate-limited (429)
  headers        HSTS on the web host; the server does not announce its version
Needs: requests, cryptography (both in the API's environment).
"""

import argparse
import socket
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

RESULTS = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{': ' + detail if detail else ''}")


def other_ca_cert(folder: Path, cn: str) -> tuple:
    """A client certificate from a CA that isn't ArqauQuat's."""
    now = datetime.now(timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Not the ArqauQuat CA")])
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=1))
            .sign(ca_key, hashes.SHA256()))
    c, k = folder / "other.crt", folder / "other.key"
    c.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    k.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()))
    return str(c), str(k)


def ports(address: str) -> None:
    allowed = {80, 443, 22}
    open_ports = []
    for p in (22, 80, 443, 3000, 5432, 8000, 8001, 9091, 9092, 9093, 9094):
        try:
            with socket.create_connection((address, p), timeout=3):
                open_ports.append(p)
        except OSError:
            pass
    bad = [p for p in open_ports if p not in allowed]
    check("only 80/443 (and SSH) reachable", not bad and {80, 443} <= set(open_ports),
          f"open: {open_ports}" + (f"; must be closed: {bad}" if bad else ""))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--address", required=True, help="the server's public address (for the port scan)")
    p.add_argument("--web-host", required=True)
    p.add_argument("--sites-host", required=True)
    p.add_argument("--insecure", action="store_true", help="don't verify server certificates (placeholders)")
    p.add_argument("--plant-cert"), p.add_argument("--plant-key")
    p.add_argument("--revoked-cert"), p.add_argument("--revoked-key")
    p.add_argument("--skip-rate-limits", action="store_true", help="don't send bursts (shared or production servers)")
    a = p.parse_args()
    verify = not a.insecure
    if a.insecure:
        requests.packages.urllib3.disable_warnings()
    sites, web = f"https://{a.sites_host}", f"https://{a.web_host}"
    s, w = requests.Session(), requests.Session()   # the host names must resolve to --address

    def get(sess, url, **kw):
        try:
            return sess.request(kw.pop("method", "GET"), url, verify=verify, timeout=15, **kw)
        except requests.exceptions.SSLError as e:
            return type("R", (), {"status_code": f"TLS error ({e.__class__.__name__})", "headers": {}})()
        except requests.RequestException as e:
            return type("R", (), {"status_code": f"no answer ({e.__class__.__name__})", "headers": {}})()

    print("Network")
    ports(a.address)

    print("Plant host without a valid certificate")
    r = get(s, f"{sites}/site-api/heartbeat", method="POST", json={})
    check("site API without certificate refused", r.status_code == 403, f"HTTP {r.status_code}")
    r = get(s, f"{sites}/flwr.proto.Fleet/PullMessages", method="POST", data=b"")
    check("Flower Fleet API without certificate refused", r.status_code == 403, f"HTTP {r.status_code}")
    with tempfile.TemporaryDirectory() as tmp:
        cert = other_ca_cert(Path(tmp), "intruder")
        r = get(s, f"{sites}/site-api/heartbeat", method="POST", json={}, cert=cert)
        check("certificate from another CA refused", r.status_code in (400, 403) or "TLS" in str(r.status_code),
              f"HTTP {r.status_code}")
    if a.revoked_cert and a.revoked_key:
        r = get(s, f"{sites}/site-api/heartbeat", method="POST", json={}, cert=(a.revoked_cert, a.revoked_key))
        check("revoked plant certificate refused", r.status_code == 400 or "TLS" in str(r.status_code),
              f"HTTP {r.status_code}")
    if a.plant_cert and a.plant_key:
        cert = (a.plant_cert, a.plant_key)
        r = get(s, f"{sites}/site-api/heartbeat", method="POST", json={"agent_kind": "kit", "agent_version": "0.3.0"},
                cert=cert)
        check("valid plant certificate accepted", r.status_code == 200, f"HTTP {r.status_code}")
        r = get(s, f"{sites}/flwr.proto.Control/ListRuns", method="POST", data=b"", cert=cert)
        check("Flower Control API not routed", r.status_code == 404, f"HTTP {r.status_code}")
        r = get(s, f"{sites}/api/auth/me", cert=cert)
        check("user API not served on the plant host", r.status_code == 404, f"HTTP {r.status_code}")

    print("Web host")
    r = get(w, f"{web}/site-api/heartbeat", method="POST", json={})
    check("site API not served to browsers", r.status_code == 404, f"HTTP {r.status_code}")
    r = get(w, f"{web}/api/auth/me", headers={"X-Site-Id": "x", "X-Gateway-Secret": "guess", "X-Client-Serial": "01"})
    check("forged identity headers give no access", r.status_code == 401, f"HTTP {r.status_code}")
    r = get(w, f"{web}/")
    check("HSTS on the web host", "strict-transport-security" in {k.lower() for k in r.headers}, "")
    server = r.headers.get("Server", "") if hasattr(r, "headers") else ""
    check("server version not announced", "/" not in server, server or "no Server header")

    print("Tokens and rate limits")
    r = get(s, f"{sites}/site-api/enroll", method="POST", json={"token": "fwe_" + "x" * 40})
    check("invalid enrollment token refused", r.status_code in (401, 422), f"HTTP {r.status_code}")
    if not a.skip_rate_limits:
        codes = [get(s, f"{sites}/site-api/enroll", method="POST", json={"token": "fwe_" + "y" * 40}).status_code
                 for _ in range(30)]
        check("enrollment attempts rate-limited", 429 in codes, f"first 429 after {codes.index(429) + 1 if 429 in codes else '-'} tries")
        codes = [get(w, f"{web}/api/auth/login", method="POST",
                     json={"email": "nobody@example.com", "password": "wrong-password-1"}).status_code for _ in range(45)]
        check("failed logins rate-limited", 429 in codes, f"first 429 after {codes.index(429) + 1 if 429 in codes else '-'} tries")
        time.sleep(1)

    failed = RESULTS.count(False)
    print(f"\n{len(RESULTS) - failed} of {len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
