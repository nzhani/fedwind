"""
The plant's keys (SITE_NETWORK_PLAN.md §2.3), made here at enrollment; private keys never leave.

  secrets/site-tls.key    EC P-256, the client certificate's key (0600)
  secrets/site.crt        client certificate from the ArqauQuat site CA (CN = site id, 90 days)
  secrets/ca.crt          the site CA that signed it
  secrets/flower.key      EC P-384 in OpenSSH format: the Flower SuperNode's identity (0600)
  secrets/flower.key.pub  its public key, registered with the federation at enrollment
  secrets/local-ca.crt    the plant's own CA (its key is discarded after signing) for the tunnel:
  secrets/tunnel.crt/.key the SuperNode talks TLS to the local tunnel (Flower 1.25 can't present a
                          client certificate, and node auth needs TLS to the next hop), and the tunnel
                          connects to the gateway with site.crt (SITE_NETWORK_PLAN.md §1, M0 finding)

A re-issued kit makes new keys: Flower never accepts a key it has seen before.
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

LOCAL_CA = "local-ca.crt"
TUNNEL_CERT = "tunnel.crt"
TUNNEL_KEY = "tunnel.key"
TLS_KEY = "site-tls.key"
CERT = "site.crt"
CA = "ca.crt"
FLOWER_KEY = "flower.key"
FLOWER_PUB = "flower.key.pub"


def write_file(path: Path, data: bytes, mode: int = 0o600) -> None:
    """Atomic; the file has its final mode before it gets its name."""
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


def new_enrollment_keys(secrets: Path, site_id: str) -> tuple[str, str]:
    """Make fresh TLS and Flower keys in `secrets`; returns (CSR PEM, Flower public key line)."""
    tls = ec.generate_private_key(ec.SECP256R1())
    write_file(secrets / TLS_KEY, tls.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                    serialization.NoEncryption()))
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, site_id)]))
           .sign(tls, hashes.SHA256()))

    flower = ec.generate_private_key(ec.SECP384R1())
    write_file(secrets / FLOWER_KEY, flower.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                                                          serialization.NoEncryption()))
    pub = flower.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()
    write_file(secrets / FLOWER_PUB, (pub + f" {site_id}\n").encode(), 0o644)
    return csr.public_bytes(serialization.Encoding.PEM).decode(), pub


def renewal_csr(secrets: Path, site_id: str) -> str:
    """A new TLS key (kept beside the current one until the new certificate arrives) and its CSR."""
    tls = ec.generate_private_key(ec.SECP256R1())
    write_file(secrets / (TLS_KEY + ".new"), tls.private_bytes(serialization.Encoding.PEM,
                                                               serialization.PrivateFormat.PKCS8,
                                                               serialization.NoEncryption()))
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, site_id)]))
           .sign(tls, hashes.SHA256()))
    return csr.public_bytes(serialization.Encoding.PEM).decode()


def install_renewed(secrets: Path, cert_pem: str, ca_pem: Optional[str]) -> None:
    """Swap in the new key and certificate (each replace is atomic; the kit's tunnel reloads when it
    sees a matching pair)."""
    os.replace(secrets / (TLS_KEY + ".new"), secrets / TLS_KEY)
    save_certificate(secrets, cert_pem, ca_pem)


def make_local_tls(secrets: Path, days: int = 365) -> None:
    """A one-off local CA and the tunnel's server certificate (names: tunnel, localhost). The CA key
    is never written: nothing else can be signed with it, and a new one is made with every kit."""
    now = datetime.now(timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ArqauQuat plant-local CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
          .not_valid_after(now + timedelta(days=days))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .sign(ca_key, hashes.SHA256()))
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "tunnel")]))
            .issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=days))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("tunnel"), x509.DNSName("localhost")]),
                           critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    write_file(secrets / TUNNEL_KEY, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                       serialization.NoEncryption()))
    write_file(secrets / LOCAL_CA, ca.public_bytes(serialization.Encoding.PEM), 0o644)
    # Last: the kit's healthcheck waits for this file before starting the tunnel and the SuperNode
    write_file(secrets / TUNNEL_CERT, cert.public_bytes(serialization.Encoding.PEM), 0o644)


def save_certificate(secrets: Path, cert_pem: str, ca_pem: Optional[str]) -> None:
    write_file(secrets / CERT, cert_pem.encode(), 0o644)
    if ca_pem:
        write_file(secrets / CA, ca_pem.encode(), 0o644)


def certificate_days_left(secrets: Path) -> Optional[float]:
    p = secrets / CERT
    if not p.is_file():
        return None
    cert = x509.load_pem_x509_certificate(p.read_bytes())
    not_after = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after.replace(tzinfo=timezone.utc)
    return (not_after - datetime.now(timezone.utc)).total_seconds() / 86400
