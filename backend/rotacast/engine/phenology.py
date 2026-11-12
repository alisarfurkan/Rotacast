"""Field memory: phenology, bare-soil windows and stress years from MODIS MOD13Q1 NDVI.

References
----------
Savitzky, A., Golay, M.J.E. (1964) Anal. Chem. 36:1627-1639.
Jonsson, P., Eklundh, L. (2004) TIMESAT - a program for analyzing time-series of satellite sensor data.
Computers & Geosciences 30:833-845 (amplitude-threshold green-up / senescence definition).
Didan, K. (2021) MOD13Q1 v061, NASA LP DAAC (16-day composites, reliability flags).
"""
from __future__ import annotations

import datetime as dt
import math

import numpy as np
import pandas as pd
from scipy.signal import find_peaks, savgol_filter

# ---------------------------------------------------------------------------------------------
# Thresholds (module-level, with their basis)
# ---------------------------------------------------------------------------------------------
MAX_RELIABILITY = 1            # MOD13Q1 pixel reliability: 0 good, 1 marginal kept; 2 snow/ice, 3 cloud dropped
COMPOSITE_DAYS = 16            # MOD13Q1 composite period
N_BINS = 23                    # composites per year: DOY 1, 17, ..., 353
SG_WINDOW = 5                  # Savitzky-Golay window (5 composites = 80 d, keeps ~1-2 month crop phases)
SG_ORDER = 2                   # quadratic preserves peak height better than a moving average
MIN_COVERAGE_BINS = 20         # a calendar year needs >= 20 of 23 composites inside the observed range
THRESHOLD_FRAC = 0.20          # green-up / senescence at baseline + 20 % of amplitude (TIMESAT default 20 %)
FALLOW_AMPLITUDE = 0.12        # amplitude (peak - annual min) below this: no crop canopy developed
WINTER_PEAK_MAX_DOY = 175      # single peak before ~DOY 175 (late Jun): autumn-sown cereal (Konya peak ~May)
                               # single peak after: spring/summer crop. (threshold tuned from the original <170 spec)
DOUBLE_PEAK_MIN_PROM = 0.15    # each of two peaks needs prominence >= 0.15 NDVI (well above SG-smoothed noise)
DOUBLE_PEAK_MIN_FRAC = 0.40    # ... and >= 40 % of the year's amplitude
DOUBLE_PEAK_MIN_SEP_BINS = 5   # peaks >= 5 composites (80 days) apart
STRESS_Z = -1.0                # season-integral z <= -1 (~ lowest 16 % of years if normal)
MIN_PATTERN_YEARS = 5          # min years of one crop pattern to compute a within-pattern z-score
BARE_THRESHOLD_DEFAULT = 0.20  # bare soil / stubble NDVI in semi-arid cropland (MOD13 bare soil ~0.1-0.2)
BARE_THRESHOLD_BOUNDS = (0.15, 0.30)   # derived threshold is clipped to this range
BARE_THRESHOLD_MARGIN = 0.05   # derived threshold = median annual minimum + margin (soil moisture / residue)
BARE_PROB_WINDOW = 0.60        # bin counts as "bare window" when P(bare) >= 0.6


def _f(v, nd=3):
    if v is None:
        return None
    v = float(v)
    return None if math.isnan(v) else round(v, nd)


def regularise(ndvi: pd.DataFrame) -> pd.DataFrame:
    """Filter by reliability and place observations on the MOD13Q1 16-day grid (DOY 1, 17, ... per year).

    Returns a frame with ``raw`` (NaN where no good observation), ``filled`` (linearly interpolated), indexed by
    grid date and trimmed to the span between the first and last good observation.
    """
    d = ndvi.copy()
    if "reliability" in d.columns:
        d = d[d["reliability"] <= MAX_RELIABILITY]
    s = d["ndvi"].astype(float).dropna().sort_index()
    s = s[~s.index.duplicated(keep="first")]
    if len(s) < 8:
        raise ValueError("too few good NDVI observations")
    y0, y1 = s.index[0].year, s.index[-1].year
    grid = pd.DatetimeIndex([pd.Timestamp(y, 1, 1) + pd.Timedelta(days=COMPOSITE_DAYS * k)
                             for y in range(y0, y1 + 1) for k in range(N_BINS)], name="date")
    pos = grid.get_indexer(s.index, method="nearest", tolerance=pd.Timedelta(days=COMPOSITE_DAYS // 2))
    ok = pos >= 0
    per_slot = pd.Series(s.to_numpy()[ok]).groupby(pos[ok]).mean()   # one value per grid slot
    raw = pd.Series(np.nan, index=grid)
    raw.iloc[per_slot.index.to_numpy()] = per_slot.to_numpy()
    first_ok, last_ok = raw.first_valid_index(), raw.last_valid_index()
    raw = raw.loc[first_ok:last_ok]
    filled = raw.interpolate(method="time", limit_direction="both")
    return pd.DataFrame({"raw": raw, "filled": filled})


def _cross_doy(doy, y, i, thr):
    """DOY where the series crosses ``thr`` between samples i and i+1 (linear interpolation)."""
    y0, y1 = y[i], y[i + 1]
    frac = 0.5 if y1 == y0 else (thr - y0) / (y1 - y0)
    return doy[i] + float(np.clip(frac, 0, 1)) * (doy[i + 1] - doy[i])


def _pattern(y: np.ndarray, amp: float) -> str:
    if amp < FALLOW_AMPLITUDE:
        return "fallow"
    pk, props = find_peaks(y, prominence=max(DOUBLE_PEAK_MIN_PROM, DOUBLE_PEAK_MIN_FRAC * amp))
    if len(pk) >= 2:
        order = np.argsort(props["prominences"])[::-1][:2]
        a, b = sorted(pk[order])
        if b - a >= DOUBLE_PEAK_MIN_SEP_BINS:
            return "double_crop"
    peak_doy = 1 + COMPOSITE_DAYS * int(np.argmax(y))
    return "winter_crop" if peak_doy < WINTER_PEAK_MAX_DOY else "summer_crop"


def derive_bare_threshold(annual_minima) -> float:
    """Field-specific bare-soil NDVI threshold: median annual minimum of the smoothed NDVI + 0.05,
    clipped to [0.15, 0.30]. A field that is bare for part of most years reveals its own bare-soil NDVI
    (soil colour, residue); a perennial/never-bare field is clipped at 0.30 and yields no bare windows.
    """
    t = float(np.median(annual_minima)) + BARE_THRESHOLD_MARGIN
    return float(np.clip(t, *BARE_THRESHOLD_BOUNDS))


def analyze_ndvi(ndvi: pd.DataFrame, bare_threshold: float | None = None) -> dict:
    """Build the ``field_memory`` object of the FieldReport (docs/CONTRACTS.md section 4).

    Steps: drop reliability > 1; regularise to the 16-day grid; linear interpolation of gaps; Savitzky-Golay
    smoothing (window 5, order 2). Per calendar year (>= 20 composites covered):

    * ``greenup_doy`` / ``senescence_doy``: smoothed NDVI crossing baseline + 20 % of amplitude on the rising
      limb before the peak / on the falling limb after it (baseline = annual minimum of the smoothed curve;
      None for fallow years or if the curve never falls below the threshold again within the year);
    * ``peak_doy``, ``peak_ndvi``;
    * ``season_integral``: sum over composites of max(NDVI - field baseline, 0) x 16 days (NDVI.days), with a
      single field baseline (median annual minimum) so years are comparable;
    * ``anomaly_z``: z-score of the integral vs all years (std with ddof=1); ``stress`` = z <= -1 (never set for
      ``fallow`` years - an intentionally unplanted year is not stress);
    * ``pattern``: winter_crop / summer_crop / double_crop / fallow (see module constants).

    ``bare_threshold`` None -> derived from the field's own annual-minimum distribution (see
    ``derive_bare_threshold``); a float overrides it (spec default 0.20 = ``BARE_THRESHOLD_DEFAULT``).
    ``bare_probability`` is reported per 16-day bin (``doy`` = bin start, 23 entries): share of years whose
    smoothed NDVI is below the threshold in that bin. ``bare_windows`` are contiguous runs of bins with
    p >= 0.6 (``end_doy`` = last day of the final bin; runs wrapping the new year are not merged).
    """
    g = regularise(ndvi)
    filled = g["filled"].to_numpy()
    win = SG_WINDOW if len(filled) >= SG_WINDOW else (len(filled) // 2) * 2 - 1
    smooth = savgol_filter(filled, win, SG_ORDER, mode="interp") if win > SG_ORDER else filled.copy()
    g["smooth"] = smooth

    ndvi_out = [
        {"date": ts.strftime("%Y-%m-%d"), "ndvi": _f(r.raw, 4), "ndvi_smooth": _f(r.smooth, 4)}
        for ts, r in g.iterrows()
    ]

    # per-year slices
    by_year = {}
    for yr, sub in g.groupby(g.index.year):
        if len(sub) >= MIN_COVERAGE_BINS:
            by_year[int(yr)] = sub
    if not by_year:
        raise ValueError("no calendar year with sufficient NDVI coverage")

    minima = np.array([s["smooth"].min() for s in by_year.values()])
    field_base = float(np.median(minima))
    thr_bare = derive_bare_threshold(minima) if bare_threshold is None else float(bare_threshold)

    years, integrals = [], []
    for yr, sub in by_year.items():
        y = sub["smooth"].to_numpy()
        doy = sub.index.dayofyear.to_numpy().astype(float)
        base = float(y.min())
        ip = int(np.argmax(y))
        amp = float(y[ip] - base)
        pattern = _pattern(y, amp) if len(y) == N_BINS else (
            "fallow" if amp < FALLOW_AMPLITUDE else
            "winter_crop" if doy[ip] < WINTER_PEAK_MAX_DOY else "summer_crop")
        greenup = senes = None
        if pattern != "fallow":
            thr = base + THRESHOLD_FRAC * amp
            below = np.where(y[:ip] < thr)[0]
            greenup = doy[0] if len(below) == 0 else _cross_doy(doy, y, int(below[-1]), thr)
            after = np.where(y[ip:] < thr)[0]
            if len(after):
                j = ip + int(after[0])
                senes = _cross_doy(doy, y, j - 1, thr)
        integral = float(np.clip(y - field_base, 0, None).sum() * COMPOSITE_DAYS)
        integrals.append(integral)
        years.append({
            "year": yr,
            "greenup_doy": None if greenup is None else int(round(greenup)),
            "peak_doy": int(doy[ip]),
            "peak_ndvi": _f(y[ip], 3),
            "senescence_doy": None if senes is None else int(round(senes)),
            "season_integral": _f(integral, 2),
            "pattern": pattern,
        })
    integrals = np.array(integrals)

    def _z(vals: np.ndarray) -> np.ndarray:
        sd = vals.std(ddof=1) if len(vals) > 1 else 0.0
        return (vals - vals.mean()) / sd if sd > 0 else np.zeros_like(vals)

    # z-score within the same crop pattern: a winter cereal naturally has a smaller NDVI integral than an
    # irrigated summer crop, so comparing across patterns would flag crop choice as "stress". Patterns with
    # fewer than MIN_PATTERN_YEARS years fall back to the all-years z-score.
    z = _z(integrals)
    groups = np.array(["summer" if r["pattern"] in ("summer_crop", "double_crop") else r["pattern"] for r in years])
    for gname in set(groups):
        m = groups == gname
        if m.sum() >= MIN_PATTERN_YEARS:
            z[m] = _z(integrals[m])
    for rec, zi in zip(years, z):
        rec["anomaly_z"] = _f(zi, 2)
        rec["stress"] = bool(zi <= STRESS_Z and rec["pattern"] != "fallow")
    stress_years = [r["year"] for r in years if r["stress"]]

    # bare probability per 16-day bin
    sm = g["smooth"]
    k = np.minimum((sm.index.dayofyear.to_numpy() - 1) // COMPOSITE_DAYS, N_BINS - 1)
    in_full = np.asarray(sm.index.year.isin(list(by_year)))
    isbare = (sm < thr_bare).to_numpy()[in_full]
    prob = pd.Series(isbare).groupby(k[in_full]).mean()
    bare_prob = [{"doy": 1 + COMPOSITE_DAYS * b, "p_bare": _f(prob.get(b, np.nan), 3)} for b in range(N_BINS)]

    windows, run = [], []
    for b in range(N_BINS + 1):
        p = prob.get(b, 0.0) if b < N_BINS else 0.0
        if p >= BARE_PROB_WINDOW:
            run.append((b, p))
        elif run:
            windows.append({
                "start_doy": 1 + COMPOSITE_DAYS * run[0][0],
                "end_doy": min(365, COMPOSITE_DAYS * (run[-1][0] + 1)),
                "probability": _f(np.mean([p_ for _, p_ in run]), 3),
            })
            run = []

    return {
        "ndvi": ndvi_out,
        "years": years,
        "bare_probability": bare_prob,
        "bare_windows": windows,
        "stress_years": stress_years,
        "bare_threshold": _f(thr_bare, 3),
    }
