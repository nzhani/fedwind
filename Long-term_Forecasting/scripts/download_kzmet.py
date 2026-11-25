"""
Download hourly NASA POWER data for the wind and solar sites (plan T1.2, FR-01, DR-09).

Writes one CSV per site in the NASA POWER export format that
preprocess_nasa_data() parses (metadata block, then YEAR,MO,DY,HR,<params>):

  <sites-dir>/<site>/nasa_<site>.csv          per-site folder mounted by client-<site>
  <registry-dir>/nasa_<site>.csv              DATASET_REGISTRY folder (simulation mode)

Wind:  WS50M (target), WD50M, T2M, PS.
Solar: ALLSKY_SFC_SW_DWN (GHI, target), CLRSKY_SFC_SW_DWN (NASA's clear-sky GHI, kept
       for checks only), T2M. Sun position and the clear-sky model used for k* are
       computed from the coordinates in the header (my_flower_app/solar.py).

Coordinates come from deploy/seed/sites.json. Times are UTC.

Usage:
  python scripts/download_kzmet.py                       # 2015-2024, all wind sites
  python scripts/download_kzmet.py --energy solar        # 2015-2024, all solar sites
  python scripts/download_kzmet.py --start 2024 --end 2024 --sites almaty aktau
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
API = "https://power.larc.nasa.gov/api/temporal/hourly/point"
PARAMETERS = {
    "wind": "WS50M,WD50M,T2M,PS",
    "solar": "ALLSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DWN,T2M",
}
REGISTRY_DIRS = {"wind": "custom", "solar": "solar"}


def fetch_year(lat: float, lon: float, year: int, parameters: str, retries: int = 4) -> list[str]:
    query = urllib.parse.urlencode({
        "parameters": parameters,
        "community": "RE",
        "latitude": lat,
        "longitude": lon,
        "start": f"{year}0101",
        "end": f"{year}1231",
        "format": "CSV",
        "time-standard": "UTC",
    })
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(f"{API}?{query}", timeout=120) as resp:
                text = resp.read().decode("utf-8")
            if "-END HEADER-" not in text:
                raise ValueError(f"unexpected response: {text[:200]}")
            return text.splitlines()
        except (urllib.error.URLError, ValueError, TimeoutError) as e:
            wait = 5 * (attempt + 1)
            print(f"  {year}: {e}; retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"NASA POWER request failed for {lat},{lon} {year}")


def download_site(lat: float, lon: float, start: int, end: int, parameters: str) -> str:
    """One CSV for all years: the first year's header block, then every year's rows."""
    header: list[str] = []
    rows: list[str] = []
    for year in range(start, end + 1):
        lines = fetch_year(lat, lon, year, parameters)
        split = lines.index("-END HEADER-") + 1
        if not header:
            header = lines[: split + 1]  # metadata + column row
            header[2] = f"Dates (year): {start} through {end} in UTC"
        rows.extend(lines[split + 1:])
        print(f"  {year}: {len(lines) - split - 1} rows")
    return "\n".join(header + rows) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", type=int, default=2015)
    parser.add_argument("--end", type=int, default=2024)
    parser.add_argument("--energy", choices=sorted(PARAMETERS), default="wind")
    parser.add_argument("--sites", nargs="*", help="site ids (default: every active site of --energy)")
    parser.add_argument("--seed", type=Path, default=REPO / "deploy" / "seed" / "sites.json")
    parser.add_argument("--sites-dir", type=Path, default=REPO / "deploy" / "data" / "sites")
    parser.add_argument("--registry-dir", default=None,
                        help="also copy here for simulation mode (default datasets/custom for wind, "
                             "datasets/solar for solar); pass '' to skip")
    args = parser.parse_args()
    # Path("") would be the current directory, so '' must stay a plain "skip"
    if args.registry_dir is None:
        args.registry_dir = REPO / "Long-term_Forecasting" / "datasets" / REGISTRY_DIRS[args.energy]
    elif args.registry_dir == "":
        args.registry_dir = None
    else:
        args.registry_dir = Path(args.registry_dir)

    sites = [s for s in json.loads(args.seed.read_text())["sites"]
             if s["energy_type"] == args.energy and s["status"] == "active"]
    if args.sites:
        sites = [s for s in sites if s["id"] in args.sites]

    for site in sites:
        print(f"{site['id']} ({site['lat']}, {site['lon']}) {args.start}-{args.end}")
        csv = download_site(site["lat"], site["lon"], args.start, args.end, PARAMETERS[args.energy])
        name = f"nasa_{site['id']}.csv"
        target = args.sites_dir / site["id"] / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(csv)
        print(f"  -> {target}")
        if args.registry_dir is not None:
            args.registry_dir.mkdir(parents=True, exist_ok=True)
            (args.registry_dir / name).write_text(csv)


if __name__ == "__main__":
    main()
