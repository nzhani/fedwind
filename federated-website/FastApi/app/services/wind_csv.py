"""
Validation for uploaded per-site wind CSVs (plan T4.2).

Accepts the NASA POWER hourly export (metadata block ending in
"-END HEADER-", then a header row) or a plain CSV whose first row is the
header.  Mirrors what preprocess_nasa_data() in the Flower app can parse.
"""

import csv
import io
from typing import List

REQUIRED_COLUMNS = ["YEAR", "MO", "DY", "HR", "WS50M"]
MIN_ROWS = 24 * 30  # a month of hourly data; less can't fill train/val/test windows


class CsvValidationError(ValueError):
    pass


def validate_wind_csv(content: bytes, min_rows: int = MIN_ROWS) -> int:
    """Check columns and size; returns the number of data rows."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("utf-16")
        except UnicodeError as e:
            raise CsvValidationError("File is not UTF-8 or UTF-16 text") from e

    lines = text.splitlines()
    start = 0
    for i, line in enumerate(lines):
        if "-END HEADER-" in line:
            start = i + 1
            break
    body = [l for l in lines[start:] if l.strip()]
    if not body:
        raise CsvValidationError("File has no header row")

    reader = csv.reader(io.StringIO("\n".join(body)))
    header: List[str] = [c.strip().upper() for c in next(reader)]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise CsvValidationError(f"Missing columns: {', '.join(missing)} (found: {', '.join(header)})")

    ws_idx = header.index("WS50M")
    rows = 0
    for row in reader:
        if len(row) <= ws_idx:
            raise CsvValidationError(f"Row {rows + 2} has too few values")
        rows += 1
    if rows < min_rows:
        raise CsvValidationError(f"Only {rows} data rows; at least {min_rows} hourly rows are needed")
    return rows
