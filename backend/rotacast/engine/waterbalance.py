"""FAO-56 single-crop-coefficient daily root-zone water balance (chapters 6, 7 and 8).

Public API
----------
* ``SeasonResult``            - result of one crop season (contract fields + documented extensions)
* ``simulate_season``         - one season for one sowing date (wrapper around the batch core)
* ``simulate_season_batch``   - many sowing dates (an ensemble of years) at once, vectorised over members
* ``simulate_fallow``         - bare-soil water balance between crops (FAO-56 ch. 7, simplified)
* ``find_sow_date``           - climate-driven sowing date (7-day rolling mean temperature rule)

Modelling simplifications (each also flagged in a comment next to the code)
---------------------------------------------------------------------------
* Kc curve: constant Kc_ini, linear in the development and late stages (FAO-56 Fig. 34, ch. 6).
  Climate corrections of Kc_mid / Kc_end (eq. 62, 65) are not applied.
* Stage lengths are scaled uniformly so the season ends when ``gdd_to_maturity`` is reached in that
  year's weather, capped to +/-30 % of the reference length (CONTRACTS.md section 2).
* Root depth grows linearly Zr_min -> Zr_max through the development stage (FAO-56 ch. 8, Table 22 range).
  Layers entered by the growing roots carry the depletion fraction the profile had at sowing.
* p is adjusted with ETc: p = p_table + 0.04 (5 - ETc) (FAO-56 Table 22 note), limited to 0.1-0.8.
* Ks follows eq. 84, ETa = Ks Kc ET0 (eq. 80 without the dual-coefficient Ke split).
* Effective precipitation: daily USDA-SCS curve-number runoff (CN 75, AMC II) subtracted from rain.
  Interception is ignored. The monthly USDA-SCS Peff table of FAO-56 ch.5/FAO-33 is not used because it
  is a monthly formula and the demo needs daily storage.
* Capillary rise = 0 (eq. 85, CR = 0). Net irrigation depth (100 % application efficiency).
* Soil cover uses Kc as a canopy proxy: fc = ((Kc-Kc_min)/(Kc_max-Kc_min))^(1+0.5h) (eq. 76, h = 1 m).
* Bare soil between crops: Kc_bare = 0.15-0.30 depending on profile wetness (FAO-56 ch. 7 Ke simplified,
  no explicit evaporation-layer stage 1/stage 2 bookkeeping), 1.0 m bucket.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------------------------------
# Constants (documented simplifications)
# --------------------------------------------------------------------------------------------------
CURVE_NUMBER = 75.0            # USDA-SCS CN, cropland, AMC II (runoff -> effective precipitation)
GDD_SCALE_CAP = 0.30           # +/-30 % stage-length scaling cap (CONTRACTS.md)
KC_MIN = 0.15                  # FAO-56 eq. 76: Kc of bare soil with no ground cover
KC_MAX_FLOOR = 1.20            # FAO-56 eq. 72 order of magnitude for Kc_max
PLANT_HEIGHT_M = 1.0           # h in eq. 76 (not in the knowledge base -> 1 m)
COVER_THRESHOLD = 0.30         # canopy cover above which a day counts as "soil covered"
P_MIN, P_MAX = 0.10, 0.80      # clip of the ETc-adjusted depletion fraction p
BARE_BUCKET_M = 1.0            # depth of the bare-soil water bucket (m)
BARE_KC_DRY, BARE_KC_WET = 0.15, 0.30  # Kc_bare range (FAO-56 ch. 7, simplified)
BARE_MAX_DEPLETION = 0.90      # bare soil cannot dry below 90 % of TAW (no roots, only evaporation)
EROSIVE_MONTHS = (4, 5, 6, 10, 11)  # months with high rainfall erosivity on the Anatolian plateau (RUSLE R)

_STAGE_ALIASES = {
    "ini": 0, "init": 0, "initial": 0, "seedling": 0, "emergence": 0,
    "dev": 1, "development": 1, "vegetative": 1,
    "mid": 2, "flowering": 2, "anthesis": 2, "heading": 2, "reproductive": 2,
    "late": 3, "grain_fill": 3, "ripening": 3, "maturity": 3,
}


class WeatherCoverageError(ValueError):
    """Raised when the weather series does not cover a requested season."""


# --------------------------------------------------------------------------------------------------
# Weather preprocessing (done once per DataFrame, then cached)
# --------------------------------------------------------------------------------------------------
class _Weather:
    """Plain numpy view of a daily weather DataFrame (continuous daily index)."""

    def __init__(self, df: pd.DataFrame):
        if not isinstance(df.index, pd.DatetimeIndex):
            raise TypeError("weather must have a DatetimeIndex")
        d = df[~df.index.duplicated()].sort_index()
        d.index = d.index.normalize()
        full = pd.date_range(d.index[0], d.index[-1], freq="D")
        d = d.reindex(full)
        for col in ("precip", "et0"):
            if col not in d:
                raise KeyError(f"weather must contain '{col}'")
        self.n = len(full)
        self.start_ord = full[0].toordinal()
        self.end_date = full[-1].date()
        self.precip = d["precip"].fillna(0.0).to_numpy(float)
        self.et0 = d["et0"].interpolate(limit_direction="both").to_numpy(float)
        if "tmean" in d:
            tmean = d["tmean"]
        elif "tmax" in d and "tmin" in d:
            tmean = (d["tmax"] + d["tmin"]) / 2.0
        else:
            raise KeyError("weather must contain 'tmean' or 'tmax'+'tmin'")
        tmean = tmean.interpolate(limit_direction="both")
        self.tmean = tmean.to_numpy(float)
        nan = np.full(self.n, np.nan)
        self.tmax = d["tmax"].to_numpy(float) if "tmax" in d else nan  # NaN -> no heat days
        self.tmin = d["tmin"].to_numpy(float) if "tmin" in d else nan  # NaN -> no frost days
        self.roll7 = pd.Series(self.tmean).rolling(7, min_periods=1).mean().to_numpy()
        self.month = full.month.to_numpy()
        self.year = full.year.to_numpy()
        self.erosive = np.isin(self.month, EROSIVE_MONTHS)
        # USDA-SCS curve-number runoff, daily: Q = (P-Ia)^2/(P-Ia+S), Ia = 0.2 S
        s = 25.4 * (1000.0 / CURVE_NUMBER - 10.0)
        ia = 0.2 * s
        ex = np.maximum(self.precip - ia, 0.0)
        runoff = np.where(ex > 0, ex * ex / (ex + s), 0.0)
        self.peff = self.precip - runoff
        self._gdd: dict[float, np.ndarray] = {}

    def gdd_cum(self, t_base: float) -> np.ndarray:
        key = float(t_base)
        if key not in self._gdd:
            self._gdd[key] = np.cumsum(np.maximum(self.tmean - key, 0.0))  # simple GDD, no upper cut-off
        return self._gdd[key]

    def idx(self, d: date) -> int:
        return d.toordinal() - self.start_ord

    def date_of(self, i: int) -> date:
        return date.fromordinal(int(i) + self.start_ord)


_CACHE: list[tuple[object, _Weather]] = []


def prepare_weather(weather) -> _Weather:
    """Return the cached numpy view of ``weather`` (accepts a DataFrame or an already prepared view)."""
    if isinstance(weather, _Weather):
        return weather
    for obj, wx in _CACHE:
        if obj is weather:
            return wx
    wx = _Weather(weather)
    _CACHE.append((weather, wx))
    if len(_CACHE) > 6:
        _CACHE.pop(0)
    return wx


# --------------------------------------------------------------------------------------------------
# Sowing rule
# --------------------------------------------------------------------------------------------------
def _doy_idx(wx: _Weather, years: np.ndarray, doy: int) -> np.ndarray:
    jan1 = np.array([date(int(y), 1, 1).toordinal() for y in years], dtype=np.int64)
    return jan1 + (doy - 1) - wx.start_ord


def sow_index(crop, wx: _Weather, years) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorised sowing rule. Returns (rule_idx, window_end_idx, valid) as arrays over ``years``."""
    years = np.atleast_1d(np.asarray(years))
    a, b = int(crop.sowing.window_doy[0]), int(crop.sowing.window_doy[1])
    if b < a:  # window wrapping over new year
        b += 365
    ia = _doy_idx(wx, years, a)
    ib = _doy_idx(wx, years, b)
    valid = (ia >= 0) & (ib < wx.n)
    width = b - a + 1
    idx = ia[:, None] + np.arange(width)[None, :]
    idx_c = np.clip(idx, 0, wx.n - 1)
    thr = float(crop.sowing.threshold_c)
    r7 = wx.roll7[idx_c]
    cond = (r7 <= thr) if crop.sowing.rule == "tmean_below" else (r7 >= thr)
    hit = cond.any(axis=1)
    first = np.argmax(cond, axis=1)
    rule = np.where(hit, ia + first, ib)  # never crosses -> window end
    return rule, ib, valid


def find_sow_date(crop, weather, year: int) -> date | None:
    """Sowing date in calendar ``year``: first day inside ``window_doy`` on which the 7-day rolling mean of
    Tmean crosses ``threshold_c`` (<= for ``tmean_below``, >= for ``tmean_above``); the window end if it never
    crosses; ``None`` if the window is not covered by the weather."""
    wx = prepare_weather(weather)
    rule, _, valid = sow_index(crop, wx, [year])
    if not valid[0]:
        return None
    return wx.date_of(rule[0])


# --------------------------------------------------------------------------------------------------
# Season geometry
# --------------------------------------------------------------------------------------------------
def season_lengths(crop, wx: _Weather, sow_idx: np.ndarray, end_idx: np.ndarray | None = None):
    """Per-member stage lengths (M,4), total simulated days (M,) and GDD scale (M,).

    Season length = days until ``gdd_to_maturity`` is accumulated from sowing (simple GDD, base t_base_c),
    expressed as a scale on the reference stage lengths and capped to 1 +/- 0.30."""
    ref = np.asarray(crop.fao56.stage_days, float)
    ref_total = ref.sum()
    cum = wx.gdd_cum(crop.t_base_c)
    sow_c = np.clip(sow_idx, 0, wx.n - 1)
    before = np.where(sow_c > 0, cum[np.maximum(sow_c - 1, 0)], 0.0)
    pos = np.searchsorted(cum, before + float(crop.gdd_to_maturity), side="left")
    reached = pos < wx.n
    n_gdd = np.where(reached, pos - sow_c + 1, np.inf)
    scale = np.clip(n_gdd / ref_total, 1 - GDD_SCALE_CAP, 1 + GDD_SCALE_CAP)
    lens = np.maximum(np.rint(ref[None, :] * scale[:, None]), (ref[None, :] > 0).astype(float)).astype(int)
    total = lens.sum(axis=1)
    nominal_total = total.copy()
    if end_idx is not None:
        total = np.minimum(total, np.maximum(end_idx - sow_idx, 0))
    return lens, total, scale, nominal_total


def _stage_of(crop) -> int:
    name = str(getattr(crop, "sensitive_stage", "mid")).lower()
    return _STAGE_ALIASES.get(name, 2)


# --------------------------------------------------------------------------------------------------
# Season result
# --------------------------------------------------------------------------------------------------
@dataclass
class SeasonResult:
    crop_id: str
    sow_date: date
    harvest_date: date
    etc_mm: float
    eta_mm: float
    precip_mm: float
    effective_precip_mm: float
    irrigation_mm: float
    drainage_mm: float
    stress_days: int               # days with Ks < 1
    yield_ratio: float             # Ya/Ym = 1 - Ky (1 - ETa/ETc), clipped 0..1
    heat_days: int
    frost_days: int
    soil_cover_days: int           # canopy cover > 30 % (Kc-based proxy)
    # ---- contract extensions (all optional for callers) ----
    final_depletion_mm: float = 0.0       # root-zone depletion Dr at the end of the season
    final_depletion_frac: float = 0.0     # Dr / TAW at the end of the season (carried to the next phase)
    initial_depletion_mm: float = 0.0
    root_zone_gain_mm: float = 0.0        # water added to the root zone by root growth into new layers
    taw_end_mm: float = 0.0
    erosive_days: int = 0                 # season days that fall in high-erosivity months
    season_days: int = 0
    gdd_scale: float = 1.0

    @property
    def delta_storage_mm(self) -> float:
        """Change in root-zone water storage (TAW - Dr) implied by the balance terms (mm)."""
        return (self.effective_precip_mm + self.irrigation_mm + self.root_zone_gain_mm
                - self.eta_mm - self.drainage_mm)


def _season_core(crop, wx: _Weather, soil, sow_idx: np.ndarray, irrigation: str, f0, end_idx=None) -> dict:
    """Vectorised FAO-56 daily loop over M members (one sowing date each)."""
    M = len(sow_idx)
    sow_idx = np.asarray(sow_idx, dtype=np.int64)
    f0 = np.clip(np.broadcast_to(np.asarray(f0, float), (M,)).copy(), 0.0, 1.0)
    if M == 0:
        return {"M": 0}
    if np.any(sow_idx < 0):
        raise WeatherCoverageError("sowing date before the start of the weather series")
    lens, total, scale, nominal_total = season_lengths(crop, wx, sow_idx, end_idx)
    if np.any(sow_idx + total > wx.n):
        raise WeatherCoverageError(f"weather ends {wx.end_date}; season of {crop.id} is not fully covered")
    T = int(total.max()) if M else 0
    if T == 0:
        raise ValueError("empty season")
    tt = np.arange(T)[:, None]                                   # (T,1)
    act = tt < total[None, :]                                    # (T,M)
    gi = np.minimum(sow_idx[None, :] + tt, wx.n - 1)
    ET0, PE, PR = wx.et0[gi], wx.peff[gi], wx.precip[gi]

    l_ini, l_dev, l_mid, l_late = (lens[:, j][None, :] for j in range(4))
    b1, b2, b3 = l_ini, l_ini + l_dev, l_ini + l_dev + l_mid
    kc_ini, kc_mid, kc_end = (float(x) for x in crop.fao56.kc)
    dev_frac = np.clip((tt - b1 + 1) / np.maximum(l_dev, 1), 0.0, 1.0)
    late_frac = np.clip((tt - b3 + 1) / np.maximum(l_late, 1), 0.0, 1.0)
    # FAO-56 Fig. 34: flat initial, linear development, flat mid, linear late stage
    KC = np.where(tt < b1, kc_ini,
         np.where(tt < b2, kc_ini + (kc_mid - kc_ini) * dev_frac,
         np.where(tt < b3, kc_mid, kc_mid + (kc_end - kc_mid) * late_frac)))
    zmin, zmax = (float(x) for x in crop.fao56.root_depth_m)
    ZR = zmin + (zmax - zmin) * dev_frac                         # linear root growth through the dev stage
    taw_m = float(soil.taw_mm_per_m)
    TAW = taw_m * ZR
    ETC_raw = KC * ET0
    ETC = ETC_raw * act
    # FAO-56 Table 22 note: p = p_table + 0.04 (5 - ETc), ETc in mm/day
    P = np.clip(float(crop.fao56.p) + 0.04 * (5.0 - ETC_raw), P_MIN, P_MAX)
    RAW = P * TAW
    INV = 1.0 / np.maximum(TAW - RAW, 1e-6)
    dTAW = np.zeros_like(TAW)
    dTAW[1:] = TAW[1:] - TAW[:-1]
    f_sub = f0[None, :]
    D_ADD = dTAW * f_sub                                         # depletion carried by newly entered layers
    G_ADD = dTAW * (1.0 - f_sub)                                 # water carried by newly entered layers

    ETA = np.empty((T, M))
    IRR = np.zeros((T, M))
    DP = np.empty((T, M))
    KS = np.empty((T, M))
    DRH = np.empty((T, M))
    Dr = f0 * TAW[0]
    D0 = Dr.copy()
    mode = irrigation
    raw15, rawh = 1.5 * RAW, 0.5 * RAW
    for t in range(T):
        Dr = Dr + D_ADD[t]
        if mode == "full":            # refill to field capacity when Dr > RAW
            irr = np.where(Dr > RAW[t], Dr, 0.0)
            Dr = Dr - irr
            IRR[t] = irr
        elif mode == "deficit":       # refill to 50 % of RAW when Dr > 1.5 RAW
            irr = np.where(Dr > raw15[t], Dr - rawh[t], 0.0)
            Dr = Dr - irr
            IRR[t] = irr
        ks = np.clip((TAW[t] - Dr) * INV[t], 0.0, 1.0)   # eq. 84 ((TAW-Dr)/((1-p)TAW)), 1 when Dr <= RAW
        eta = ks * ETC[t]
        Dr = Dr - PE[t] + eta                              # eq. 85 with CR = 0
        dp = np.maximum(-Dr, 0.0)                          # water above field capacity drains
        Dr = np.maximum(Dr, 0.0)
        ETA[t] = eta
        DP[t] = dp
        KS[t] = ks
        DRH[t] = Dr
    last = total - 1
    cols = np.arange(M)
    Dr_end = DRH[last, cols]
    taw_end = TAW[last, cols]

    # heat / frost days in the crop's sensitive stage
    s = _stage_of(crop)
    lo = lens[:, :s].sum(axis=1)[None, :]
    hi = lo + lens[:, s][None, :]
    smask = (tt >= lo) & (tt < hi) & act
    heat = ((wx.tmax[gi] > float(crop.heat_stress_tmax_c)) & smask).sum(axis=0)
    frost = ((wx.tmin[gi] < float(crop.frost_damage_tmin_c)) & smask).sum(axis=0)
    # soil cover from Kc (eq. 76 simplified)
    kc_max = max(KC_MAX_FLOOR, kc_mid + 0.05)
    fcov = np.clip((KC - KC_MIN) / (kc_max - KC_MIN), 0.0, 1.0) ** (1.0 + 0.5 * PLANT_HEIGHT_M)
    cover_days = ((fcov > COVER_THRESHOLD) & act).sum(axis=0)

    etc_mm = ETC.sum(axis=0)
    eta_mm = (ETA * act).sum(axis=0)
    ratio = np.where(etc_mm > 0, eta_mm / np.maximum(etc_mm, 1e-9), 1.0)
    yr = np.clip(1.0 - float(crop.fao56.ky) * (1.0 - ratio), 0.0, 1.0)
    return {
        "M": M, "lens": lens, "total": total, "scale": scale, "sow_idx": sow_idx,
        "harvest_idx": sow_idx + total,
        "etc": etc_mm, "eta": eta_mm,
        "precip": (PR * act).sum(axis=0), "peff": (PE * act).sum(axis=0),
        "irr": (IRR * act).sum(axis=0), "dp": (DP * act).sum(axis=0),
        "stress": ((KS < 1.0) & act).sum(axis=0),
        "yield_ratio": yr, "heat": heat, "frost": frost, "cover_days": cover_days,
        "erosive_days": (wx.erosive[gi] & act).sum(axis=0),
        "gain": (G_ADD * act).sum(axis=0),
        "d0": D0, "d_end": Dr_end, "taw_end": taw_end,
        "f_end": np.clip(Dr_end / np.maximum(taw_end, 1e-9), 0.0, 1.0),
    }


def _to_results(crop, wx: _Weather, core: dict) -> list[SeasonResult]:
    out = []
    for m in range(core["M"]):
        out.append(SeasonResult(
            crop_id=crop.id, sow_date=wx.date_of(core["sow_idx"][m]), harvest_date=wx.date_of(core["harvest_idx"][m]),
            etc_mm=float(core["etc"][m]), eta_mm=float(core["eta"][m]), precip_mm=float(core["precip"][m]),
            effective_precip_mm=float(core["peff"][m]), irrigation_mm=float(core["irr"][m]),
            drainage_mm=float(core["dp"][m]), stress_days=int(core["stress"][m]),
            yield_ratio=float(core["yield_ratio"][m]), heat_days=int(core["heat"][m]), frost_days=int(core["frost"][m]),
            soil_cover_days=int(core["cover_days"][m]),
            final_depletion_mm=float(core["d_end"][m]), final_depletion_frac=float(core["f_end"][m]),
            initial_depletion_mm=float(core["d0"][m]), root_zone_gain_mm=float(core["gain"][m]),
            taw_end_mm=float(core["taw_end"][m]), erosive_days=int(core["erosive_days"][m]),
            season_days=int(core["total"][m]), gdd_scale=float(core["scale"][m]),
        ))
    return out


def simulate_season_batch(crop, sow_dates, weather, soil, irrigation: str = "none",
                          initial_depletion_frac=0.3, end_dates=None) -> list[SeasonResult]:
    """Run one season per sowing date (vectorised). ``end_dates`` optionally terminates the season early
    (used for cover crops that are terminated before the next main crop)."""
    wx = prepare_weather(weather)
    sow_idx = np.array([wx.idx(d) for d in sow_dates], dtype=np.int64)
    end_idx = None if end_dates is None else np.array([wx.idx(d) for d in end_dates], dtype=np.int64)
    return _to_results(crop, wx, _season_core(crop, wx, soil, sow_idx, irrigation, initial_depletion_frac, end_idx))


def simulate_season(crop, sow_date: date, weather: pd.DataFrame, soil, irrigation: str = "none",
                    initial_depletion_frac: float = 0.3, end_date: date | None = None) -> SeasonResult:
    """FAO-56 single-Kc daily simulation of one crop season.

    irrigation: "none" | "deficit" (refill to 50 % of RAW when Dr > 1.5 RAW) | "full" (refill to field
    capacity when Dr > RAW). Raises ``WeatherCoverageError`` if the weather ends before the season does."""
    return simulate_season_batch(crop, [sow_date], weather, soil, irrigation, initial_depletion_frac,
                                 None if end_date is None else [end_date])[0]


# --------------------------------------------------------------------------------------------------
# Bare-soil (fallow) balance
# --------------------------------------------------------------------------------------------------
@dataclass
class FallowResult:
    start: date
    end: date
    bare_days: int
    erosive_bare_days: int
    eta_mm: float
    precip_mm: float
    effective_precip_mm: float
    drainage_mm: float
    final_depletion_frac: float
    final_depletion_mm: float


def _fallow_core(wx: _Weather, soil, start_idx, end_idx, f0, zb: float = BARE_BUCKET_M) -> dict:
    start_idx = np.asarray(start_idx, dtype=np.int64)
    end_idx = np.asarray(end_idx, dtype=np.int64)
    M = len(start_idx)
    f0 = np.clip(np.broadcast_to(np.asarray(f0, float), (M,)).copy(), 0.0, 1.0)
    nd = np.maximum(end_idx - start_idx, 0)
    taw_b = float(soil.taw_mm_per_m) * zb
    zeros = np.zeros(M)
    if M == 0 or nd.max() == 0:
        return {"M": M, "bare": nd, "erosive": nd * 0, "eta": zeros, "peff": zeros, "precip": zeros, "dp": zeros,
                "f_end": f0, "d_end": f0 * taw_b}
    if np.any(start_idx < 0) or np.any(start_idx + nd > wx.n):
        raise WeatherCoverageError("fallow period outside the weather series")
    T = int(nd.max())
    tt = np.arange(T)[:, None]
    act = tt < nd[None, :]
    gi = np.minimum(start_idx[None, :] + tt, wx.n - 1)
    ET0, PE = wx.et0[gi], wx.peff[gi]
    ETA = np.empty((T, M))
    DP = np.empty((T, M))
    DRH = np.empty((T, M))
    Dr = f0 * taw_b
    D0 = Dr.copy()
    lim = BARE_MAX_DEPLETION * taw_b
    k_span = BARE_KC_WET - BARE_KC_DRY
    for t in range(T):
        # FAO-56 ch. 7 simplified: Kc_bare 0.15 (dry) .. 0.30 (wet), scaled by profile wetness
        eta = (BARE_KC_DRY + k_span * (1.0 - Dr / taw_b)) * ET0[t]
        base = Dr - PE[t]
        eta = np.minimum(eta, np.maximum(lim - base, 0.0))
        Dr = base + eta
        dp = np.maximum(-Dr, 0.0)
        Dr = np.maximum(Dr, 0.0)
        ETA[t] = eta
        DP[t] = dp
        DRH[t] = Dr
    cols = np.arange(M)
    d_end = np.where(nd > 0, DRH[np.maximum(nd - 1, 0), cols], D0)
    return {
        "M": M, "bare": nd, "erosive": (wx.erosive[gi] & act).sum(axis=0),
        "eta": (ETA * act).sum(axis=0), "peff": (PE * act).sum(axis=0),
        "precip": (wx.precip[gi] * act).sum(axis=0), "dp": (DP * act).sum(axis=0),
        "f_end": np.clip(d_end / taw_b, 0.0, 1.0), "d_end": d_end, "d0": D0,
    }


def simulate_fallow(start: date, end: date, weather: pd.DataFrame, soil,
                    depletion_frac: float = 0.5) -> FallowResult:
    """Bare-soil water balance for [start, end) so soil water carries over between crop seasons."""
    wx = prepare_weather(weather)
    c = _fallow_core(wx, soil, [wx.idx(start)], [wx.idx(end)], depletion_frac)
    return FallowResult(
        start=start, end=end, bare_days=int(c["bare"][0]), erosive_bare_days=int(c["erosive"][0]),
        eta_mm=float(c["eta"][0]), precip_mm=float(c["precip"][0]), effective_precip_mm=float(c["peff"][0]),
        drainage_mm=float(c["dp"][0]), final_depletion_frac=float(c["f_end"][0]),
        final_depletion_mm=float(c["d_end"][0]))
