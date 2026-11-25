"""
Flower node registration (SITE_NETWORK_PLAN.md M3, §2.1 L3): a plant's SuperNode key is registered
with the SuperLink at enrollment and unregistered when the plant is revoked or re-issued.

  FLOWER_NODE_AUTH=off (default)  the SuperLink runs without --enable-supernode-auth (lab Compose):
                                  the public key is stored, nothing is registered
  FLOWER_NODE_AUTH=on             `flwr supernode register|unregister` over the Control API, with the
                                  same FLOWER_APP_DIR / FLWR_FEDERATION as runs

Flower refuses a key it has seen before, even after unregistering, so a re-issued kit always
brings new keys (the site agent generates them at every enrollment).
"""

import os
import tempfile
from typing import Optional, Protocol

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.services.federation_client import FederationUnavailable, FlwrCliFederation
from app.settings import get_settings


class FlowerKeyError(ValueError):
    """The SuperNode public key is unusable; the message goes back to the site agent."""


class FlowerNodes(Protocol):
    def register(self, public_key: str) -> str: ...
    def unregister(self, node_id: str) -> None: ...


def check_public_key(public_key: str) -> str:
    """An OpenSSH EC public key on a NIST curve (what `flwr supernode register` accepts); returns it
    as one normalized line."""
    line = " ".join((public_key or "").split())
    try:
        key = serialization.load_ssh_public_key(line.encode())
    except (ValueError, TypeError, IndexError, UnsupportedAlgorithm):
        raise FlowerKeyError("The Flower key must be an OpenSSH public key (ecdsa-sha2-nistp384 ...)") from None
    if not isinstance(key, ec.EllipticCurvePublicKey):
        raise FlowerKeyError("The Flower key must be an EC key (P-384 recommended)")
    # Re-serialize: drops comments, so the same key always compares equal
    return key.public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()


class FlwrCliNodes:
    def __init__(self, fed: FlwrCliFederation):
        self.fed = fed

    def register(self, public_key: str) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".pub", delete=False) as f:
            f.write(public_key + "\n")
            path = f.name
        try:
            data = self.fed._flwr("supernode", "register", path, self.fed.app_dir, self.fed.federation,
                                  "--format", "json", timeout=30)
        finally:
            os.unlink(path)
        node_id = data.get("node-id") or data.get("node_id")
        if node_id is None:
            raise FederationUnavailable("`flwr supernode register` returned no node id")
        return str(node_id)

    def unregister(self, node_id: str) -> None:
        self.fed._flwr("supernode", "unregister", str(node_id), self.fed.app_dir, self.fed.federation,
                       "--format", "json", timeout=30)


def enabled() -> bool:
    return os.environ.get("FLOWER_NODE_AUTH", "off").lower() in ("on", "true", "1", "yes")


def get_flower_nodes() -> Optional[FlowerNodes]:
    """None when node auth is off (nothing to register)."""
    if not enabled():
        return None
    settings = get_settings()
    if not settings.federation_address:
        raise FederationUnavailable("FLOWER_NODE_AUTH=on but no SuperLink is configured (FEDERATION_ADDRESS)")
    return FlwrCliNodes(FlwrCliFederation(
        address=settings.federation_address,
        app_dir=os.environ.get("FLOWER_APP_DIR", "/flower_app"),
        federation=os.environ.get("FLWR_FEDERATION", "lab"),
        flwr_bin=os.environ.get("FLWR_BIN", "flwr"),
        server_runs_dir=os.environ.get("SERVER_RUNS_DIR", str(settings.runs_dir)),
    ))
