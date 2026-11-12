"""Synthetic Konya-like weather, soil and crops for the WP3b tests (no network, no other WP needed)."""
from __future__ import annotations

from types import SimpleNamespace as NS

import numpy as np
import pandas as pd

MONTH_RAIN_MM = [38, 30, 30, 38, 42, 25, 8, 6, 10, 25, 30, 40]  # ~320 mm/yr, winter/spring dominated


def make_weather(first_year=1990, last_year=2024, seed=1, rain_scale=1.0) -> pd.DataFrame:
    """Daily weather with seasonal sinusoids (Tmean 11 +/- 12 C, ET0 3.4 +/- 3.0 mm/day) and random rain."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(f"{first_year}-01-01", f"{last_year}-12-31", freq="D")
    doy = idx.dayofyear.to_numpy()
    phase = np.sin(2 * np.pi * (doy - 110) / 365.0)
    noise = rng.normal(0, 2.0, len(idx))
    tmean = 11.0 + 12.0 * phase + noise
    tmax = tmean + 6.5 + rng.normal(0, 1.0, len(idx))
    tmin = tmean - 6.5 + rng.normal(0, 1.0, len(idx))
    et0 = np.clip(3.4 + 3.0 * phase + rng.normal(0, 0.4, len(idx)), 0.2, None)
    month = idx.month.to_numpy()
    year_mult = dict(zip(range(first_year, last_year + 1), rng.lognormal(0, 0.25, last_year - first_year + 1)))
    mult = np.array([year_mult[y] for y in idx.year])
    dim = idx.days_in_month.to_numpy()
    p_wet = 0.22
    tot = np.array(MONTH_RAIN_MM)[month - 1] * mult * rain_scale
    mean_amt = tot / (dim * p_wet)
    wet = rng.random(len(idx)) < p_wet
    precip = np.where(wet, rng.exponential(1.0, len(idx)) * mean_amt, 0.0)
    return pd.DataFrame({"tmax": tmax, "tmin": tmin, "tmean": tmean, "precip": precip, "et0": et0}, index=idx.rename("date"))


def make_soil() -> NS:
    fc, wp = 0.34, 0.20
    return NS(fc=fc, wp=wp, taw_mm_per_m=(fc - wp) * 1000.0, clay_pct=35.0, sand_pct=30.0, silt_pct=35.0,
              soc_gkg=12.0, ph=7.8, bulk_density=1.3, texture_class="clay loam", source_id="soil_default")


def _crop(id_, en, tr, family, category, season, rule, thr, window, tbase, gdd, heat, frost, stage, days, kc, root, p, ky,
          n_fix, residue, rusle, groups, yields, price, irr_typ, legume=False):
    return NS(
        id=id_, name={"en": en, "tr": tr}, family=family, category=category, season=season,
        sowing=NS(rule=rule, threshold_c=thr, window_doy=tuple(window)),
        t_base_c=tbase, gdd_to_maturity=gdd, heat_stress_tmax_c=heat, frost_damage_tmin_c=frost,
        sensitive_stage=stage,
        fao56=NS(stage_days=tuple(days), kc=tuple(kc), root_depth_m=tuple(root), p=p, ky=ky),
        n_fixation_kg_ha=n_fix, residue_index=residue, rusle_c=rusle, disease_groups=list(groups),
        economics=NS(yield_t_ha={"rainfed": yields[0], "irrigated": yields[1]}, price_usd_t=price),
        irrigation_typical=irr_typ, drought_tolerance=3,
        is_legume=legume, is_cover=(category == "cover"), season_length_days=sum(days),
    )


def make_crops() -> dict:
    cs = [
        _crop("wheat_winter", "Winter wheat", "Kislik bugday", "Poaceae", "cereal", "winter", "tmean_below", 12, (270, 330),
              0, 2000, 32, -2, "mid", (140, 70, 45, 30), (0.4, 1.15, 0.25), (0.3, 1.5), 0.55, 1.0,
              0, 0.7, 0.25, ["cereal_root_rots", "cereal_rusts"], (2.5, 5.5), 280, "optional"),
        _crop("barley_winter", "Winter barley", "Kislik arpa", "Poaceae", "cereal", "winter", "tmean_below", 12, (270, 330),
              0, 1800, 30, -2, "mid", (130, 60, 40, 25), (0.3, 1.15, 0.25), (0.3, 1.5), 0.55, 0.9,
              0, 0.7, 0.25, ["cereal_root_rots", "barley_scald"], (2.2, 4.5), 250, "optional"),
        _crop("chickpea", "Chickpea", "Nohut", "Fabaceae", "legume", "spring", "tmean_above", 7, (75, 120),
              5, 1300, 35, -3, "mid", (25, 35, 40, 25), (0.4, 1.0, 0.35), (0.3, 1.0), 0.45, 0.85,
              40, 0.5, 0.45, ["legume_ascochyta", "legume_fusarium"], (1.1, 2.2), 750, "optional", legume=True),
        _crop("lentil", "Lentil", "Mercimek", "Fabaceae", "legume", "spring", "tmean_above", 6, (70, 115),
              5, 1250, 35, -3, "mid", (25, 30, 40, 25), (0.4, 1.1, 0.3), (0.3, 1.0), 0.5, 0.9,
              35, 0.5, 0.45, ["legume_ascochyta", "lentil_rust"], (1.0, 1.8), 650, "optional", legume=True),
        _crop("sugar_beet", "Sugar beet", "Seker pancari", "Amaranthaceae", "root", "spring", "tmean_above", 8, (85, 125),
              3, 2500, 38, -3, "mid", (30, 45, 90, 15), (0.35, 1.2, 0.7), (0.3, 1.2), 0.55, 1.0,
              0, 0.5, 0.35, ["beet_cercospora", "beet_nematodes"], (25.0, 60.0), 38, "required"),
        _crop("maize_grain", "Grain maize", "Misir", "Poaceae", "cereal", "summer", "tmean_above", 12, (105, 140),
              10, 1500, 35, -1.5, "mid", (25, 40, 45, 30), (0.3, 1.2, 0.6), (0.3, 1.2), 0.55, 1.25,
              0, 0.9, 0.3, ["maize_smut", "maize_borer"], (4.0, 11.0), 230, "required"),
        _crop("sunflower", "Sunflower", "Aycicegi", "Asteraceae", "oilseed", "summer", "tmean_above", 10, (95, 130),
              6, 1700, 35, -2, "mid", (25, 35, 45, 25), (0.35, 1.0, 0.35), (0.3, 1.5), 0.45, 0.95,
              0, 0.6, 0.4, ["sclerotinia", "sunflower_rust"], (1.4, 3.0), 450, "optional"),
        _crop("safflower", "Safflower", "Aspir", "Asteraceae", "oilseed", "spring", "tmean_above", 6, (75, 115),
              4, 1800, 36, -4, "mid", (25, 35, 55, 30), (0.3, 1.15, 0.25), (0.3, 1.5), 0.6, 0.8,
              0, 0.6, 0.35, ["safflower_rust"], (1.0, 2.2), 480, "optional"),
        _crop("vetch_cover", "Vetch cover", "Fig ortu", "Fabaceae", "cover", "winter", "tmean_below", 14, (250, 330),
              0, 1200, 35, -8, "mid", (40, 40, 40, 20), (0.4, 0.95, 0.4), (0.3, 0.8), 0.5, 0.5,
              30, 0.8, 0.10, ["vetch_diseases"], (0.0, 0.0), 0, "none", legume=True),
    ]
    return {c.id: c for c in cs}


FAKE_CLIMATE = {
    "frost": {"frost_free_days": {"p10": 160, "p50": 180, "p90": 200},
              "last_spring_doy": {"p50": 105}, "first_fall_doy": {"p50": 285}},
    "monthly_normals": [{"month": m, "tmin_c": t} for m, t in
                        zip(range(1, 13), [-6, -5, -2, 3, 7, 11, 14, 14, 10, 5, 0, -4])],
}
