"""MODIS NDVI / land cover via the ORNL DAAC MODIS web service (no auth).

https://modis.ornl.gov/rst/api/v1/  -- products MOD13Q1 (NDVI, 250 m, 16-day) and MCD12Q1 (IGBP land cover).
source_id for NDVI: ``modis_mod13q1``; land cover uses ``modis_mcd12q1``.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date

import numpy as np
import pandas as pd

from .cache import cached_get_json

SOURCE_ID = "modis_mod13q1"
LC_SOURCE_ID = "modis_mcd12q1"
BASE = "https://modis.ornl.gov/rst/api/v1"
CHUNK_DATES = 10   # service limit per subset request
MAX_WORKERS = 3    # polite concurrency (<= 4)
NDVI_BAND = "250m_16_days_NDVI"
REL_BAND = "250m_16_days_pixel_reliability"
NDVI_SCALE = 0.0001
NDVI_FILL = -3000


def list_dates(product: str, lat: float, lon: float) -> list[dict]:
    """All composite dates ({'modis_date','calendar_date'}) available at a point."""
    return cached_get_json(f"modis_dates_{product.lower()}", f"{BASE}/{product}/dates",
                           {"latitude": lat, "longitude": lon})["dates"]


def _subset(product: str, source_id: str, lat: float, lon: float, band: str,
            first: str, last: str) -> list[dict]:
    payload = cached_get_json(source_id, f"{BASE}/{product}/subset", {
        "latitude": lat, "longitude": lon, "band": band,
        "startDate": first, "endDate": last, "kmAboveBelow": 0, "kmLeftRight": 0})
    return payload.get("subset", [])


def parse_subset(rows: list[dict]) -> pd.Series:
    """Subset rows -> Series indexed by calendar_date (first pixel value of each row)."""
    return pd.Series({pd.Timestamp(r["calendar_date"]): r["data"][0] for r in rows}, dtype=float)


def build_ndvi_frame(ndvi_rows: list[dict], rel_rows: list[dict]) -> pd.DataFrame:
    """Combine NDVI + reliability subset rows into the contract DataFrame."""
    ndvi = parse_subset(ndvi_rows).replace(NDVI_FILL, np.nan) * NDVI_SCALE
    rel = parse_subset(rel_rows)
    df = pd.DataFrame({"ndvi": ndvi, "reliability": rel}).sort_index()
    df.loc[~df["ndvi"].between(-0.2, 1.0), "ndvi"] = np.nan
    # reliability fill (-1) or missing -> treat as cloudy (3) so downstream filters drop it
    df["reliability"] = df["reliability"].where(df["reliability"].between(0, 3), 3).fillna(3).astype(int)
    df.index.name = "date"
    return df


def fetch_ndvi(lat: float, lon: float, start: date, end: date) -> pd.DataFrame:
    """MOD13Q1 16-day NDVI at one 250 m pixel. Columns: ndvi (-0.2..1, scaled), reliability
    (0 good, 1 marginal, 2 snow/ice, 3 cloudy). Index: composite calendar date."""
    dates = [d for d in list_dates("MOD13Q1", lat, lon)
             if start <= date.fromisoformat(d["calendar_date"]) <= end]
    chunks = [dates[i:i + CHUNK_DATES] for i in range(0, len(dates), CHUNK_DATES)]
    jobs = [(c[0]["modis_date"], c[-1]["modis_date"], band)
            for c in chunks for band in (NDVI_BAND, REL_BAND)]

    def run(job: tuple[str, str, str]) -> list[dict]:
        return _subset("MOD13Q1", SOURCE_ID, lat, lon, job[2], job[0], job[1])

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        results = list(ex.map(run, jobs))
    ndvi_rows = [r for res, j in zip(results, jobs) if j[2] == NDVI_BAND for r in res]
    rel_rows = [r for res, j in zip(results, jobs) if j[2] == REL_BAND for r in res]
    df = build_ndvi_frame(ndvi_rows, rel_rows)
    df.attrs.update({"lat": lat, "lon": lon, "source_id": SOURCE_ID})
    return df


def fetch_landcover(lat: float, lon: float, year: int) -> int:
    """MCD12Q1 LC_Type1 (IGBP) class at the pixel for ``year`` (clamped to the available years).
    12 = croplands, 14 = cropland/natural vegetation mosaic."""
    avail = [int(d["calendar_date"][:4]) for d in list_dates("MCD12Q1", lat, lon)]
    y = min(max(year, min(avail)), max(avail))
    md = f"A{y}001"
    rows = _subset("MCD12Q1", LC_SOURCE_ID, lat, lon, "LC_Type1", md, md)
    if not rows:
        raise ValueError(f"No MCD12Q1 land-cover data for {lat},{lon} {y}")
    return int(rows[0]["data"][0])
