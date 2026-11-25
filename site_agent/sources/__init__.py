"""
Where a site's hourly data comes from. Every source keeps an hourly UTC series of the forecast
variable (wind speed in m/s, or GHI in W/m2) and answers the same questions:

  refresh()        pick up new data
  today()          Stats(last_hour, rows, gaps) for the newest data day
  day(d)           DayQuality(rows, gaps, flagged, curtailed) for one UTC day
  window(hours)    (end_hour, values) of the newest `hours` hours, None where missing (central forecasting)
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

# Plausible ranges per energy type: values outside are "flagged" and not used
RANGES = {"wind": (0.0, 40.0), "solar": (0.0, 1400.0)}


@dataclass
class Stats:
    last_hour: Optional[datetime]
    rows: int
    gaps: int


@dataclass
class DayQuality:
    rows: int
    gaps: int
    flagged: int
    curtailed: int


class HourlySource:
    """Shared bookkeeping; subclasses fill self.values {hour: value or None} and self.curtailed."""

    def __init__(self, energy_type: str):
        if energy_type not in RANGES:
            raise ValueError(f"ENERGY_TYPE must be wind or solar, got {energy_type!r}")
        self.energy_type = energy_type
        self.values: Dict[datetime, Optional[float]] = {}
        self.curtailed: Dict[datetime, bool] = {}

    def refresh(self) -> None:
        raise NotImplementedError

    def _ok(self, v: Optional[float]) -> bool:
        lo, hi = RANGES[self.energy_type]
        return v is not None and lo <= v <= hi

    def last_hour(self) -> Optional[datetime]:
        good = [h for h, v in self.values.items() if self._ok(v)]
        return max(good) if good else None

    def today(self) -> Stats:
        last = self.last_hour()
        if last is None:
            return Stats(None, 0, 0)
        start = last.replace(hour=0, minute=0, second=0, microsecond=0)
        hours = [start + timedelta(hours=i) for i in range(last.hour + 1)]
        rows = sum(1 for h in hours if self._ok(self.values.get(h)))
        return Stats(last, rows, len(hours) - rows)

    def day(self, d: date) -> DayQuality:
        """gaps: hours with no data at all; flagged: data present but implausible; curtailed: counted
        separately (curtailment changes power, not the weather variable we forecast)."""
        start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        hours = [start + timedelta(hours=i) for i in range(24)]
        present = [h for h in hours if h in self.values]
        good = [h for h in present if self._ok(self.values[h])]
        return DayQuality(rows=len(good), gaps=24 - len(present), flagged=len(present) - len(good),
                          curtailed=sum(1 for h in hours if self.curtailed.get(h)))

    def window(self, hours: int) -> Tuple[Optional[datetime], List[Optional[float]]]:
        last = self.last_hour()
        if last is None:
            return None, []
        span = [last - timedelta(hours=hours - 1 - i) for i in range(hours)]
        return last, [self.values.get(h) if self._ok(self.values.get(h)) else None for h in span]


def make_source(name: str, env: dict) -> HourlySource:
    if name == "nasa_power":
        from site_agent.sources.nasa_power import NasaPowerSource

        return NasaPowerSource(env)
    if name == "csv_inbox":
        from site_agent.sources.csv_inbox import CsvInboxSource

        return CsvInboxSource(env)
    raise ValueError(f"Unknown DATA_SOURCE {name!r} (csv_inbox or nasa_power)")
