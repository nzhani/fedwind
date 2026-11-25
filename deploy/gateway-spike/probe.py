"""
Probes from the "internet" network (SITE_NETWORK_PLAN.md §2.4). Prints one PASS/FAIL line per check.

  python /probe.py
"""

import http.client
import socket
import ssl

HOST = "sites.fedwind.test"
PKI = "/pki"


def request(path, cert=None):
    """(status, body) of an HTTPS GET to the gateway, or ('error', reason) if TLS/HTTP fails."""
    ctx = ssl.create_default_context(cafile=f"{PKI}/web-ca.crt")
    if cert:
        ctx.load_cert_chain(f"{PKI}/{cert}.crt", f"{PKI}/{cert}.key")
    try:
        conn = http.client.HTTPSConnection(HOST, 443, context=ctx, timeout=10)
        conn.request("GET", path)
        resp = conn.getresponse()
        return resp.status, resp.read().decode(errors="replace").strip().splitlines()[0:2]
    except (ssl.SSLError, OSError, http.client.HTTPException) as e:
        return "error", f"{type(e).__name__}: {e}"


def reachable(host, port):
    try:
        socket.create_connection((host, port), timeout=3).close()
        return True
    except OSError as e:
        return f"no ({type(e).__name__})"


results = []


def check(name, ok, detail):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")


s, b = request("/site-api/whoami")
check("no client certificate is refused", s != 200, f"{s} {b}")

s, b = request("/site-api/whoami", cert="site1")
check("valid plant certificate is accepted and identified", s == 200 and "CN=konaev" in str(b), f"{s} {b}")

s, b = request("/site-api/whoami", cert="site3")
check("revoked plant certificate is refused", s != 200, f"{s} {b}")

s, b = request("/site-api/whoami", cert="tunnel")  # signed by a plant's local CA, not the site CA
check("certificate from another CA is refused", s != 200, f"{s} {b}")

s, b = request("/flwr.proto.Control/ListRuns", cert="site1")
check("Control API is not proxied even with a valid certificate", s == 404, f"{s} {b}")

for port in (9091, 9092, 9093):
    r = reachable("superlink", port)
    check(f"SuperLink :{port} not reachable from the internet", r is not True, str(r))

print(f"\n{sum(results)}/{len(results)} checks passed")
