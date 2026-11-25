"""
Kazakhstan outline + big lakes from Natural Earth 1:50m (public domain) -> components/fw/kz-map-data.ts.

  curl -LO https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson
  curl -LO https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_lakes.geojson
  python3 scripts/make_kz_map.py <folder with the two files> components/fw/kz-map-data.ts
"""
import json
import math
import sys
from pathlib import Path

ne, out = Path(sys.argv[1]), Path(sys.argv[2])
LON0, LAT0 = 46.0, 56.0                 # top-left of the frame (degrees)
LON1, LAT1 = 88.0, 40.0
K = math.cos(math.radians(48))          # equirectangular, true scale at 48 N
W = 1000.0
S = W / ((LON1 - LON0) * K)             # px per degree of longitude * K
H = (LAT0 - LAT1) * S


def xy(lon, lat):
    return ((lon - LON0) * K * S, (LAT0 - lat) * S)


def rdp(pts, eps):
    if len(pts) < 3:
        return pts
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = math.hypot(dx, dy) or 1e-9
    dmax, idx = 0.0, 0
    for i in range(1, len(pts) - 1):
        x, y = pts[i]
        d = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / norm
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        return rdp(pts[: idx + 1], eps)[:-1] + rdp(pts[idx:], eps)
    return [pts[0], pts[-1]]


def rings(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for poly in polys:
        yield poly[0]  # outer ring


def path(geom, eps=0.8, min_pts=4):
    parts = []
    for ring in rings(geom):
        raw = [xy(lon, lat) for lon, lat in ring]
        mid = len(raw) // 2               # closed ring: simplify two open halves
        pts = rdp(raw[: mid + 1], eps)[:-1] + rdp(raw[mid:], eps)
        if len(pts) < min_pts:
            continue
        parts.append("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + "Z")
    return "".join(parts)


countries = json.loads((ne / "ne_50m_admin_0_countries.geojson").read_text())["features"]
kz = next(f for f in countries if f["properties"]["ADM0_A3"] == "KAZ")
outline = path(kz["geometry"])

lakes = []
for f in json.loads((ne / "ne_50m_lakes.geojson").read_text())["features"]:
    name = f["properties"].get("name") or ""
    lons = [c[0] for r in rings(f["geometry"]) for c in r]
    lats = [c[1] for r in rings(f["geometry"]) for c in r]
    if not (LON0 < sum(lons) / len(lons) < LON1 and LAT1 < sum(lats) / len(lats) < LAT0):
        continue
    if name in ("Lake Balkhash", "Aral Sea", "Lake Zaysan", "Lake Alakol", "North Aral Sea") or any(k in name for k in ("Aral", "Balkhash", "Alak", "Tengiz")):
        p = path(f["geometry"], eps=0.6)
        if p:
            lakes.append(p)

ts = f"""// Generated from Natural Earth 1:50m (public domain): Kazakhstan's outline and its big lakes,
// simplified and projected (equirectangular, true scale at 48° N) into a {W:.0f} × {H:.0f} frame.
// Regenerate with scripts/make_kz_map.py; no map tiles, works offline.

export const KZ_FRAME = {{ lon0: {LON0}, lat0: {LAT0}, k: {K:.6f}, s: {S:.6f}, width: {W:.0f}, height: {H:.0f} }} as const

export const KZ_OUTLINE = "{outline}"

export const KZ_LAKES: string[] = {json.dumps(lakes)}

/** [x, y] in the frame for a latitude / longitude */
export function kzProject(lat: number, lon: number): [number, number] {{
  return [(lon - KZ_FRAME.lon0) * KZ_FRAME.k * KZ_FRAME.s, (KZ_FRAME.lat0 - lat) * KZ_FRAME.s]
}}
"""
out.write_text(ts)
print("outline chars", len(outline), "lakes", len(lakes), "frame", W, round(H), "bytes", len(ts))
