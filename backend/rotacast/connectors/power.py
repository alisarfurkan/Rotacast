"""NASA POWER daily point connector (source_id ``nasa_power``). No auth.

https://power.larc.nasa.gov/api/temporal/daily/point  (community AG).
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from .cache import cached_get_json

SOURCE_ID = "nasa_power"
URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAM_MAP = {
    "T2M_MAX": "tmax",              # degC
    "T2M_MIN": "tmin",              # degC
    "T2M": "tmean",                 # degC
    "PRECTOTCORR": "precip",        # mm/day
    "RH2M": "rh",                   # %
    "WS2M": "wind2m",               # m/s at 2 m
    "ALLSKY_SFC_SW_DWN": "rs",      # MJ m-2 day-1
    "GWETROOT": "gwetroot",         # 0-1 root-zone soil wetness
    "GWETTOP": "gwettop",           # 0-1 surface soil wetness
}
FILL = -999.0
CHUNK_YEARS = 10  # a 10-year request (~3650 days x 9 params) was verified to work


def _chunks(start: date, end: date) -> list[tuple[date, date]]:
    out, y = [], start.year
    while y <= end.year:
        s = max(start, date(y, 1, 1))
        e = min(end, date(y + CHUNK_YEARS - 1, 12, 31))
        out.append((s, e))
        y += CHUNK_YEARS
    return out


def parse_response(payload: dict) -> tuple[pd.DataFrame, float | None]:
    """Convert a POWER JSON payload to a DataFrame (+ elevation in m). -999 becomes NaN."""
    params = payload["properties"]["parameter"]
    df = pd.DataFrame({PARAM_MAP[k]: pd.Series(v) for k, v in params.items() if k in PARAM_MAP})
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df.index.name = "date"
    df = df.astype(float).where(lambda d: d != FILL, np.nan).sort_index()
    coords = payload.get("geometry", {}).get("coordinates", [])
    elev = float(coords[2]) if len(coords) > 2 else None
    return df, elev


def fetch_daily(lat: float, lon: float, start: date, end: date) -> pd.DataFrame:
    """Daily weather for a point. Columns tmax,tmin,tmean (degC), precip (mm/d), rh (%),
    wind2m (m/s), rs (MJ/m2/d), gwetroot, gwettop (0-1). Source: NASA POWER (AG community)."""
    frames, elev = [], None
    for s, e in _chunks(start, end):
        payload = cached_get_json(SOURCE_ID, URL, {
            "parameters": ",".join(PARAM_MAP), "community": "AG",
            "longitude": lon, "latitude": lat,
            "start": s.strftime("%Y%m%d"), "end": e.strftime("%Y%m%d"), "format": "JSON",
        }, timeout=180)
        df, el = parse_response(payload)
        frames.append(df)
        elev = el if el is not None else elev
    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated()]
    df = df.loc[pd.Timestamp(start):pd.Timestamp(end)]
    df = df.reindex(pd.date_range(df.index.min(), df.index.max(), freq="D", name="date"))
    df.attrs.update({"lat": lat, "lon": lon, "elevation_m": elev, "source_id": SOURCE_ID})
    return df
