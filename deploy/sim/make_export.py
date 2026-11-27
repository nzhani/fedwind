#!/usr/bin/env python3
"""
Turn a NASA POWER hourly file into a plant's hourly export in the kit's data contract
(data/README.md: timestamp_utc, ghi_wm2 or wind_speed_ms, power_kw, available, curtailed), so a
simulated plant runs on ready data, without downloading anything.

  python3 deploy/sim/make_export.py <nasa csv> <out csv> --capacity-kw 20000
"""
import argparse
import csv
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("nasa_csv", type=Path)
p.add_argument("out_csv", type=Path)
p.add_argument("--capacity-kw", type=float, default=20000)
a = p.parse_args()

lines = a.nasa_csv.read_text(errors="ignore").splitlines()
start = next(i for i, ln in enumerate(lines) if "-END HEADER-" in ln) + 1
rows = list(csv.DictReader(lines[start:]))
solar = "ALLSKY_SFC_SW_DWN" in rows[0]
col_in, col_out = ("ALLSKY_SFC_SW_DWN", "ghi_wm2") if solar else ("WS50M", "wind_speed_ms")
a.out_csv.parent.mkdir(parents=True, exist_ok=True)
with open(a.out_csv, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["timestamp_utc", col_out, "power_kw", "available", "curtailed"])
    n = 0
    for r in rows:
        v = float(r[col_in])
        if v <= -998:
            continue
        ts = f"{int(r['YEAR']):04d}-{int(r['MO']):02d}-{int(r['DY']):02d}T{int(r['HR']):02d}:00:00Z"
        power = min(a.capacity_kw, max(0.0, a.capacity_kw * v / 1000 * 0.8)) if solar else ""
        w.writerow([ts, round(v, 2), round(power, 1) if power != "" else "", 1, 0])
        n += 1
print(f"{a.out_csv}: {n} hours ({col_out})")
