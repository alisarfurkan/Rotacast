"""GRACE / GRACE-FO terrestrial water storage anomaly (source_id ``grace_csr_mascon``).

Product: UT Austin CSR GRACE/GRACE-FO RL06.3 mascon solution, 0.25 deg grid, ``lwe_thickness`` (cm
liquid water equivalent). The "all-corrections" file already has GIA removal, geocenter, C20 and C30
replacement applied; CSR mascons need no further gain/scale factors. We apply the CSR RL06 land mask and
cos(lat) area weighting. Anomalies are relative to the product's own baseline mean.

https://download.csr.utexas.edu/outgoing/grace/RL0603_mascons/  (no login). Citation: Save, Bettadpur,
Tapley (2016), doi:10.15781/cgq9-nh24. The ~110 MB netCDF is NOT committed; a small CSV extract for
the Konya bbox is (data/cache/grace_csr_mascon/konya_tws.csv). Override the netCDF location with
``ROTACAST_GRACE_NC`` / ``ROTACAST_GRACE_MASK``; otherwise it is looked up in the cache dir (and
downloaded via :func:`download_grace` when online).
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from .cache import CACHE_DIR, CacheMiss, is_offline

SOURCE_ID = "grace_csr_mascon"
GRACE_DIR = CACHE_DIR / SOURCE_ID
BASE_URL = "https://download.csr.utexas.edu/outgoing/grace/RL0603_mascons/"
NC_NAME = "CSR_GRACE_GRACE-FO_RL0603_Mascons_all-corrections.nc"
MASK_NAME = "CSR_GRACE_GRACE-FO_RL06_Mascons_v02_LandMask.nc"
KONYA_BBOX = (32.0, 37.0, 34.5, 38.8)


def _csv_path(bbox: tuple[float, float, float, float]) -> Path:
    if tuple(round(v, 3) for v in bbox) == KONYA_BBOX:
        return GRACE_DIR / "konya_tws.csv"
    return GRACE_DIR / ("tws_" + "_".join(f"{v:g}" for v in bbox) + ".csv")


def download_grace() -> None:
    """Download the netCDF + land mask into the cache dir (large; online only)."""
    import httpx
    GRACE_DIR.mkdir(parents=True, exist_ok=True)
    for name in (NC_NAME, MASK_NAME):
        dest = GRACE_DIR / name
        if dest.exists():
            continue
        part = dest.with_suffix(".part")
        with httpx.stream("GET", BASE_URL + name, follow_redirects=True, timeout=600) as r:
            r.raise_for_status()
            with open(part, "wb") as fh:
                for chunk in r.iter_bytes(1 << 20):
                    fh.write(chunk)
        part.replace(dest)


def _nc_paths() -> tuple[Path, Path]:
    nc = Path(os.environ.get("ROTACAST_GRACE_NC", GRACE_DIR / NC_NAME))
    mask = Path(os.environ.get("ROTACAST_GRACE_MASK", GRACE_DIR / MASK_NAME))
    return nc, mask


def compute_bbox_series(nc_path: Path, mask_path: Path | None,
                        bbox: tuple[float, float, float, float]) -> pd.Series:
    """Area-weighted (cos lat), land-masked mean of lwe_thickness over bbox -> monthly Series (cm)."""
    import xarray as xr
    min_lon, min_lat, max_lon, max_lat = bbox
    with xr.open_dataset(nc_path) as ds:
        lon360 = ds["lon"].values % 360
        lats = ds["lat"].values
        lat_sel = np.where((lats >= min_lat) & (lats <= max_lat))[0]
        lon_sel = np.where((lon360 >= min_lon % 360) & (lon360 <= max_lon % 360))[0]
        if lat_sel.size == 0 or lon_sel.size == 0:
            raise ValueError(f"bbox {bbox} contains no grid cell")
        sub = ds["lwe_thickness"].isel(lat=lat_sel, lon=lon_sel).values.astype(float)  # (t, y, x)
        t_days = ds["time"].values.astype(float)
        land = np.ones(sub.shape[1:])
        if mask_path is not None and Path(mask_path).exists():
            with xr.open_dataset(mask_path) as m:
                land = m["LO_val"].isel(lat=lat_sel, lon=lon_sel).values.astype(float)
    base_w = np.cos(np.radians(lats[lat_sel]))[:, None] * np.ones(lon_sel.size)[None, :]
    w = base_w * (land > 0.5)
    if w.sum() == 0:
        w = base_w
    valid = np.isfinite(sub) & (np.abs(sub) < 1e4)
    num = (np.where(valid, sub, 0.0) * w).sum(axis=(1, 2))
    den = (valid * w).sum(axis=(1, 2))
    vals = np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)
    times = pd.Timestamp("2002-01-01") + pd.to_timedelta(t_days, unit="D")
    s = pd.Series(vals, index=times.to_period("M").to_timestamp()).dropna()
    s = s.groupby(level=0).mean()
    s.index.name = "date"
    s.name = "tws_cm"
    return s


def fetch_tws(bbox: tuple[float, float, float, float]) -> pd.Series:
    """Monthly TWS anomaly (cm equivalent water height) averaged over bbox (min_lon, min_lat,
    max_lon, max_lat). Index: month start. attrs: {"source_id": "grace_csr_mascon"}.

    Resolution order: committed CSV extract for this bbox -> compute from local netCDF (and write the
    CSV) -> download netCDF (if online) -> raise CacheMiss with instructions.
    """
    csv = _csv_path(bbox)
    if csv.exists():
        s = pd.read_csv(csv, parse_dates=["date"], index_col="date")["tws_cm"]
    else:
        nc, mask = _nc_paths()
        if not nc.exists():
            if is_offline():
                raise CacheMiss(f"{SOURCE_ID}: no cached series for {bbox}; place {NC_NAME} in {GRACE_DIR}")
            download_grace()
            nc, mask = _nc_paths()
        s = compute_bbox_series(nc, mask, bbox)
        csv.parent.mkdir(parents=True, exist_ok=True)
        s.to_csv(csv, header=["tws_cm"], float_format="%.4f")
    s.index.name = "date"
    s.name = "tws_cm"
    s.attrs["source_id"] = SOURCE_ID
    return s
