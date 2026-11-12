"""Satellite precipitation (CHIRPS v2.0 0.05 deg; fallback NASA GPM IMERG 0.1 deg) via NASA SERVIR ClimateSERV.

No login. API (base ``https://climateserv.servirglobal.net/chirps``; the ``/api`` alias is flaky):
``submitDataRequest`` (GET: datatype, begintime/endtime ``MM/DD/YYYY``, intervaltype=0 daily, operationtype=5 average,
geometry=GeoJSON polygon) -> ``["<uuid>"]``; ``getDataRequestProgress?id=`` -> ``[100.0]`` when done;
``getDataFromRequest?id=`` -> ``{"data": [{"date": "MM/DD/YYYY", "raw_value": mm/day, ...}]}``.
Datatype ids: 26 = NASA IMERG (``gpm_imerg``), 0 = CHIRPS (``chirps``).

:func:`bias_correct_power` rescales NASA POWER daily rain month by month so that long-term monthly totals match the
satellite record over their overlap, while keeping POWER's day-to-day timing.
"""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import httpx
import numpy as np
import pandas as pd

from .cache import USER_AGENT, CacheMiss, _atomic_write, cache_path, is_offline

BASE = "https://climateserv.servirglobal.net/chirps"
DATASETS = {  # source_id -> (ClimateSERV datatype, first usable year)
    "gpm_imerg": (26, 2001),
    "chirps": (0, 1981),
}
PREFERENCE = ("chirps", "gpm_imerg")  # CHIRPS is gauge-blended: IMERG gave spurious 100-230 mm days on the Konya plain
HALF_WIDTH_DEG = 0.05      # polygon is a 0.1 deg box around the point
CHUNK_YEARS = 1
WORKERS = 3
MIN_OVERLAP_YEARS = 8
FACTOR_MIN, FACTOR_MAX = 0.3, 1.5
CONNECT_TIMEOUT = 6.0


def _call(path: str, params: dict, tries: int = 4):
    """GET one ClimateSERV endpoint with retries (the server drops some connections)."""
    last: Exception | None = None
    for attempt in range(tries):
        try:
            with httpx.Client(timeout=httpx.Timeout(20.0, connect=CONNECT_TIMEOUT), headers={"User-Agent": USER_AGENT}) as c:
                r = c.get(f"{BASE}/{path}/", params=params)
            if r.status_code == 200:
                return r.json()
            last = RuntimeError(f"HTTP {r.status_code} from {path}")
        except (httpx.HTTPError, ValueError) as exc:
            last = exc
        time.sleep(min(1.0 * (attempt + 1), 5.0))
    raise RuntimeError(f"ClimateSERV {path} failed after {tries} tries: {last}")


def _polygon(lat: float, lon: float) -> str:
    h = HALF_WIDTH_DEG
    ring = [[lon - h, lat - h], [lon + h, lat - h], [lon + h, lat + h], [lon - h, lat + h], [lon - h, lat - h]]
    return json.dumps({"type": "Polygon", "coordinates": [[[round(x, 4), round(y, 4)] for x, y in ring]]})


def parse_response(payload: dict) -> pd.Series:
    """ClimateSERV ``getDataFromRequest`` payload -> daily mm Series (negative fill values become NaN)."""
    rows = payload["data"]
    if not rows:
        return pd.Series(dtype=float, name="precip", index=pd.DatetimeIndex([], name="date"))
    idx = pd.to_datetime([r["date"] for r in rows], format="%m/%d/%Y")
    vals = np.array([float(r["raw_value"]) for r in rows], dtype=float)
    vals[vals < 0] = np.nan
    s = pd.Series(vals, index=idx, name="precip").sort_index()
    s.index.name = "date"
    return s[~s.index.duplicated()]


def _chunk_params(source_id: str, lat: float, lon: float, s: date, e: date) -> dict:
    return {"datatype": DATASETS[source_id][0], "begintime": s.strftime("%m/%d/%Y"), "endtime": e.strftime("%m/%d/%Y"),
            "intervaltype": 0, "operationtype": 5, "geometry": _polygon(lat, lon)}


def _is_cached(source_id: str, lat: float, lon: float, s: date, e: date) -> bool:
    return cache_path(source_id, BASE + "/getDataFromRequest", _chunk_params(source_id, lat, lon, s, e)).exists()


def _fetch_chunk(source_id: str, lat: float, lon: float, s: date, e: date) -> pd.Series:
    params = _chunk_params(source_id, lat, lon, s, e)
    path = cache_path(source_id, BASE + "/getDataFromRequest", params)
    if path.exists():
        return parse_response(json.loads(path.read_text(encoding="utf-8")))
    if is_offline():
        raise CacheMiss(f"{source_id}: not cached ({params})")
    sub = dict(params, dateType_Category="default", isZip_CurrentDataType="false")
    rid = _call("submitDataRequest", sub)[0]
    deadline = time.time() + 240
    while True:
        prog = _call("getDataRequestProgress", {"id": rid})
        if prog and float(prog[0]) >= 100:
            break
        if prog and float(prog[0]) < 0 or time.time() > deadline:
            raise RuntimeError(f"ClimateSERV request {rid} failed (progress {prog})")
        time.sleep(2)
    payload = _call("getDataFromRequest", {"id": rid})
    # an empty list means the dataset has no coverage for this period yet (IMERG final lags by many months): cache it
    slim = {"data": [{"date": r["date"], "raw_value": r["raw_value"]} for r in payload.get("data") or []]}
    _atomic_write(path, json.dumps(slim).encode("utf-8"))
    return parse_response(slim)


def _try_chunk(source_id: str, lat: float, lon: float, s: date, e: date, down: threading.Event):
    if down.is_set() and not _is_cached(source_id, lat, lon, s, e):
        return RuntimeError("ClimateSERV unreachable, skipped")
    try:
        return _fetch_chunk(source_id, lat, lon, s, e)
    except Exception as exc:
        down.set()  # circuit breaker: do not hammer a server that just failed  # noqa: BLE001 - one flaky year must not sink the whole record
        return exc


def _fetch_source(source_id: str, lat: float, lon: float, start: date, end: date) -> pd.Series:
    y0 = max(start.year, DATASETS[source_id][1])
    spans = [(max(start, date(y, 1, 1)), min(end, date(y + CHUNK_YEARS - 1, 12, 31)))
             for y in range(y0, end.year + 1, CHUNK_YEARS)]
    down = threading.Event()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:  # the server answers ~1 min per year; ask for several at once
        results = list(ex.map(lambda se: _try_chunk(source_id, lat, lon, se[0], se[1], down), spans))
    parts = [r for r in results if isinstance(r, pd.Series)]
    if not parts:
        raise RuntimeError(f"{source_id}: all chunks failed ({results[0] if results else 'no chunks'})")
    ser = pd.concat(parts).sort_index()  # failed years are simply missing; the correction uses complete overlap months only
    return ser[~ser.index.duplicated()]


def fetch_precip_daily(lat: float, lon: float, start: date, end: date) -> pd.Series:
    """Daily satellite rain (mm/day) for a point, ``attrs['source_id']`` in {gpm_imerg, chirps}.
    Tries CHIRPS first (gauge-blended, 1981+), then GPM IMERG; raises RuntimeError if neither is usable."""
    errors = []
    for sid in PREFERENCE:
        try:
            ser = _fetch_source(sid, lat, lon, start, end)
            if ser.notna().sum() < 365 * MIN_OVERLAP_YEARS:
                raise RuntimeError(f"too few days ({int(ser.notna().sum())})")
            ser = ser.astype(float)
            ser.attrs.update({"source_id": sid, "lat": lat, "lon": lon})
            return ser
        except Exception as exc:  # noqa: BLE001 - try the next dataset
            errors.append(f"{sid}: {exc}")
    raise RuntimeError("satellite precipitation unavailable: " + "; ".join(errors))


def bias_correct_power(power_df: pd.DataFrame, sat_series: pd.Series, *, min_overlap_years: int = MIN_OVERLAP_YEARS) -> pd.DataFrame:
    """Monthly ratio correction of POWER ``precip``: per calendar month, factor = long-term monthly total of the
    satellite / that of POWER over the overlap (complete months only), clipped to [0.3, 1.5]. Applied to every POWER
    day so timing stays POWER's. Returns a copy; factors/source go to ``attrs['precip_correction']``."""
    p = power_df["precip"].astype(float)
    sat = sat_series.astype(float)
    both = pd.concat({"p": p, "s": sat}, axis=1).dropna()
    both = both[both.index.year >= 1]  # keep as is; filtered below by complete months
    ym = both.index.to_period("M")
    dim = both["p"].groupby(ym).transform("size")
    full = both[dim == both.index.days_in_month]
    if full.empty:
        raise ValueError("no overlapping complete months between POWER and satellite precipitation")
    tot = full.groupby(full.index.to_period("M")).sum()
    months = tot.index.month
    n_years = int(len(set(tot.index.year)))
    if n_years < min_overlap_years:
        raise ValueError(f"overlap too short ({n_years} years)")
    factors: dict[int, float] = {}
    for m in range(1, 13):
        sel = tot[months == m]
        ps, ss = float(sel["p"].sum()), float(sel["s"].sum())
        raw = ss / ps if ps > 0 else 1.0
        factors[m] = float(np.clip(raw, FACTOR_MIN, FACTOR_MAX))
    f = pd.Series(power_df.index.month, index=power_df.index).map(factors).astype(float)
    out = power_df.copy()
    out["precip"] = p * f
    ann_p = float(tot["p"].sum() / n_years)
    ann_s = float(tot["s"].sum() / n_years)
    out.attrs = dict(power_df.attrs)
    out.attrs["precip_correction"] = {
        "source_id": sat_series.attrs.get("source_id", "satellite"),
        "factors_by_month": {int(k): round(v, 3) for k, v in factors.items()},
        "power_mean_mm": round(ann_p, 1),
        "sat_mean_mm": round(ann_s, 1),
        "overlap_years": n_years,
    }
    return out
