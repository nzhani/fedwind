#!/usr/bin/env python3
import csv
import os
from pathlib import Path

import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent / "datasets"
NASA_DIR = BASE_DIR / "custom"
VNMET_DIR = BASE_DIR / "VNMET"
OUTPUT_DIR = Path(__file__).resolve().parent / "fairness_analysis"
OUTPUT_PATH = OUTPUT_DIR / "client_stats.csv"

NASA_TARGET = "WS50M"
VNMET_TARGET = "Vavg80 [m/s]"

NASA_FILES = {
    "Aktau": "nasa_aktau.csv",
    "Almaty": "nasa_almaty.csv",
    "Astana": "nasa_astana.csv",
    "Taraz": "nasa_taraz.csv",
    "Zhezkazgan": "nasa_zhezkazgan.csv",
}

VNMET_FILES = {
    "Station 001": "001.csv",
    "Station 002": "002.csv",
    "Station 003": "003.csv",
    "Station 004": "004.csv",
    "Station 005": "005.csv",
}


def load_nasa_series(path: Path) -> pd.Series | None:
    if not path.exists():
        return None
    try:
        with path.open("r", errors="ignore") as f:
            lines = f.readlines()
        data_start_idx = None
        for i, line in enumerate(lines):
            if "-END HEADER-" in line:
                data_start_idx = i + 1
                break
        if data_start_idx is None:
            return None
        df = pd.read_csv(
            path,
            skiprows=data_start_idx,
            sep=r"[,\t\s]+",
            engine="python",
        )
        df.columns = [c.strip().upper().replace("\ufeff", "") for c in df.columns]
        if NASA_TARGET not in df.columns:
            return None
        series = df[NASA_TARGET].replace(-999, np.nan).dropna()
        return series
    except Exception:
        return None


def load_vnmet_series(path: Path) -> pd.Series | None:
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path)
        if VNMET_TARGET not in df.columns:
            return None
        series = pd.to_numeric(df[VNMET_TARGET], errors="coerce").dropna()
        return series
    except Exception:
        return None


def compute_stats(series: pd.Series) -> dict:
    mean = float(series.mean())
    std = float(series.std())
    cv = std / mean if mean != 0 else float("inf")
    return {
        "mean": mean,
        "std": std,
        "cv": cv,
        "n": int(series.shape[0]),
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []

    for client, filename in NASA_FILES.items():
        series = load_nasa_series(NASA_DIR / filename)
        if series is None or series.empty:
            continue
        stats = compute_stats(series)
        rows.append({
            "dataset": "NASA",
            "client": client,
            **stats,
        })

    for client, filename in VNMET_FILES.items():
        series = load_vnmet_series(VNMET_DIR / filename)
        if series is None or series.empty:
            continue
        stats = compute_stats(series)
        rows.append({
            "dataset": "VNMET",
            "client": client,
            **stats,
        })

    if not rows:
        print("No data found. Nothing to save.")
        return 1

    df = pd.DataFrame(rows, columns=["dataset", "client", "mean", "std", "cv", "n"])
    df.to_csv(OUTPUT_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
    print(f"Saved: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
