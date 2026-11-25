"""
REAL source: hourly exports the plant drops into /data/inbox (data contract in the kit's
data/README.md). Columns used: timestamp_utc, wind_speed_ms (wind) or ghi_wm2 (solar), curtailed.
Later files win for the same hour. Rows with bad timestamps are skipped; unreadable values are
flagged; curtailed hours keep their weather value and are counted separately.
"""

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path

from site_agent.sources import HourlySource

COLUMN = {"wind": "wind_speed_ms", "solar": "ghi_wm2"}

log = logging.getLogger("fedwind.agent.csv")


class CsvInboxSource(HourlySource):
    def __init__(self, env: dict):
        super().__init__(env["ENERGY_TYPE"])
        self.inbox = Path(env.get("DATA_DIR", "/data")) / "inbox"
        self._seen = {}

    def refresh(self) -> None:
        files = sorted(self.inbox.glob("*.csv"), key=lambda p: p.stat().st_mtime) if self.inbox.is_dir() else []
        state = {str(p): p.stat().st_mtime for p in files}
        if state == self._seen:
            return
        values, curtailed = {}, {}
        for path in files:
            try:
                self._read(path, values, curtailed)
            except (OSError, csv.Error, KeyError) as e:
                log.warning("skipping %s: %s", path.name, e)
        self.values, self.curtailed, self._seen = values, curtailed, state

    def _read(self, path: Path, values: dict, curtailed: dict) -> None:
        col = COLUMN[self.energy_type]
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if "timestamp_utc" not in (reader.fieldnames or []) or col not in reader.fieldnames:
                raise KeyError(f"needs columns timestamp_utc and {col}")
            for row in reader:
                try:
                    t = datetime.fromisoformat(row["timestamp_utc"].strip().replace("Z", "+00:00"))
                except ValueError:
                    continue
                hour = (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
                hour = hour.replace(minute=0, second=0, microsecond=0)
                cut = str(row.get("curtailed", "0")).strip() in ("1", "true", "True")
                try:
                    v = float(row[col])
                except (TypeError, ValueError):
                    v = None
                values[hour] = v          # None (unreadable) counts as flagged
                curtailed[hour] = cut
