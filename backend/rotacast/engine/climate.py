"""Climate profile from daily NASA POWER data (FAO-56 ET0, frost statistics, trends).

References
----------
Allen, R.G., Pereira, L.S., Raes, D., Smith, M. (1998). Crop evapotranspiration - Guidelines for
computing crop water requirements. FAO Irrigation and Drainage Paper 56. FAO, Rome.
Mann, H.B. (1945) Econometrica 13:245-259; Kendall, M.G. (1975) Rank Correlation Methods.
Sen, P.K. (1968) J. Am. Stat. Assoc. 63:1379-1389.
"""
from __future__ import annotations

import calendar
import math

import numpy as np
import pandas as pd
from scipy import stats

# ---------------------------------------------------------------------------------------------
# Thresholds / constants
# ---------------------------------------------------------------------------------------------
GSC = 0.0820                  # solar constant, MJ m-2 min-1 (FAO-56 eq. 21)
SIGMA = 4.903e-9              # Stefan-Boltzmann, MJ K-4 m-2 day-1 (FAO-56 eq. 39)
FROST_TMIN_C = 0.0            # frost day: tmin <= 0 degC (WMO/agro-meteorological convention)
HEAT_TMAX_C = 35.0            # "hot day" tmax >= 35 degC (common heat-wave / grain-fill damage level)
SPLIT_DOY = 200               # last spring frost searched before, first fall frost after (~19 July)
SHIFT_YEARS = 15              # years in the early / late comparison windows
NORMAL_PERCENTILES = (10, 50, 90)


# ---------------------------------------------------------------------------------------------
# ET0
# ---------------------------------------------------------------------------------------------
def _e0(t):
    """Saturation vapour pressure (kPa), FAO-56 eq. 11."""
    return 0.6108 * np.exp(17.27 * t / (t + 237.3))


def extraterrestrial_radiation(doy, lat_deg: float):
    """Daily extraterrestrial radiation Ra (MJ m-2 day-1), FAO-56 eq. 21 (+ eqs. 22-25)."""
    doy = np.asarray(doy, dtype=float)
    phi = math.radians(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
    delta = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(delta), -1.0, 1.0))
    return (24 * 60 / np.pi) * GSC * dr * (
        ws * np.sin(phi) * np.sin(delta) + np.cos(phi) * np.cos(delta) * np.sin(ws)
    )


def et0_penman_monteith(df: pd.DataFrame, lat: float, elevation_m: float) -> pd.Series:
    """FAO-56 Penman-Monteith reference evapotranspiration, daily (mm/day), eq. 6, G = 0.

    Required columns: tmax, tmin, wind2m, rs (MJ m-2 day-1) and either ``rh`` (daily mean RH %,
    ea by eq. 19) or both ``rhmax`` and ``rhmin`` (eq. 17). A column ``ea`` (kPa), if present,
    takes precedence. Index must be a DatetimeIndex (for the day of year). Result is clipped at 0.
    """
    tmax = df["tmax"].to_numpy(float)
    tmin = df["tmin"].to_numpy(float)
    tmean = (tmax + tmin) / 2                                   # eq. 9
    u2 = df["wind2m"].to_numpy(float)
    rs = df["rs"].to_numpy(float)
    doy = df.index.dayofyear.to_numpy()

    es = (_e0(tmax) + _e0(tmin)) / 2                            # eq. 12
    if "ea" in df.columns:
        ea = df["ea"].to_numpy(float)
    elif "rhmax" in df.columns and "rhmin" in df.columns:       # eq. 17
        ea = (_e0(tmin) * df["rhmax"].to_numpy(float) / 100 + _e0(tmax) * df["rhmin"].to_numpy(float) / 100) / 2
    else:                                                       # eq. 19
        ea = df["rh"].to_numpy(float) / 100 * es

    ra = extraterrestrial_radiation(doy, lat)
    rso = (0.75 + 2e-5 * elevation_m) * ra                      # eq. 37
    rs_rso = np.clip(np.divide(rs, rso, out=np.full_like(rs, np.nan), where=rso > 0), 0.0, 1.0)
    rs_rso = np.where(np.isnan(rs_rso), 0.5, rs_rso)            # polar night: arbitrary, Rn ~ 0 anyway
    rns = 0.77 * rs                                             # eq. 38
    rnl = SIGMA * ((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2 * (0.34 - 0.14 * np.sqrt(ea)) * (
        1.35 * rs_rso - 0.35)                                   # eq. 39
    rn = rns - rnl                                              # eq. 40

    delta = 4098 * _e0(tmean) / (tmean + 237.3) ** 2            # eq. 13
    pressure = 101.3 * ((293 - 0.0065 * elevation_m) / 293) ** 5.26   # eq. 7
    gamma = 0.000665 * pressure                                 # eq. 8
    g = 0.0
    et0 = (0.408 * delta * (rn - g) + gamma * 900 / (tmean + 273) * u2 * (es - ea)) / (
        delta + gamma * (1 + 0.34 * u2))
    return pd.Series(np.clip(et0, 0.0, None), index=df.index, name="et0")


def add_et0(df: pd.DataFrame, lat: float, elevation_m: float) -> pd.DataFrame:
    """Return a copy of ``df`` with an ``et0`` column (mm/day)."""
    out = df.copy()
    out["et0"] = et0_penman_monteith(out, lat, elevation_m)
    out.attrs = dict(df.attrs)
    return out


# ---------------------------------------------------------------------------------------------
# Trend statistics
# ---------------------------------------------------------------------------------------------
def sen_slope(x, y) -> float:
    """Sen's (Theil-Sen) slope: median of all pairwise slopes. NaN if fewer than 2 points."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    ok = ~(np.isnan(x) | np.isnan(y))
    x, y = x[ok], y[ok]
    if len(x) < 2:
        return float("nan")
    i, j = np.triu_indices(len(x), k=1)
    dx = x[j] - x[i]
    keep = dx != 0
    return float(np.median((y[j] - y[i])[keep] / dx[keep]))


def mann_kendall_p(y) -> float:
    """Two-sided Mann-Kendall trend test p-value (normal approximation, continuity correction, no tie correction)."""
    y = np.asarray(y, float)
    y = y[~np.isnan(y)]
    n = len(y)
    if n < 4:
        return float("nan")
    s = float(np.sign(y[None, :] - y[:, None])[np.triu_indices(n, k=1)].sum())
    var = n * (n - 1) * (2 * n + 5) / 18
    z = 0.0 if s == 0 else (s - np.sign(s)) / math.sqrt(var)
    return float(2 * (1 - stats.norm.cdf(abs(z))))


# ---------------------------------------------------------------------------------------------
# Climate profile
# ---------------------------------------------------------------------------------------------
def _f(v, nd=2):
    """Plain float (rounded) or None for NaN."""
    if v is None:
        return None
    v = float(v)
    return None if math.isnan(v) else round(v, nd)


def _pcts(values) -> dict:
    v = np.asarray(values, float)
    v = v[~np.isnan(v)]
    if len(v) == 0:
        return {"p10": None, "p50": None, "p90": None}
    q = np.percentile(v, NORMAL_PERCENTILES)
    return {"p10": _f(q[0], 1), "p50": _f(q[1], 1), "p90": _f(q[2], 1)}


def _full_years(df: pd.DataFrame) -> list[int]:
    """Calendar years whose every day is present in the index."""
    counts = df.groupby(df.index.year).size()
    return [int(y) for y, n in counts.items() if n == (366 if calendar.isleap(int(y)) else 365)]


def _yearly_table(df: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    """Per-year metrics (full years only), including frost dates (DOY, NaN when no frost)."""
    d = df[df.index.year.isin(years)]
    yr = d.index.year
    doy = pd.Series(d.index.dayofyear, index=d.index)
    tmean = (d["tmax"] + d["tmin"]) / 2 if "tmean" not in d else d["tmean"]
    frost = d["tmin"] <= FROST_TMIN_C

    g = d.groupby(yr)
    tab = pd.DataFrame(index=pd.Index(years, name="year"))
    tab["precip_mm"] = g["precip"].sum()
    tab["et0_mm"] = g["et0"].sum()
    tab["tmean_c"] = tmean.groupby(yr).mean()
    tab["gdd0"] = tmean.clip(lower=0).groupby(yr).sum()
    tab["heat_days_35"] = (d["tmax"] >= HEAT_TMAX_C).groupby(yr).sum()
    tab["frost_days"] = frost.groupby(yr).sum()

    spring = frost & (doy < SPLIT_DOY)
    fall = frost & (doy > SPLIT_DOY)
    last_spring = doy.where(spring).groupby(yr).max()
    first_fall = doy.where(fall).groupby(yr).min()
    tab["last_spring_frost"] = last_spring
    tab["first_fall_frost"] = first_fall
    ndays = pd.Series([366 if calendar.isleap(y) else 365 for y in years], index=tab.index)
    # no frost in spring -> frost-free from day 0; no fall frost -> frost-free to year end
    tab["frost_free_days"] = (first_fall.fillna(ndays + 1) - last_spring.fillna(0) - 1).clip(lower=0)

    month = d.index.month
    tab["spring_precip_mm"] = d["precip"].where(month.isin([3, 4, 5]), 0.0).groupby(yr).sum()
    tab["summer_tmax_c"] = d["tmax"].where(month.isin([6, 7, 8])).groupby(yr).mean()
    return tab


# id, column, unit, label
_SHIFT_METRICS = [
    ("last_spring_frost", "last_spring_frost", "doy",
     {"en": "Last spring frost", "tr": "Son ilkbahar donu"}),
    ("first_fall_frost", "first_fall_frost", "doy",
     {"en": "First fall frost", "tr": "İlk sonbahar donu"}),
    ("frost_free_days", "frost_free_days", "days",
     {"en": "Frost-free days", "tr": "Donsuz gün sayısı"}),
    ("heat_days_35", "heat_days_35", "days",
     {"en": "Days with Tmax >= 35 °C", "tr": "Tmax >= 35 °C olan gün sayısı"}),
    ("gdd0", "gdd0", "°C·day",
     {"en": "Growing degree-days (base 0 °C)", "tr": "Büyüme derece-günü (taban 0 °C)"}),
    ("precip_mm", "precip_mm", "mm",
     {"en": "Annual precipitation", "tr": "Yıllık yağış"}),
    ("et0_mm", "et0_mm", "mm",
     {"en": "Annual reference ET0", "tr": "Yıllık referans ET0"}),
    ("tmean_c", "tmean_c", "°C",
     {"en": "Mean annual temperature", "tr": "Yıllık ortalama sıcaklık"}),
    ("spring_precip_mm", "spring_precip_mm", "mm",
     {"en": "Spring (MAM) precipitation", "tr": "İlkbahar (MAM) yağışı"}),
    ("summer_tmax_c", "summer_tmax_c", "°C",
     {"en": "Summer (JJA) mean Tmax", "tr": "Yaz (HAZ-AĞU) ortalama Tmax"}),
]


def climate_profile(df: pd.DataFrame, lat: float) -> dict:
    """Build the ``climate`` object of the FieldReport (docs/CONTRACTS.md section 4).

    ``df`` is the POWER daily frame (tmax, tmin, tmean, precip, ...). If ``et0`` is missing it is computed
    with ``df.attrs['elevation_m']`` (default 0 m when absent). Annual statistics use full calendar years only;
    monthly normals use all complete months. Shift compares the first and last ``SHIFT_YEARS`` full years
    (or half of the record each when it is shorter than 2 x SHIFT_YEARS); trends use the whole record.
    """
    df = df.sort_index()
    if "et0" not in df.columns:
        df = add_et0(df, lat, float(df.attrs.get("elevation_m", 0.0)))
    years = _full_years(df)
    if len(years) < 4:
        raise ValueError("climate_profile needs at least 4 full calendar years of daily data")
    tab = _yearly_table(df, years)

    annual = [
        {"year": int(y), "precip_mm": _f(r.precip_mm, 1), "et0_mm": _f(r.et0_mm, 1), "tmean_c": _f(r.tmean_c, 2),
         "gdd0": _f(r.gdd0, 0), "heat_days_35": int(r.heat_days_35), "frost_days": int(r.frost_days)}
        for y, r in tab.iterrows()
    ]

    # monthly normals over all complete months
    ym = df.groupby([df.index.year, df.index.month])
    cnt = ym["tmax"].count()
    dim = pd.Series([calendar.monthrange(y, m)[1] for y, m in cnt.index], index=cnt.index)
    complete = cnt[cnt == dim].index
    mm = pd.DataFrame({
        "precip_mm": ym["precip"].sum(), "et0_mm": ym["et0"].sum(), "tmax_c": ym["tmax"].mean(),
        "tmin_c": ym["tmin"].mean(),
        "tmean_c": ym["tmean"].mean() if "tmean" in df else (ym["tmax"].mean() + ym["tmin"].mean()) / 2,
    }).loc[complete]
    normals = mm.groupby(level=1).mean()
    monthly = [
        {"month": int(m), "precip_mm": _f(r.precip_mm, 1), "et0_mm": _f(r.et0_mm, 1), "tmean_c": _f(r.tmean_c, 2),
         "tmin_c": _f(r.tmin_c, 2), "tmax_c": _f(r.tmax_c, 2)}
        for m, r in normals.iterrows()
    ]

    frost = {
        "last_spring_doy": _pcts(tab["last_spring_frost"]),
        "first_fall_doy": _pcts(tab["first_fall_frost"]),
        "frost_free_days": _pcts(tab["frost_free_days"]),
    }
    p_mean, et_mean = float(tab["precip_mm"].mean()), float(tab["et0_mm"].mean())
    water = {"aridity_index": _f(p_mean / et_mean, 3) if et_mean > 0 else None,
             "annual_deficit_mm": _f(et_mean - p_mean, 1)}

    n = len(years)
    k = SHIFT_YEARS if n >= 2 * SHIFT_YEARS else n // 2
    early_years, late_years = years[:k], years[-k:]
    metrics = []
    for mid, col, unit, label in _SHIFT_METRICS:
        s = tab[col].astype(float)
        e, l = s.loc[early_years].mean(), s.loc[late_years].mean()
        valid = s.dropna()
        slope = sen_slope(valid.index.to_numpy(), valid.to_numpy()) * 10 if len(valid) >= 2 else float("nan")
        metrics.append({
            "id": mid, "label": label, "unit": unit,
            "early": _f(e, 2), "late": _f(l, 2), "delta": _f(l - e, 2),
            "trend_per_decade": _f(slope, 3), "p_value": _f(mann_kendall_p(valid.to_numpy()), 4),
        })

    return {
        "period": [int(years[0]), int(years[-1])],
        "annual": annual,
        "monthly_normals": monthly,
        "frost": frost,
        "water_balance": water,
        "shift": {"early": [int(early_years[0]), int(early_years[-1])],
                  "late": [int(late_years[0]), int(late_years[-1])], "metrics": metrics},
    }
