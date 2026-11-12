"""Soil properties: ISRIC SoilGrids v2 REST (source_id ``soilgrids``) with a documented regional fallback.

https://rest.isric.org/soilgrids/v2.0/properties/query  (CC BY 4.0, no auth; flaky, hence the fallback).
Layers 0-5, 5-15, 15-30 cm are depth-weighted (5:10:15 cm) to 0-30 cm. Raw values are divided by each
layer's ``unit_measure.d_factor`` (clay/sand/silt g/kg -> %, soc dg/kg -> g/kg, phh2o pH*10 -> pH,
bdod cg/cm3 -> g/cm3 (== kg/dm3)). Field capacity / wilting point: Saxton & Rawls (2006), Soil Sci. Soc.
Am. J. 70:1569-1578, eqs. 1-2 (matric potential -33 kPa and -1500 kPa), OM = SOC x 1.724.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from .cache import cached_get_json

log = logging.getLogger(__name__)

SOURCE_ID = "soilgrids"
DEFAULT_SOURCE_ID = "soil_default"
URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
PROPERTIES = ["clay", "sand", "silt", "soc", "phh2o", "bdod"]
DEPTHS = {"0-5cm": 5.0, "5-15cm": 10.0, "15-30cm": 15.0}  # label -> thickness (cm)


@dataclass
class SoilProfile:
    """0-30 cm depth-weighted soil profile."""
    clay_pct: float
    sand_pct: float
    silt_pct: float
    soc_gkg: float           # soil organic carbon, g/kg
    ph: float
    bulk_density: float      # g/cm3
    texture_class: str       # USDA texture class
    fc: float                # field capacity, m3/m3 (Saxton & Rawls 2006, -33 kPa)
    wp: float                # wilting point, m3/m3 (Saxton & Rawls 2006, -1500 kPa)
    taw_mm_per_m: float      # (fc - wp) * 1000
    source_id: str           # "soilgrids" | "soil_default"


def usda_texture_class(sand: float, silt: float, clay: float) -> str:
    """USDA texture triangle class from sand/silt/clay percentages (standard threshold cascade)."""
    if silt + 1.5 * clay < 15:
        return "sand"
    if silt + 1.5 * clay >= 15 and silt + 2 * clay < 30:
        return "loamy sand"
    if (7 <= clay < 20 and sand > 52 and silt + 2 * clay >= 30) or (clay < 7 and silt < 50 and silt + 2 * clay >= 30):
        return "sandy loam"
    if 7 <= clay < 27 and 28 <= silt < 50 and sand <= 52:
        return "loam"
    if (silt >= 50 and 12 <= clay < 27) or (50 <= silt < 80 and clay < 12):
        return "silt loam"
    if silt >= 80 and clay < 12:
        return "silt"
    if 20 <= clay < 35 and silt < 28 and sand > 45:
        return "sandy clay loam"
    if 27 <= clay < 40 and 20 < sand <= 45:
        return "clay loam"
    if 27 <= clay < 40 and sand <= 20:
        return "silty clay loam"
    if clay >= 35 and sand > 45:
        return "sandy clay"
    if clay >= 40 and silt >= 40:
        return "silty clay"
    if clay >= 40:
        return "clay"
    return "loam"


def saxton_rawls_2006(sand_pct: float, clay_pct: float, soc_gkg: float) -> tuple[float, float]:
    """Return (fc, wp) in m3/m3 from sand %, clay %, SOC g/kg (Saxton & Rawls 2006, eqs. 1-2)."""
    s, c = sand_pct / 100.0, clay_pct / 100.0
    om = soc_gkg * 1.724 / 10.0  # % organic matter
    t1500 = -0.024 * s + 0.487 * c + 0.006 * om + 0.005 * s * om - 0.013 * c * om + 0.068 * s * c + 0.031
    wp = t1500 + (0.14 * t1500 - 0.02)
    t33 = -0.251 * s + 0.195 * c + 0.011 * om + 0.006 * s * om - 0.027 * c * om + 0.452 * s * c + 0.299
    fc = t33 + (1.283 * t33 ** 2 - 0.374 * t33 - 0.015)
    return fc, wp


def build_profile(clay: float, sand: float, silt: float, soc: float, ph: float, bd: float,
                  source_id: str) -> SoilProfile:
    fc, wp = saxton_rawls_2006(sand, clay, soc)
    return SoilProfile(clay_pct=clay, sand_pct=sand, silt_pct=silt, soc_gkg=soc, ph=ph,
                       bulk_density=bd, texture_class=usda_texture_class(sand, silt, clay),
                       fc=fc, wp=wp, taw_mm_per_m=(fc - wp) * 1000.0, source_id=source_id)


def parse_soilgrids(payload: dict) -> SoilProfile:
    """Parse a SoilGrids v2 query response into a depth-weighted 0-30 cm profile."""
    out: dict[str, float] = {}
    for layer in payload["properties"]["layers"]:
        d_factor = layer["unit_measure"]["d_factor"] or 1
        num = den = 0.0
        for dep in layer["depths"]:
            v = dep["values"].get("mean")
            w = DEPTHS.get(dep["label"])
            if v is None or w is None:
                continue
            num += w * v / d_factor
            den += w
        if den == 0:
            raise ValueError(f"no data for {layer['name']}")
        out[layer["name"]] = num / den
    return build_profile(out["clay"], out["sand"], out["silt"], out["soc"], out["phh2o"],
                         out["bdod"], SOURCE_ID)


# Regional fallback. Konya Plain (Cumra): SoilGrids v2 at 37.60N 32.75E (queried 2026-11-12) gave
# clay 33.8 %, sand 18.9 %, silt 47.3 %, SOC 16.7 g/kg, pH 7.4, BD 1.43 g/cm3 (silty clay loam). Turkish
# soil surveys describe the Konya alluvial plain as calcareous, fine-textured clay-loam soils with low
# organic matter (~1-2 %). Chosen default is a deliberately conservative clay loam: clay 33, sand 32,
# silt 35, SOC 10 g/kg, pH 7.6, BD 1.40 g/cm3 -- an approximation, not a measurement.
KONYA_DEFAULT = dict(clay=33.0, sand=32.0, silt=35.0, soc=10.0, ph=7.6, bd=1.40)
# Generic loam elsewhere (USDA loam centroid; SOC 12 g/kg ~ 2 % OM; neutral pH).
GENERIC_DEFAULT = dict(clay=20.0, sand=40.0, silt=40.0, soc=12.0, ph=6.8, bd=1.35)


def default_profile(lat: float, lon: float) -> SoilProfile:
    """Documented regional default (``soil_default``): clay loam for the Konya region, else loam."""
    in_konya = 36.5 <= lat <= 39.5 and 31.0 <= lon <= 35.0
    return build_profile(**(KONYA_DEFAULT if in_konya else GENERIC_DEFAULT), source_id=DEFAULT_SOURCE_ID)


def fetch_soil(lat: float, lon: float) -> SoilProfile:
    """0-30 cm soil profile at a point. Tries SoilGrids (with retries), then its disk cache, then the
    regional default. Never raises."""
    params = {"lon": lon, "lat": lat, "property": PROPERTIES, "depth": list(DEPTHS), "value": "mean"}
    try:
        return parse_soilgrids(cached_get_json(SOURCE_ID, URL, params, timeout=60, retries=3))
    except Exception as exc:  # noqa: BLE001 - contract: never raise
        log.warning("SoilGrids unavailable (%s); using regional default", exc)
        return default_profile(lat, lon)
