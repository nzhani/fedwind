"""
The plant's training store (SITE_NETWORK_PLAN.md M5): every checked hour the agent has, written
as /data/store/nasa_<site>.csv in the NASA POWER CSV layout the Flower app already reads
(my_flower_app/dataloader.preprocess_nasa_data, solar.solar_frame), so the SuperNode trains on it
unchanged:

  -BEGIN HEADER- ... Location: Latitude <lat> Longitude <lon> ... -END HEADER-
  YEAR,MO,DY,HR,WS50M                  wind: hub-height wind speed (m/s), column name kept for the loader
  YEAR,MO,DY,HR,ALLSKY_SFC_SW_DWN      solar: GHI (W/m2, hour average)

Missing and implausible hours are -999 (the loader interpolates them linearly), so the file
starts after the newest gap longer than MAX_GAP_HOURS: weeks of straight lines would teach the
model nothing true. Hours flagged by the data contract never reach the store as values. The file
stays on the plant: the SuperNode reads it, nothing sends it anywhere.
"""

import os
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Optional

from site_agent.sources import HourlySource

COLUMN = {"wind": "WS50M", "solar": "ALLSKY_SFC_SW_DWN"}
MISSING = -999
MAX_GAP_HOURS = 72


def store_path(data_dir: Path, site_id: str) -> Path:
    return Path(data_dir) / "store" / f"nasa_{site_id}.csv"


class TrainingStore:
    def __init__(self, data_dir: Path, site_id: str, lat: float, lon: float):
        self.path = store_path(data_dir, site_id)
        self.site_id, self.lat, self.lon = site_id, lat, lon
        self.hours = 0                    # good hours in the file (reported in the heartbeat)
        self._signature = None

    def update(self, source: HourlySource) -> bool:
        """Rewrite the file when the source's data changed; returns True when written."""
        good = {h: v for h, v in source.values.items() if source._ok(v)}
        if not good:
            return False
        hours = sorted(good)
        first, last = hours[0], hours[-1]
        for a, b in zip(reversed(hours[:-1]), reversed(hours[1:])):
            if b - a > timedelta(hours=MAX_GAP_HOURS):
                first = b
                break
        good = {h: v for h, v in good.items() if h >= first}
        signature = (first, last, len(good), round(sum(good.values()), 3))
        if signature == self._signature and self.path.is_file():
            return False
        column = COLUMN[source.energy_type]
        lines = [
            "-BEGIN HEADER-",
            f"ArqauQuat site store for {self.site_id}: hourly UTC, written by the site agent",
            f"Dates (UTC): {first:%Y-%m-%d %H:00} through {last:%Y-%m-%d %H:00}",
            f"Location: Latitude  {self.lat:.4f}   Longitude {self.lon:.4f}",
            f"The value for missing or implausible hours: {MISSING}",
            "Parameter(s):",
            f"{column}  {'wind speed at hub height (m/s)' if source.energy_type == 'wind' else 'global horizontal irradiance (W/m^2)'}",
            "-END HEADER-",
            f"YEAR,MO,DY,HR,{column}",
        ]
        h = first
        while h <= last:
            v = good.get(h)
            lines.append(f"{h.year},{h.month},{h.day},{h.hour},{MISSING if v is None else round(v, 3)}")
            h += timedelta(hours=1)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".store.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            os.chmod(tmp, 0o644)
            os.replace(tmp, self.path)     # the SuperNode never sees a half-written file
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        self.hours, self._signature = len(good), signature
        return True

    def span_days(self) -> Optional[float]:
        return None if not self._signature else (self._signature[1] - self._signature[0]).total_seconds() / 86400
