"""Water-only model of specialty crops (cumin, fenugreek): FAO-56 daily balance with a fixed calendar.

Only the water need is modelled (METHODS section 7.2): ETc, rain-fed water use and the net irrigation that
full irrigation would add. Income, yield ratio and frost/heat risk are not computed (no verified price, Ky or
temperature thresholds). The existing ``waterbalance._season_core`` does the work; a lightweight crop-like
object with a fixed season replaces the GDD-scaled one (``fixed_season`` flag, see ``season_lengths``).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from . import waterbalance as wb

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "specialty_water.yaml"
FALLOW_START_DOY = 274      # 1 Oct before sowing: bare-soil balance gives the soil water at sowing
FALLOW_START_DEPLETION = 0.5
DEFAULT_START_DEPLETION = 0.3  # used when the weather does not cover the previous autumn


@dataclass(frozen=True)
class _Fao56:
    stage_days: tuple
    kc: tuple
    root_depth_m: tuple
    p: float
    ky: float = 0.0     # unused: no yield ratio is computed


@dataclass(frozen=True)
class WaterCrop:
    """Crop-like object understood by ``waterbalance._season_core`` (fixed season, no yield/temperature model)."""
    id: str
    name: dict
    fao56: _Fao56
    sow_doy: int
    harvest_doy: int
    sources: tuple
    practice: str
    stage_basis: str
    fixed_season: bool = True
    t_base_c: float = 0.0
    gdd_to_maturity: float = 0.0
    heat_stress_tmax_c: float = 99.0     # no thresholds: heat/frost counters stay 0 and are never reported
    frost_damage_tmin_c: float = -99.0
    sensitive_stage: str = "mid"

    @property
    def season_days(self) -> int:
        return self.harvest_doy - self.sow_doy


def scale_stages(proportions, total: int) -> tuple:
    """Stage lengths (days) proportional to ``proportions`` that sum to exactly ``total`` (largest remainder)."""
    p = np.asarray(proportions, float)
    raw = p / p.sum() * total
    n = np.floor(raw).astype(int)
    for i in np.argsort(-(raw - n))[: int(total - n.sum())]:
        n[i] += 1
    return tuple(int(x) for x in n)


def load_water_models(path: Path = DEFAULT_PATH) -> dict[str, WaterCrop]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    out = {}
    for mid, d in raw.items():
        total = int(d["harvest_doy"]) - int(d["sow_doy"])
        out[mid] = WaterCrop(
            id=mid, name=dict(d["name"]),
            fao56=_Fao56(scale_stages(d["stage_days"], total), tuple(float(x) for x in d["kc"]),
                         tuple(float(x) for x in d["root_depth_m"]), float(d["p"])),
            sow_doy=int(d["sow_doy"]), harvest_doy=int(d["harvest_doy"]), sources=tuple(d["sources"]),
            practice=d["practice"], stage_basis=d["stage_basis"])
    return out


def _band(x) -> dict:
    a = np.asarray(x, float)
    p10, p50, p90 = np.percentile(a, [10, 50, 90]) if a.size else (0.0, 0.0, 0.0)
    return {"p10": float(p10), "p50": float(p50), "p90": float(p90)}


def simulate_specialty_water(crop: WaterCrop, weather, soil, years) -> dict:
    """Season water bands over ``years`` (sowing in each year at ``crop.sow_doy``).

    Returns bands (p10/p50/p90 across years) of
    * ``etc_mm``                  unstressed crop water need over the season (sum of Kc x ET0),
    * ``rainfed_eta_mm``          water actually used rain-fed (rain and stored soil water),
    * ``rain_eff_mm``             effective rain over the season,
    * ``irr_need_full_m3_ha``     net irrigation that full irrigation adds to avoid stress (1 mm = 10 m3/ha),
    * ``rainfed_irrigation_m3_ha`` irrigation water of the documented practice (rain-fed: 0),
    plus ``season`` (sowing/harvest day of year, days) and ``n_years``."""
    wx = wb.prepare_weather(weather)
    years = np.array([int(y) for y in years], dtype=np.int64)
    sow = wb._doy_idx(wx, years, crop.sow_doy)
    ok = (sow >= 0) & (sow + crop.season_days <= wx.n)
    years, sow = years[ok], sow[ok]
    if sow.size == 0:
        raise wb.WeatherCoverageError(f"no year of the weather series covers the {crop.id} season")
    # soil water at sowing: bare-soil balance from 1 October of the previous year (existing fallow machinery)
    start = wb._doy_idx(wx, years - 1, FALLOW_START_DOY)
    f0 = np.full(sow.size, DEFAULT_START_DEPLETION)
    cov = start >= 0
    if cov.any():
        f0[cov] = wb._fallow_core(wx, soil, start[cov], sow[cov], FALLOW_START_DEPLETION)["f_end"]
    rain = wb._season_core(crop, wx, soil, sow, "none", f0)
    full = wb._season_core(crop, wx, soil, sow, "full", f0)
    return {
        "etc_mm": _band(rain["etc"]), "rainfed_eta_mm": _band(rain["eta"]), "rain_eff_mm": _band(rain["peff"]),
        "irr_need_full_m3_ha": _band(full["irr"] * 10.0), "rainfed_irrigation_m3_ha": _band(np.zeros(sow.size)),
        "season": {"sow_doy": crop.sow_doy, "harvest_doy": crop.harvest_doy, "days": crop.season_days},
        "n_years": int(sow.size), "years": [int(y) for y in years],
    }


_MODELS: dict[str, WaterCrop] | None = None


def water_models() -> dict[str, WaterCrop]:
    """The packaged water-only models (loaded once)."""
    global _MODELS
    if _MODELS is None:
        _MODELS = load_water_models()
    return _MODELS
