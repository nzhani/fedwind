"""
Certificates the central server needs before anything else starts (SITE_NETWORK_PLAN.md §2.3).
Runs as the one-shot `pki-init` service on every `docker compose up`; idempotent.

  /internal-ca/ca.key, ca.crt     internal CA (10 years). Only this service mounts its key.
  /superlink-tls/                 superlink.crt + .key (SAN "superlink", 1 year, renewed when < 30 days
                                  left) and ca.crt: TLS for the Fleet and Control APIs inside the server
  /internal-trust/ca.crt          the internal CA certificate only: the API (flwr CLI) and the gateway
                                  (grpcs to the SuperLink) trust it
  /certs/live/<host>/             placeholder self-signed fullchain.pem + privkey.pem for WEB_HOST and
                                  SITES_HOST, only when missing, so nginx can start before
                                  Let's Encrypt (deploy/central/certs.sh) has issued the real ones

The site CA (plant certificates) is the API's (federated-website/FastApi/app/services/site_ca.py).
"""

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CA_DIR = Path(os.environ.get("INTERNAL_CA_DIR", "/internal-ca"))
SUPERLINK_DIR = Path(os.environ.get("SUPERLINK_TLS_DIR", "/superlink-tls"))
TRUST_DIR = Path(os.environ.get("INTERNAL_TRUST_DIR", "/internal-trust"))
CERTS_DIR = Path(os.environ.get("GATEWAY_CERTS_DIR", "/certs"))
RENEW_BEFORE = timedelta(days=30)


def now() -> datetime:
    return datetime.now(timezone.utc)


def write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def pem_key(key) -> bytes:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def pem_cert(cert) -> bytes:
    return cert.public_bytes(serialization.Encoding.PEM)


def not_after(cert) -> datetime:
    return getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after.replace(tzinfo=timezone.utc)


def internal_ca():
    key_file, cert_file = CA_DIR / "ca.key", CA_DIR / "ca.crt"
    if key_file.is_file() and cert_file.is_file():
        return (serialization.load_pem_private_key(key_file.read_bytes(), None),
                x509.load_pem_x509_certificate(cert_file.read_bytes()))
    key = ec.generate_private_key(ec.SECP384R1())
    name = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ArqauQuat"),
                      x509.NameAttribute(NameOID.COMMON_NAME, "ArqauQuat internal CA")])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now() - timedelta(minutes=5)).not_valid_after(now() + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(key, hashes.SHA384()))
    write(key_file, pem_key(key), 0o600)
    write(cert_file, pem_cert(cert), 0o644)
    print("internal CA created")
    return key, cert


def server_cert(ca_key, ca_cert, names, days):
    key = ec.generate_private_key(ec.SECP256R1())
    ski = ca_cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])]))
            .issuer_name(ca_cert.subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now() - timedelta(minutes=5)).not_valid_after(now() + timedelta(days=days))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in names]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(ski), critical=False)
            .sign(ca_key, hashes.SHA384()))
    return key, cert


def superlink(ca_key, ca_cert) -> None:
    crt = SUPERLINK_DIR / "superlink.crt"
    if crt.is_file() and not_after(x509.load_pem_x509_certificate(crt.read_bytes())) - now() > RENEW_BEFORE:
        return
    key, cert = server_cert(ca_key, ca_cert, ["superlink"], 365)
    write(SUPERLINK_DIR / "superlink.key", pem_key(key), 0o600)
    write(crt, pem_cert(cert), 0o644)
    print(f"SuperLink certificate issued, valid until {not_after(cert):%Y-%m-%d} (restart superlink to load it)")


def placeholder(host: str) -> None:
    live = CERTS_DIR / "live" / host
    if (live / "fullchain.pem").is_file() and (live / "privkey.pem").is_file():
        return
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now() - timedelta(minutes=5)).not_valid_after(now() + timedelta(days=30))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False)
            .sign(key, hashes.SHA256()))
    write(live / "privkey.pem", pem_key(key), 0o600)
    write(live / "fullchain.pem", pem_cert(cert), 0o644)
    print(f"placeholder certificate for {host} (self-signed; run deploy/central/certs.sh issue)")


def main() -> int:
    hosts = [h for h in (os.environ.get("WEB_HOST", ""), os.environ.get("SITES_HOST", "")) if h]
    if len(hosts) != 2:
        print("WEB_HOST and SITES_HOST must be set (deploy/central/.env)", file=sys.stderr)
        return 1
    ca_key, ca_cert = internal_ca()
    superlink(ca_key, ca_cert)
    write(SUPERLINK_DIR / "ca.crt", pem_cert(ca_cert), 0o644)
    write(TRUST_DIR / "ca.crt", pem_cert(ca_cert), 0o644)
    for host in hosts:
        placeholder(host)
    print("pki-init: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
