"""
Settings for the federated platform endpoints (sites, runs, forecast, models).

Read from the environment on every call so tests can point them at a
temporary folder.  Defaults work for a local checkout:

  FEDWIND_DATA_DIR    <repo>/deploy/data   (runs/, models/, sites/)
  FEDWIND_SITES_SEED  <repo>/deploy/seed/sites.json
  FEDERATION_ADDRESS  unset -> federation "not connected"
  INFERENCE_URL_TEMPLATE  unset -> inference "not connected"
                      e.g. http://inference-{site}:8000
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# <repo>/federated-website/FastApi/app/settings.py -> <repo>; in a container
# the file sits higher up, so the env vars above must be set there.
_parents = Path(__file__).resolve().parents
_REPO_ROOT = _parents[3] if len(_parents) > 3 else Path("/")


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    sites_seed: Path
    federation_address: Optional[str]
    inference_url_template: Optional[str]

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def sites_dir(self) -> Path:
        return self.data_dir / "sites"


def get_settings() -> Settings:
    return Settings(
        data_dir=Path(os.environ.get("FEDWIND_DATA_DIR", _REPO_ROOT / "deploy" / "data")),
        sites_seed=Path(os.environ.get("FEDWIND_SITES_SEED", _REPO_ROOT / "deploy" / "seed" / "sites.json")),
        federation_address=os.environ.get("FEDERATION_ADDRESS") or None,
        inference_url_template=os.environ.get("INFERENCE_URL_TEMPLATE") or None,
    )
