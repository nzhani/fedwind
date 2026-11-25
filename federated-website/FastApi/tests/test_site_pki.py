"""Site PKI (SITE_NETWORK_PLAN.md M3): CA, certificate enrollment, Flower node registration, revocation."""

from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from app.services import flower_nodes, site_ca
from app.services.federation_client import FederationUnavailable
from app.services.site_connection import apply_revocations
from tests.test_accounts import csrf, login
from tests.test_site_connection import approved_plant, kit

SECRET = "gateway-s3cret"


def make_csr(cn: str, key=None) -> str:
    key = key or ec.generate_private_key(ec.SECP256R1())
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
           .sign(key, hashes.SHA256()))
    return csr.public_bytes(serialization.Encoding.PEM).decode()


def flower_key() -> str:
    pub = ec.generate_private_key(ec.SECP384R1()).public_key()
    return pub.public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode() + " plant@host"


class FakeNodes:
    def __init__(self):
        self.registered, self.unregistered = {}, []
        self.fail_register = self.fail_unregister = False

    def register(self, public_key):
        if self.fail_register:
            raise FederationUnavailable("`flwr supernode` failed: SuperLink unreachable")
        node_id = str(9000 + len(self.registered))
        self.registered[node_id] = public_key
        return node_id

    def unregister(self, node_id):
        if self.fail_unregister:
            raise FederationUnavailable("`flwr supernode` failed: SuperLink unreachable")
        self.unregistered.append(node_id)


@pytest.fixture
def nodes(monkeypatch):
    fake = FakeNodes()
    monkeypatch.setattr(flower_nodes, "get_flower_nodes", lambda: fake)
    return fake


@pytest.fixture
def mtls(monkeypatch):
    monkeypatch.setenv("SITE_AUTH_MODE", "mtls")
    monkeypatch.setenv("GATEWAY_SHARED_SECRET", SECRET)


def enroll(client, files, csr=None, key=None):
    body = {"token": files["enrollment.token"].strip(), "agent": {"kind": "kit", "version": "0.2.0"}}
    if csr:
        body["csr"] = csr
    if key:
        body["flower_public_key"] = key
    return client.post("/site-api/enroll", json=body)


def gateway_beat(client, site_id, serial, secret=SECRET, **body):
    return client.post("/site-api/heartbeat", json={"agent_kind": "kit", "agent_version": "0.2.0", **body},
                       headers={"X-Gateway-Secret": secret, "X-Site-Id": site_id, "X-Client-Serial": serial})


def as_admin(client):
    client.cookies.clear()
    return login(client, "admin@fedwind.kz")[1]


def as_operator(client):
    client.cookies.clear()
    return login(client, "op@plant.kz")[1]


# --- the CA on its own ------------------------------------------------------------------------------

def test_ca_signs_only_good_csrs(data_dir):
    assert site_ca.init_ca() is True and site_ca.init_ca() is False
    assert oct((site_ca.ca_dir() / "ca.key").stat().st_mode & 0o777) == "0o600"
    ca = x509.load_pem_x509_certificate(site_ca.ca_cert_pem().encode())

    issued = site_ca.sign_csr(make_csr("zhanatas-1ded"), "zhanatas-1ded")
    cert = x509.load_pem_x509_certificate(issued.pem.encode())
    ca.public_key().verify(cert.signature, cert.tbs_certificate_bytes, ec.ECDSA(cert.signature_hash_algorithm))
    assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == "zhanatas-1ded"
    assert cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value == x509.ExtendedKeyUsage(
        [ExtendedKeyUsageOID.CLIENT_AUTH])
    assert not cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    assert timedelta(days=89) < issued.not_after - datetime.now(timezone.utc) <= timedelta(days=90)
    assert site_ca.normalize_serial(format(cert.serial_number, "x").zfill(40)) == issued.serial

    with pytest.raises(site_ca.CsrError, match="common name"):
        site_ca.sign_csr(make_csr("another-site"), "zhanatas-1ded")
    with pytest.raises(site_ca.CsrError, match="2048"):
        site_ca.sign_csr(make_csr("s", rsa.generate_private_key(65537, 1024)), "s")
    with pytest.raises(site_ca.CsrError, match="PEM"):
        site_ca.sign_csr("-----BEGIN CERTIFICATE REQUEST-----\nAAAA\n-----END CERTIFICATE REQUEST-----", "s")

    site_ca.write_crl([(issued.serial, datetime.now(timezone.utc))])
    crl = site_ca.read_crl()
    assert crl.is_signature_valid(ca.public_key())
    assert crl.get_revoked_certificate_by_serial_number(cert.serial_number) is not None
    assert crl.next_update_utc > datetime.now(timezone.utc) + timedelta(days=6)


def test_flower_key_must_be_openssh_ec():
    key = flower_key()
    assert flower_nodes.check_public_key(key) == key.rsplit(" ", 1)[0]       # comment dropped
    rsa_pub = rsa.generate_private_key(65537, 2048).public_key().public_bytes(
        serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()
    for bad in ("ssh-ed25519 AAAA", rsa_pub, "not a key"):
        with pytest.raises(flower_nodes.FlowerKeyError):
            flower_nodes.check_public_key(bad)


# --- enrollment --------------------------------------------------------------------------------------

def test_certificate_enrollment_and_revocation(db_client, pg_url, nodes, mtls):
    site_id, op = approved_plant(db_client)
    files = kit(db_client, site_id, op)
    assert "SITE_AUTH_MODE=mtls" in files[".env"] and "COMPOSE_PROFILES=federation" in files[".env"]
    assert "GATEWAY_HOST=" in files[".env"] and "{{" not in files["docker-compose.yml"]
    assert f'site="{site_id}" energy="wind"' in files["docker-compose.yml"]          # the SuperNode's identity
    assert "--auth-supernode-private-key=/secrets/flower.key" in files["docker-compose.yml"]
    assert "grpc_ssl_certificate         /pki/site.crt" in files["tunnel.conf.template"]
    assert "nvidia" in files["docker-compose.gpu.yml"]
    assert files["ca.crt"] == site_ca.ca_cert_pem() and "PRIVATE" not in files["ca.crt"]

    # Every refusal leaves the token usable
    assert enroll(db_client, files).status_code == 422                                   # no CSR
    assert enroll(db_client, files, make_csr("someone-else"), flower_key()).status_code == 422
    assert enroll(db_client, files, make_csr(site_id)).status_code == 422                # no Flower key
    assert enroll(db_client, files, make_csr(site_id), "ssh-rsa AAAA").status_code == 422
    nodes.fail_register = True
    assert enroll(db_client, files, make_csr(site_id), flower_key()).status_code == 503
    nodes.fail_register = False
    assert nodes.registered == {}

    fkey = flower_key()
    r = enroll(db_client, files, make_csr(site_id), fkey)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "site_key" not in body and body["flower_node_id"] == "9000"
    assert nodes.registered == {"9000": fkey.rsplit(" ", 1)[0]}
    cert = x509.load_pem_x509_certificate(body["certificate"].encode())
    serial = format(cert.serial_number, "X")
    assert body["ca_certificate"] == files["ca.crt"]
    assert enroll(db_client, files, make_csr(site_id), flower_key()).status_code == 401  # one use only

    with psycopg.connect(pg_url) as conn:
        kind, stored, node = conn.execute("SELECT kind, cert_serial, flower_node_id FROM site_credentials").fetchone()
    assert (kind, stored, node) == ("cert", serial, "9000")

    # The gateway's headers: the right site with its live certificate only
    assert gateway_beat(db_client, site_id, serial).json()["status"] == "active"
    assert gateway_beat(db_client, site_id, "00:" + serial.lower()).status_code == 200   # serial formats
    assert gateway_beat(db_client, site_id, serial, secret="wrong").status_code == 401
    assert gateway_beat(db_client, site_id, "ABCDEF").status_code == 401
    assert gateway_beat(db_client, "almaty", serial).status_code == 401
    d = db_client.get(f"/api/my/sites/{site_id}").json()
    assert d["can_train"] is False and d["train_note"] == "0 of 2160 hours of training data"
    gateway_beat(db_client, site_id, serial, train_hours=2200)                        # store big enough
    d = db_client.get(f"/api/my/sites/{site_id}").json()
    assert d["can_train"] is True and d["train_note"] is None and d["connection"]["train_hours"] == 2200
    assert d["connection"]["state"] == "online"

    t = as_admin(db_client)
    assert db_client.post(f"/api/admin/sites/{site_id}/revoke", json={"note": "Left"}, headers=csrf(t)).status_code == 200
    assert gateway_beat(db_client, site_id, serial).status_code == 401
    assert site_ca.read_crl().get_revoked_certificate_by_serial_number(cert.serial_number) is not None
    assert nodes.unregistered == ["9000"]
    with psycopg.connect(pg_url) as conn:
        done = conn.execute("SELECT flower_unregistered_at FROM site_revocations").fetchone()[0]
    assert done is not None


def test_reissue_needs_new_keys_and_retries_unregistering(db_client, pg_url, nodes, mtls):
    site_id, op = approved_plant(db_client)
    fkey = flower_key()
    first = enroll(db_client, kit(db_client, site_id, op), make_csr(site_id), fkey).json()

    nodes.fail_unregister = True
    t = as_admin(db_client)
    r = db_client.post(f"/api/admin/sites/{site_id}/reissue-kit", json={"note": "Server replaced"}, headers=csrf(t))
    assert r.status_code == 200
    old = x509.load_pem_x509_certificate(first["certificate"].encode())
    assert site_ca.read_crl().get_revoked_certificate_by_serial_number(old.serial_number) is not None  # cut off anyway
    with psycopg.connect(pg_url) as conn:
        pending, error = conn.execute("SELECT flower_unregistered_at, flower_error FROM site_revocations").fetchone()
    assert pending is None and "unreachable" in error

    op = as_operator(db_client)
    files = kit(db_client, site_id, op)
    assert enroll(db_client, files, make_csr(site_id), fkey).status_code == 409          # Flower refuses old keys
    second = enroll(db_client, files, make_csr(site_id), flower_key())
    assert second.status_code == 200 and second.json()["flower_node_id"] == "9001"

    nodes.fail_unregister = False
    assert apply_revocations()["unregistered"] == 1                                       # the maintenance loop
    assert nodes.unregistered == ["9000"]


def test_token_mode_with_a_csr_gets_both(db_client):
    """Development: the agent always sends a CSR; it gets a certificate and a bearer site key."""
    site_id, op = approved_plant(db_client)
    kit_files = kit(db_client, site_id, op)
    r = enroll(db_client, kit_files, make_csr(site_id), flower_key())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["site_key"].startswith("fws_") and body["certificate"] and "flower_node_id" not in body
    assert "COMPOSE_PROFILES=\n" in kit_files[".env"]                              # no tunnel/SuperNode in dev
    beat = db_client.post("/site-api/heartbeat", json={}, headers={"Authorization": f"Bearer {body['site_key']}"})
    assert beat.json()["status"] == "active"


def test_deleted_plants_stay_in_the_crl(db_client, pg_url, nodes, mtls):
    from app.cli import demo_reset

    site_id, op = approved_plant(db_client)
    body = enroll(db_client, kit(db_client, site_id, op), make_csr(site_id), flower_key()).json()
    demo_reset(True, [])
    with psycopg.connect(pg_url) as conn:
        assert conn.execute("SELECT count(*) FROM sites WHERE id = %s", (site_id,)).fetchone()[0] == 0
    serial = x509.load_pem_x509_certificate(body["certificate"].encode()).serial_number
    assert site_ca.read_crl().get_revoked_certificate_by_serial_number(serial) is not None
    assert nodes.unregistered == [body["flower_node_id"]]


def test_public_half_is_published_for_the_gateway(data_dir, monkeypatch, tmp_path):
    monkeypatch.setenv("SITE_CA_PUBLIC_DIR", str(tmp_path / "public"))
    site_ca.init_ca()
    public = sorted(f.name for f in (tmp_path / "public").iterdir())
    assert public == ["ca.crt", "crl.pem"]                                   # never ca.key
    assert (tmp_path / "public" / "ca.crt").read_text() == site_ca.ca_cert_pem()
