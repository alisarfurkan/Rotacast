"""Request models for the optional field inputs (CONTRACTS section 6.1): ``field_polygon`` and ``field_details``.

Validation errors surface as FastAPI's standard 422 with ``loc`` = ["body", "field_polygon" | "field_details", ...].
``normalize_polygon`` / ``normalize_details`` turn validated models into the compact dicts the report builder uses
(only given values are kept; ``null``, ``{}`` and ``[]`` mean "not given")."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from . import geometry
from .engine.rotations import IRRIGATION_EFFICIENCY
from .knowledge.crops import load_crops

TEXTURE_CLASSES = ("clay", "clay loam", "silty clay loam", "silty clay", "loam", "silt loam", "sandy loam",
                   "sandy clay loam", "sandy clay", "loamy sand", "sand", "silt")
EXCLUDE_REASONS = ("no_equipment", "no_buyer", "not_wanted")
IRRIGATION_METHODS = tuple(IRRIGATION_EFFICIENCY)
AREA_MIN_HA, AREA_MAX_HA = 0.01, 10_000.0
HISTORY_MIN_YEAR = 2000


def _known_crop(cid: Any) -> str:
    if not isinstance(cid, str) or cid not in load_crops():
        raise ValueError(f"unknown crop id: {cid!r}")
    return cid


def _empty(v: Any) -> bool:
    return v is None or (isinstance(v, (list, dict, tuple, str)) and len(v) == 0)


class FieldPolygon(BaseModel):
    """GeoJSON Polygon, WGS84 [lon, lat]; only the outer ring is used."""
    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[list[float]]]

    @field_validator("coordinates")
    @classmethod
    def _check_ring(cls, v):
        if not v or not v[0]:
            raise ValueError("coordinates must contain one outer ring")
        for p in v[0]:
            if len(p) < 2:
                raise ValueError("every position needs [lon, lat]")
            if not (-180 <= p[0] <= 180 and -90 <= p[1] <= 90):
                raise ValueError(f"position out of range (lon -180..180, lat -90..90): {p[:2]}")
        pts = geometry.open_ring(v[0])
        if len(pts) < 3:
            raise ValueError("polygon needs at least 3 distinct vertices")
        if geometry.is_self_intersecting(pts):
            raise ValueError("polygon must not self-intersect")
        a = geometry.area_ha(pts)
        if not (AREA_MIN_HA <= a <= AREA_MAX_HA):
            raise ValueError(f"polygon area {a:.3f} ha is outside {AREA_MIN_HA}-{AREA_MAX_HA:g} ha")
        return v


class SoilInput(BaseModel):
    texture_class: Literal[TEXTURE_CLASSES] | None = None
    clay_pct: float | None = Field(None, ge=0, le=100)
    sand_pct: float | None = Field(None, ge=0, le=100)
    soc_gkg: float | None = Field(None, ge=0, le=200)
    ph: float | None = Field(None, ge=3, le=10)

    @model_validator(mode="after")
    def _texture_sum(self):
        if self.clay_pct is not None and self.sand_pct is not None and self.clay_pct + self.sand_pct > 100 + 1e-9:
            raise ValueError("clay_pct + sand_pct must be <= 100")
        return self


class ExcludedCrop(BaseModel):
    crop_id: str
    reason: Literal["no_equipment", "no_buyer", "not_wanted"] = "not_wanted"

    @field_validator("crop_id")
    @classmethod
    def _crop(cls, v):
        return _known_crop(v)


class HistoryItem(BaseModel):
    year: int
    crop_id: str

    @field_validator("year")
    @classmethod
    def _year(cls, v):
        last = date.today().year - 1
        if not (HISTORY_MIN_YEAR <= v <= last):
            raise ValueError(f"year must be between {HISTORY_MIN_YEAR} and {last}")
        return v

    @field_validator("crop_id")
    @classmethod
    def _crop(cls, v):
        return _known_crop(v)


class FieldDetails(BaseModel):
    soil: SoilInput | None = None
    excluded_crops: list[ExcludedCrop] | None = None
    irrigation_method: Literal["flood", "furrow", "sprinkler", "drip"] | None = None
    water_quota_m3_yr: float | None = Field(None, ge=0, le=1e12)
    yields_t_ha: dict[str, Annotated[float, Field(gt=0, le=200)]] | None = None
    history: list[HistoryItem] | None = None
    irrigation_applied_m3_ha: dict[str, Annotated[float, Field(ge=0, le=30000)]] | None = None

    @field_validator("excluded_crops", mode="before")
    @classmethod
    def _excluded_forms(cls, v):
        """Accept plain crop ids and {crop_id, reason} objects."""
        if v is None:
            return v
        if not isinstance(v, list):
            raise ValueError("excluded_crops must be a list")
        return [{"crop_id": x} if isinstance(x, str) else x for x in v]

    @field_validator("yields_t_ha", "irrigation_applied_m3_ha")
    @classmethod
    def _crop_keys(cls, v):
        for k in (v or {}):
            _known_crop(k)
        return v

    @field_validator("history")
    @classmethod
    def _unique_years(cls, v):
        years = [h.year for h in (v or [])]
        if len(set(years)) != len(years):
            raise ValueError("history years must be unique")
        return v


def normalize_polygon(p: Any) -> dict | None:
    """-> {"ring": closed [[lon, lat], ...], "area_ha": float, "centroid": [lon, lat]} or None."""
    if _empty(p):
        return None
    m = p if isinstance(p, FieldPolygon) else FieldPolygon.model_validate(p)
    pts = geometry.open_ring(m.coordinates[0])
    cx, cy = (round(v, 6) for v in geometry.centroid(pts))  # ~0.1 m; also keeps the cache key stable
    return {"ring": geometry.closed_ring(m.coordinates[0]), "area_ha": geometry.area_ha(pts), "centroid": [cx, cy]}


def normalize_details(d: Any) -> dict:
    """Only the given values, in canonical form (sorted, deduplicated) so it can be part of the cache key."""
    if _empty(d):
        return {}
    m = d if isinstance(d, FieldDetails) else FieldDetails.model_validate(d)
    out: dict = {}
    if m.soil is not None:
        s = {k: v for k, v in m.soil.model_dump().items() if v is not None}
        if s:
            out["soil"] = s
    if m.excluded_crops:
        ex: dict[str, str] = {}
        for e in m.excluded_crops:
            ex.setdefault(e.crop_id, e.reason)
        out["excluded_crops"] = dict(sorted(ex.items()))
    if m.irrigation_method:
        out["irrigation_method"] = m.irrigation_method
    if m.water_quota_m3_yr is not None:
        out["water_quota_m3_yr"] = float(m.water_quota_m3_yr)
    if m.yields_t_ha:
        out["yields_t_ha"] = dict(sorted(m.yields_t_ha.items()))
    if m.history:
        out["history"] = sorted(({"year": h.year, "crop_id": h.crop_id} for h in m.history), key=lambda h: h["year"])
    if m.irrigation_applied_m3_ha:
        out["irrigation_applied_m3_ha"] = dict(sorted(m.irrigation_applied_m3_ha.items()))
    return out
