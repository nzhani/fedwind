"""Site agent against a fake platform (no network, no Docker)."""

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from site_agent.agent import Agent, Revoked  # noqa: E402
from site_agent.sources import nasa_power  # noqa: E402
from site_agent.sources.csv_inbox import CsvInboxSource  # noqa: E402


class Resp:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakePlatform:
    """Records calls; answers like the real /site-api."""

    def __init__(self, site_id="zh-1", mtls=False):
        self.site_id, self.calls, self.status, self.revoked, self.token_used = site_id, [], "active", False, False
        self.mtls, self.tls = mtls, []

    def post(self, url, json=None, timeout=None, headers=None, **tls):
        path = url.split("8001")[-1]
        self.calls.append((path, json, headers))
        self.tls.append(tls)
        if path == "/site-api/enroll":
            if self.token_used or json["token"] != "fwe_good":
                return Resp(401)
            if not json.get("csr") or not json.get("flower_public_key", "").startswith("ecdsa-sha2-nistp384 "):
                return Resp(422, {"detail": "CSR and Flower key required"})
            self.token_used = True
            body = {"site_id": self.site_id, "config": {"heartbeat_s": 15},
                    "certificate": sign(json["csr"]), "ca_certificate": "CA PEM\n", "flower_node_id": "77"}
            if not self.mtls:
                body["site_key"] = "fws_key"
            return Resp(200, body)
        if self.mtls:
            if "cert" not in tls or self.revoked:
                return Resp(400)            # what nginx answers for a missing or revoked certificate
        elif headers.get("Authorization") != "Bearer fws_key" or self.revoked:
            return Resp(401)
        if path == "/site-api/heartbeat":
            return Resp(200, {"status": self.status, "heartbeat_s": 15})
        return Resp(200, {"ok": True})


def sign(csr_pem: str) -> str:
    """A self-signed stand-in for the platform's CA: same subject and key as the CSR, 90 days."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    csr = x509.load_pem_x509_csr(csr_pem.encode())
    ca = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(csr.subject).issuer_name(csr.subject)
            .public_key(csr.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now).not_valid_after(now + timedelta(days=90)).sign(ca, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def kit(tmp_path, token="fwe_good", source="csv_inbox"):
    (tmp_path / "kit").mkdir()
    (tmp_path / "kit" / "enrollment.token").write_text(token + "\n")
    return {"SITE_ID": "zh-1", "SITE_API_URL": "http://host:8001", "ENERGY_TYPE": "wind", "LAT": "43.5",
            "LON": "69.7", "DATA_SOURCE": source, "HEARTBEAT_S": "30", "SECRETS_DIR": str(tmp_path / "secrets"),
            "TOKEN_FILE": str(tmp_path / "kit" / "enrollment.token"), "DATA_DIR": str(tmp_path / "data")}


def write_inbox(tmp_path, hours=60, bad=(), curtailed=()):
    inbox = tmp_path / "data" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 11, 17, tzinfo=timezone.utc)
    lines = ["timestamp_utc,wind_speed_ms,power_kw,available,curtailed"]
    for i in range(hours):
        t = start + timedelta(hours=i)
        v = "99" if i in bad else f"{5 + i % 7}.0"
        lines.append(f"{t.isoformat().replace('+00:00', 'Z')},{v},1000,1,{1 if i in curtailed else 0}")
    (inbox / "export.csv").write_text("\n".join(lines) + "\n")


def test_enrolls_once_and_keeps_the_key_private(tmp_path):
    p = FakePlatform()
    a = Agent(kit(tmp_path), session=p)
    assert a.kind == "kit"
    a.enroll()
    key = tmp_path / "secrets" / "site.key"
    assert key.read_text().strip() == "fws_key" and (key.stat().st_mode & 0o777) == 0o600
    assert a.heartbeat_s == 15
    # A restart finds the key, so the (now used) token is not sent again
    enrolls = sum(1 for c in p.calls if c[0] == "/site-api/enroll")
    b = Agent(kit_env_defaults(tmp_path), session=p)
    assert b.site_key() == "fws_key"
    b.heartbeat()
    assert sum(1 for c in p.calls if c[0] == "/site-api/enroll") == enrolls


def kit_env_defaults(tmp_path):
    return {"SITE_ID": "zh-1", "SITE_API_URL": "http://host:8001", "ENERGY_TYPE": "wind", "LAT": "43.5",
            "LON": "69.7", "DATA_SOURCE": "csv_inbox", "SECRETS_DIR": str(tmp_path / "secrets"),
            "TOKEN_FILE": str(tmp_path / "kit" / "enrollment.token"), "DATA_DIR": str(tmp_path / "data")}


def test_bad_token_and_wrong_site_are_explained(tmp_path):
    with pytest.raises(RuntimeError, match="download a new kit"):
        Agent(kit(tmp_path, token="fwe_used"), session=FakePlatform()).enroll()
    (tmp_path / "kit" / "enrollment.token").write_text("fwe_good\n")
    with pytest.raises(RuntimeError, match="belongs to site other"):
        Agent(kit_env_defaults(tmp_path), session=FakePlatform(site_id="other")).enroll()


def test_heartbeat_reports_counts_and_learns_suspension(tmp_path):
    write_inbox(tmp_path, hours=60, bad={50})
    p = FakePlatform()
    a = Agent(kit(tmp_path), session=p)
    a.enroll()
    a.source.refresh()
    assert a.heartbeat()["status"] == "active"
    path, body, headers = p.calls[-1]
    assert path == "/site-api/heartbeat" and headers["Authorization"] == "Bearer fws_key"
    assert body["agent_kind"] == "kit" and body["last_data_hour"].startswith("2026-11-19T11:00")
    assert body["rows_today"] == 11 and body["gaps_today"] == 1        # hour 50 = 19 Nov 02:00 is flagged
    assert "wind_speed_ms" not in str(body)                            # counts only, no measurements
    p.status = "suspended"
    a.heartbeat()
    assert a.status == "suspended"
    p.revoked = True
    with pytest.raises(Revoked):
        a.heartbeat()


def test_quality_for_the_seven_newest_data_days(tmp_path):
    write_inbox(tmp_path, hours=48, bad={3}, curtailed={5, 6})
    p = FakePlatform()
    a = Agent(kit(tmp_path), session=p)
    a.enroll()
    a.source.refresh()
    sent = a.daily_quality(now=datetime(2026, 11, 25, tzinfo=timezone.utc))
    assert [s["day"] for s in sent][-2:] == ["2026-11-17", "2026-11-18"] and len(sent) == 7
    q17 = next(c[1] for c in p.calls if c[0] == "/site-api/quality" and c[1]["day"] == "2026-11-17")
    assert q17 == {"day": "2026-11-17", "rows": 23, "gaps": 0, "flagged": 1, "curtailed": 2}
    assert a.daily_quality(now=datetime(2026, 11, 25, 12, tzinfo=timezone.utc)) == []   # once per day


def test_simulated_plant_uses_nasa_power_and_its_cache(tmp_path):
    env = kit(tmp_path, source="nasa_power")
    a = Agent(env, session=FakePlatform())
    assert a.kind == "simulated"

    class Nasa:
        def __init__(self, fail=False):
            self.fail = fail

        def get(self, url, timeout=None, params=None):
            if self.fail:
                raise nasa_power.requests.ConnectionError("offline")
            assert params["parameters"] == "WS50M" and params["time-standard"] == "UTC"
            return Resp(200, {"properties": {"parameter": {"WS50M": {"2026111500": 4.5, "2026111501": -999.0,
                                                                     "2026111502": 6.0}}}})

    src = nasa_power.NasaPowerSource(env, session=Nasa())
    src.refresh()
    assert src.last_hour() == datetime(2026, 11, 15, 2, tzinfo=timezone.utc)
    assert src.day(date(2026, 11, 15)).gaps == 22                      # -999 is a gap, not a value
    # NASA unreachable later: the cache keeps the plant going
    offline = nasa_power.NasaPowerSource(env, session=Nasa(fail=True))
    offline.refresh()
    assert offline.last_hour() == src.last_hour()


def test_csv_source_window_for_central_forecasting(tmp_path):
    write_inbox(tmp_path, hours=30, bad={29})
    src = CsvInboxSource({"ENERGY_TYPE": "wind", "DATA_DIR": str(tmp_path / "data")})
    src.refresh()
    end, values = src.window(4)
    assert end == datetime(2026, 11, 18, 4, tzinfo=timezone.utc) and len(values) == 4 and None not in values


def test_window_only_with_consent_and_only_when_new(tmp_path):
    write_inbox(tmp_path, hours=400)
    p = FakePlatform()
    a = Agent(kit(tmp_path), session=p)
    a.enroll()
    a.source.refresh()
    a.heartbeat()
    assert a.forecast_window() is None                        # enrollment config had no consent
    (tmp_path / "secrets" / "site.json").write_text('{"consents": {"share_forecast_window": true}}')
    assert a.forecast_window() is not None
    path, body, _ = p.calls[-1]
    assert path == "/site-api/forecast-input" and len(body["values"]) == 336
    assert body["end_hour"].startswith("2026-12-03T15:00")    # newest hour of the 400-hour export
    assert a.forecast_window() is None                        # nothing new since
    p.status = "suspended"
    a.heartbeat()
    a.last_window_end = None
    assert a.forecast_window() is None                        # paused while suspended


def test_solar_looks_back_far_enough_for_nasa_irradiance(tmp_path):
    """NASA's hourly irradiance lags about 3 months, so the solar source asks for 150 days."""
    env = {**kit(tmp_path, source="nasa_power"), "ENERGY_TYPE": "solar"}
    seen = {}

    class Nasa:
        def get(self, url, timeout=None, params=None):
            seen.update(params)
            return Resp(200, {"properties": {"parameter": {"ALLSKY_SFC_SW_DWN": {"2026083112": 640.0}}}})

    src = nasa_power.NasaPowerSource(env, session=Nasa())
    src.refresh()
    start = datetime.strptime(seen["start"], "%Y%m%d").date()
    assert seen["parameters"] == "ALLSKY_SFC_SW_DWN" and (datetime.now(timezone.utc).date() - start).days == 150
    assert src.last_hour() == datetime(2026, 8, 31, 12, tzinfo=timezone.utc)


def test_enrollment_makes_keys_here_and_sends_only_public_parts(tmp_path):
    from cryptography import x509
    from cryptography.x509.oid import NameOID

    p = FakePlatform()
    a = Agent(kit(tmp_path), session=p)
    a.enroll()
    sent = next(c[1] for c in p.calls if c[0] == "/site-api/enroll")
    secrets = tmp_path / "secrets"
    for private in ("site-tls.key", "flower.key"):
        assert (secrets / private).stat().st_mode & 0o777 == 0o600
        assert (secrets / private).read_text().strip() not in str(sent)       # private keys stay here
    csr = x509.load_pem_x509_csr(sent["csr"].encode())
    assert csr.is_signature_valid and csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == "zh-1"
    assert sent["flower_public_key"] == (secrets / "flower.key.pub").read_text().split(" zh-1")[0]
    assert (secrets / "site.crt").is_file() and (secrets / "ca.crt").read_text() == "CA PEM\n"
    # The tunnel's local TLS: its certificate chains to the plant-local CA, whose key is not kept
    from cryptography.hazmat.primitives.asymmetric import ec as _ec
    local_ca = x509.load_pem_x509_certificate((secrets / "local-ca.crt").read_bytes())
    tunnel = x509.load_pem_x509_certificate((secrets / "tunnel.crt").read_bytes())
    local_ca.public_key().verify(tunnel.signature, tunnel.tbs_certificate_bytes, _ec.ECDSA(tunnel.signature_hash_algorithm))
    assert sorted(f.name for f in secrets.iterdir() if "ca" in f.name and f.suffix == ".key") == []
    assert p.tls == [{}]                                                       # token mode: no TLS options


def test_mtls_mode_uses_the_certificate_and_learns_revocation(tmp_path):
    p = FakePlatform(mtls=True)
    env = {**kit(tmp_path), "SITE_AUTH_MODE": "mtls"}
    a = Agent(env, session=p)
    assert not a.enrolled()
    assert a.enroll() is None and a.enrolled() and not (tmp_path / "secrets" / "site.key").exists()
    assert "cert" not in p.tls[0]                                              # enrollment: token, no certificate
    a.heartbeat()
    path, _, headers = p.calls[-1]
    assert path == "/site-api/heartbeat" and "Authorization" not in headers
    assert p.tls[-1]["cert"] == (str(tmp_path / "secrets" / "site.crt"), str(tmp_path / "secrets" / "site-tls.key"))
    p.revoked = True
    with pytest.raises(Revoked):
        a.heartbeat()


def test_every_enrollment_attempt_gets_fresh_flower_keys(tmp_path):
    p = FakePlatform()
    a = Agent(kit(tmp_path), session=p)
    p.token_used = True                       # first attempt refused
    with pytest.raises(RuntimeError):
        a.enroll()
    first = (tmp_path / "secrets" / "flower.key.pub").read_text()
    p.token_used = False
    a.enroll()
    assert (tmp_path / "secrets" / "flower.key.pub").read_text() != first


def test_training_store_in_the_nasa_layout_the_flower_app_reads(tmp_path):
    from site_agent.store import MISSING

    write_inbox(tmp_path, hours=60, bad={10})
    a = Agent(kit(tmp_path), session=FakePlatform())
    a.source.refresh()
    assert a.store.update(a.source) and not a.store.update(a.source)        # rewritten only on change
    text = (tmp_path / "data" / "store" / "nasa_zh-1.csv").read_text().splitlines()
    end = text.index("-END HEADER-")
    assert any(l.startswith("Location: Latitude  43.5000   Longitude 69.7000") for l in text[:end])
    assert text[end + 1] == "YEAR,MO,DY,HR,WS50M"
    rows = text[end + 2:]
    assert len(rows) == 60 and rows[0] == "2026,11,17,0,5.0" and rows[10].endswith(f",{MISSING}")
    assert a.store.hours == 59
    a.enroll()
    a.heartbeat()
    assert p_last(a)["train_hours"] == 59


def p_last(agent):
    return agent.http.calls[-1][1]


def test_store_starts_after_a_long_outage(tmp_path):
    from site_agent.sources import HourlySource
    from site_agent.store import TrainingStore

    src = HourlySource("solar")
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    src.values = {t0 + timedelta(hours=i): 100.0 for i in range(48)}                       # old block
    src.values.update({t0 + timedelta(days=30, hours=i): 200.0 for i in range(100)})       # after 4 weeks off
    store = TrainingStore(tmp_path, "s-1", 43.0, 77.0)
    store.update(src)
    rows = store.path.read_text().split("-END HEADER-\n")[1].splitlines()
    assert rows[0] == "YEAR,MO,DY,HR,ALLSKY_SFC_SW_DWN" and len(rows) == 101 and rows[1] == "2026,1,31,0,200.0"


def test_simulated_history_is_fetched_once_per_past_year(tmp_path):
    env = {**kit(tmp_path, source="nasa_power"), "SIM_HISTORY_YEARS": "2"}
    calls = []

    class Nasa:
        def get(self, url, timeout=None, params=None):
            calls.append((params["start"], params["end"]))
            y = params["start"][:4]
            return Resp(200, {"properties": {"parameter": {"WS50M": {f"{y}0601{h:02d}": 7.0 for h in range(24)}}}})

    from site_agent.sources.nasa_power import NasaPowerSource

    src = NasaPowerSource(env, session=Nasa())
    now = datetime(2026, 11, 24, tzinfo=timezone.utc)
    src._load_history(now)
    assert sorted(calls)[:2] == [("20240101", "20241231"), ("20250101", "20251231")]
    assert ("20260101", "20261124") in calls                                    # this year so far
    calls.clear()
    fresh = NasaPowerSource(env, session=Nasa())
    merged = fresh._load_history(now)
    assert calls == [] and len(merged) == 72                                     # from disk


def test_status_page_shows_state_without_secrets(tmp_path):
    import json
    import urllib.request

    from site_agent import status

    p = FakePlatform()
    a = Agent(kit(tmp_path), session=p)
    a.enroll()
    server = status.serve(a, 0)
    try:
        port = server.server_address[1]
        s = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/status.json").read())
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/").read().decode()
    finally:
        server.shutdown()
    assert s["site_id"] == "zh-1" and s["enrolled"] is True and s["certificate_days_left"] > 89
    assert "fws_key" not in page and "PRIVATE" not in page and "zh-1" in page
