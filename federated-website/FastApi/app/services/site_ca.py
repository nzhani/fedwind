"""
The site CA (SITE_NETWORK_PLAN.md M3, §2.3): signs plant client certificates from a CSR and
publishes the certificate revocation list the gateway checks (nginx `ssl_client_certificate` +
`ssl_crl`, M4).

Files in SITE_CA_DIR (default <FEDWIND_DATA_DIR>/site-ca; in Compose a volume only the API mounts):
  ca.key      EC P-384 private key, 0600. Back it up offline; losing it means re-enrolling every plant.
  ca.crt      self-signed, 5 years; goes into every site kit and to the gateway
  crl.pem     revoked plant certificates that haven't expired yet; rebuilt on every revocation and
              by the maintenance loop (it must never pass its next-update time, or nginx refuses
              every plant)
  crl.number  CRL sequence number

SITE_CA_PUBLIC_DIR (optional; deploy/central): ca.crt and crl.pem are also copied there, a volume
the gateway mounts read-only, so the gateway never sees ca.key. It reloads when crl.pem changes.

Private keys of plants never come here: a plant sends a CSR, its key stays at the plant.
"""

import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CA_VALIDITY = timedelta(days=5 * 365)
CERT_VALIDITY = timedelta(days=90)      # renewal at 60 days comes with M8
CRL_VALIDITY = timedelta(days=7)        # rebuilt at least daily by the maintenance loop
CA_NAME = "ArqauQuat site CA"
SIGNING_HASH = hashes.SHA384()
EC_CURVES = (ec.SECP256R1, ec.SECP384R1, ec.SECP521R1)


class CsrError(ValueError):
    """The CSR can't be signed; the message goes back to the site agent."""


@dataclass(frozen=True)
class IssuedCert:
    pem: str
    serial: str                 # upper-case hex
    not_after: datetime


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ca_dir() -> Path:
    explicit = os.environ.get("SITE_CA_DIR")
    if explicit:
        return Path(explicit)
    from app.settings import get_settings

    return get_settings().data_dir / "site-ca"


def serial_hex(n: int) -> str:
    return format(n, "X")


def normalize_serial(s: str) -> Optional[str]:
    """Serials compare as numbers: nginx may print leading zeros, colons or lower case."""
    try:
        return serial_hex(int(s.replace(":", "").strip(), 16))
    except (ValueError, AttributeError):
        return None


def _write_private(path: Path, data: bytes, mode: int = 0o600) -> None:
    """Atomic write; the file exists with its final mode before it gets its name."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# The CA itself
# ---------------------------------------------------------------------------

def exists() -> bool:
    d = ca_dir()
    return (d / "ca.key").is_file() and (d / "ca.crt").is_file()


def init_ca() -> bool:
    """Create the CA unless it exists. Returns True when it was created now."""
    d = ca_dir()
    if exists():
        return False
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    key = ec.generate_private_key(ec.SECP384R1())
    name = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ArqauQuat"),
                      x509.NameAttribute(NameOID.COMMON_NAME, CA_NAME)])
    now = _now()
    ski = x509.SubjectKeyIdentifier.from_public_key(key.public_key())
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + CA_VALIDITY)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False,
                                     data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
                                     encipher_only=False, decipher_only=False), critical=True)
        .add_extension(ski, critical=False)
        .sign(key, SIGNING_HASH)
    )
    # Key first: a ca.crt without its key would look like a finished CA
    _write_private(d / "ca.key", key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                   serialization.NoEncryption()))
    _write_private(d / "ca.crt", cert.public_bytes(serialization.Encoding.PEM), 0o644)
    write_crl([])
    return True


def _load() -> Tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
    init_ca()
    d = ca_dir()
    key = serialization.load_pem_private_key((d / "ca.key").read_bytes(), password=None)
    cert = x509.load_pem_x509_certificate((d / "ca.crt").read_bytes())
    return key, cert


def ca_cert_pem() -> str:
    _load()
    return (ca_dir() / "ca.crt").read_text()


# ---------------------------------------------------------------------------
# Plant certificates
# ---------------------------------------------------------------------------

def _check_public_key(pub) -> None:
    if isinstance(pub, ec.EllipticCurvePublicKey):
        if not isinstance(pub.curve, EC_CURVES):
            raise CsrError(f"Unsupported EC curve {pub.curve.name}; use P-256 or P-384")
    elif isinstance(pub, rsa.RSAPublicKey):
        if pub.key_size < 2048:
            raise CsrError("RSA keys need at least 2048 bits")
    else:
        raise CsrError("The CSR key must be EC (P-256/P-384) or RSA (2048+ bits)")


def sign_csr(csr_pem: str, site_id: str, validity: timedelta = CERT_VALIDITY) -> IssuedCert:
    """Check the CSR (valid signature, sensible key, CN = this site) and sign a client certificate.

    The certificate carries only what the CA decides: CN = site id, client-auth usage, 90 days.
    Nothing else from the CSR (other names, extensions) is copied."""
    try:
        csr = x509.load_pem_x509_csr(csr_pem.encode() if isinstance(csr_pem, str) else csr_pem)
    except (ValueError, TypeError) as e:
        raise CsrError(f"Not a PEM certificate signing request: {e}") from None
    if not csr.is_signature_valid:
        raise CsrError("The CSR signature doesn't match its key")
    pub = csr.public_key()
    _check_public_key(pub)
    cns = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if len(cns) != 1 or cns[0].value != site_id:
        raise CsrError(f"The CSR's common name must be the site id '{site_id}'")

    ca_key, ca_cert = _load()
    now = _now()
    not_after = min(now + validity, ca_cert.not_valid_after_utc if hasattr(ca_cert, "not_valid_after_utc")
                    else ca_cert.not_valid_after.replace(tzinfo=timezone.utc))
    serial = x509.random_serial_number()
    ca_ski = ca_cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ArqauQuat plant"),
                                 x509.NameAttribute(NameOID.COMMON_NAME, site_id)]))
        .issuer_name(ca_cert.subject)
        .public_key(pub)
        .serial_number(serial)
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
                                     key_encipherment=isinstance(pub, rsa.RSAPublicKey), data_encipherment=False,
                                     key_agreement=False, key_cert_sign=False, crl_sign=False,
                                     encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(pub), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(ca_ski), critical=False)
        .sign(ca_key, SIGNING_HASH)
    )
    return IssuedCert(pem=cert.public_bytes(serialization.Encoding.PEM).decode(), serial=serial_hex(serial),
                      not_after=not_after)


# ---------------------------------------------------------------------------
# Revocation list
# ---------------------------------------------------------------------------

def write_crl(revoked: Iterable[Tuple[str, datetime]]) -> Path:
    """Write crl.pem with these (serial hex, revoked at) entries; returns its path."""
    if not exists():
        init_ca()
    d = ca_dir()
    key = serialization.load_pem_private_key((d / "ca.key").read_bytes(), password=None)
    cert = x509.load_pem_x509_certificate((d / "ca.crt").read_bytes())
    number_file = d / "crl.number"
    try:
        number = int(number_file.read_text().strip()) + 1
    except (OSError, ValueError):
        number = 1
    now = _now()
    builder = (
        x509.CertificateRevocationListBuilder()
        .issuer_name(cert.subject)
        .last_update(now - timedelta(minutes=5))
        .next_update(now + CRL_VALIDITY)
        .add_extension(x509.CRLNumber(number), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(
            cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value), critical=False)
    )
    seen = set()
    for serial, at in revoked:
        n = int(serial, 16)
        if n in seen:
            continue
        seen.add(n)
        builder = builder.add_revoked_certificate(
            x509.RevokedCertificateBuilder().serial_number(n).revocation_date(at or now).build())
    crl = builder.sign(key, SIGNING_HASH)
    _write_private(number_file, f"{number}\n".encode(), 0o644)
    _write_private(d / "crl.pem", crl.public_bytes(serialization.Encoding.PEM), 0o644)
    publish()
    return d / "crl.pem"


def publish() -> Optional[Path]:
    """Copy the public half (ca.crt, crl.pem) to SITE_CA_PUBLIC_DIR, if set."""
    target = os.environ.get("SITE_CA_PUBLIC_DIR")
    if not target:
        return None
    out = Path(target)
    out.mkdir(parents=True, exist_ok=True)
    d = ca_dir()
    for name in ("ca.crt", "crl.pem"):   # certificate first: the gateway needs both, CRL changes later
        if (d / name).is_file():
            _write_private(out / name, (d / name).read_bytes(), 0o644)
    return out


def read_crl() -> Optional[x509.CertificateRevocationList]:
    p = ca_dir() / "crl.pem"
    return x509.load_pem_x509_crl(p.read_bytes()) if p.is_file() else None

