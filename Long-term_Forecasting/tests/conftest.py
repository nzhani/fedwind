import os
import sys
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parents[1]
# utils/ and my_flower_app/ import the same way as in the containers (PYTHONPATH)
for p in (ML_ROOT, ML_ROOT / "flower_app"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
os.environ.setdefault("FEDWIND_ML_ROOT", str(ML_ROOT))


def write_nasa_csv(path: Path, hours: int = 24 * 60, start_year: int = 2024) -> Path:
    """Small NASA POWER-format file: metadata block, header, hourly rows."""
    import math

    lines = ["-BEGIN HEADER-", "NASA/POWER test file", "-END HEADER-", "YEAR,MO,DY,HR,WS50M,T2M"]
    for h in range(hours):
        day, hour = divmod(h, 24)
        month, dom = divmod(day, 28)
        lines.append(f"{start_year},{month + 1},{dom + 1},{hour},{6 + 3 * math.sin(h / 12):.3f},{-5 + h % 10}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path
