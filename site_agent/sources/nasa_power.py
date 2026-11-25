"""
SIMULATION source: NASA POWER hourly weather at the plant's coordinates stands in for its SCADA.

  wind   WS50M               wind speed at 50 m (m/s)
  solar  ALLSKY_SFC_SW_DWN   GHI (W/m2, hour average)

Fetches the last LOOKBACK_DAYS days (UTC), caches them in /data/store/nasa_power.json and refreshes
every REFRESH_HOURS. For training (the SuperNode reads the store, store.py), SIM_HISTORY_YEARS
past calendar years plus the current year so far are fetched, one request per year, and kept in
/data/store/nasa_history_<year>.json: past years once (they never change), the current year
again after a week. NASA's newest hours lag: about 3 days for wind speed, about 3 months for hourly
irradiance (satellite processing), hence the longer solar lookback. "now" for the simulated plant is the newest
hour NASA has. If NASA can't be reached, the cache keeps the plant going.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from site_agent.sources import HourlySource

API = "https://power.larc.nasa.gov/api/temporal/hourly/point"
PARAMETER = {"wind": "WS50M", "solar": "ALLSKY_SFC_SW_DWN"}
LOOKBACK_DAYS = {"wind": 40, "solar": 150}
REFRESH_HOURS = 6
HISTORY_REFRESH = timedelta(days=7)

log = logging.getLogger("fedwind.agent.nasa")


class NasaPowerSource(HourlySource):
    def __init__(self, env: dict, session=None):
        super().__init__(env["ENERGY_TYPE"])
        self.lat, self.lon = float(env["LAT"]), float(env["LON"])
        self.cache = Path(env.get("DATA_DIR", "/data")) / "store" / "nasa_power.json"
        self.http = session or requests.Session()
        self.fetched_at = None
        self.history_years = max(0, int(env.get("SIM_HISTORY_YEARS", "0") or 0))
        self._history: dict = {}

    def refresh(self) -> None:
        now = datetime.now(timezone.utc)
        if self.fetched_at and now - self.fetched_at < timedelta(hours=REFRESH_HOURS):
            return
        cached = self._read_cache()
        if cached and now - cached[0] < timedelta(hours=REFRESH_HOURS):
            self.fetched_at, raw = cached
        else:
            try:
                raw = self._download(now)
                self._write_cache(now, raw)
                self.fetched_at = now
            except (requests.RequestException, KeyError, ValueError) as e:
                if not cached:
                    raise
                log.warning("NASA POWER unreachable (%s); using the cache from %s", e, cached[0].isoformat())
                self.fetched_at, raw = cached
        self.values = {**self._load_history(now), **parse(raw)}

    def _load_history(self, now: datetime) -> dict:
        """Whole past years for training; fetched once each, then read from disk. A year NASA
        can't deliver now is retried at the next refresh; the plant keeps reporting meanwhile."""
        if not self.history_years:
            return {}
        for year in range(now.year - self.history_years, now.year + 1):
            current = year == now.year
            if year in self._history and not current:
                continue
            path = self.cache.parent / f"nasa_history_{year}.json"
            raw = None
            try:
                cached = json.loads(path.read_text())
                if not current or now - datetime.fromisoformat(cached["fetched_at"]) < HISTORY_REFRESH:
                    raw = cached["values"]
            except (OSError, ValueError, KeyError):
                pass
            if raw is None:
                try:
                    end = now.strftime("%Y%m%d") if current else f"{year}1231"
                    raw = self._download_range(f"{year}0101", end)
                except (requests.RequestException, KeyError, ValueError) as e:
                    log.warning("NASA POWER history %d not available now (%s)", year, e)
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"year": year, "fetched_at": now.isoformat(), "lat": self.lat,
                                            "lon": self.lon, "values": raw}))
                log.info("training history %d: %d hours", year, len(raw))
            self._history[year] = parse(raw)
        merged = {}
        for year in sorted(self._history):
            merged.update(self._history[year])
        return merged

    def _download(self, now: datetime) -> dict:
        start = (now - timedelta(days=LOOKBACK_DAYS[self.energy_type])).strftime("%Y%m%d")
        return self._download_range(start, now.strftime("%Y%m%d"))

    def _download_range(self, start: str, end: str) -> dict:
        r = self.http.get(API, timeout=300, params={
            "parameters": PARAMETER[self.energy_type], "community": "RE", "latitude": self.lat,
            "longitude": self.lon, "start": start, "end": end,
            "format": "JSON", "time-standard": "UTC"})
        r.raise_for_status()
        return r.json()["properties"]["parameter"][PARAMETER[self.energy_type]]

    def _read_cache(self):
        try:
            c = json.loads(self.cache.read_text())
            return datetime.fromisoformat(c["fetched_at"]), c["values"]
        except (OSError, ValueError, KeyError):
            return None

    def _write_cache(self, when: datetime, raw: dict) -> None:
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        self.cache.write_text(json.dumps({"fetched_at": when.isoformat(), "lat": self.lat, "lon": self.lon,
                                          "values": raw}))


def parse(raw: dict) -> dict:
    """{"YYYYMMDDHH": value} -> {datetime UTC: value}; NASA's -999 (not yet available) becomes a gap."""
    out = {}
    for k, v in raw.items():
        if v is None or float(v) <= -998:
            continue
        out[datetime.strptime(k, "%Y%m%d%H").replace(tzinfo=timezone.utc)] = float(v)
    return out
