"""Konya province + district boundaries from geoBoundaries (gbOpen, TUR ADM1/ADM2).

Raw (large) GeoJSON is cached under ``data/cache/_raw/geoboundaries`` (gitignored); API metadata under
``data/cache/geoboundaries``. Network use goes through :mod:`rotacast.connectors.cache`.
"""
from __future__ import annotations

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from ..connectors.cache import cached_get_json
from . import RAW_CACHE

API = "https://www.geoboundaries.org/api/current/gbOpen/TUR/{level}/"
META_SOURCE = "geoboundaries"
RAW_SOURCE = f"{RAW_CACHE}/geoboundaries"
SIMPLIFY_DEG = 0.001  # ~100 m


def fetch_meta(level: str) -> dict:
    return cached_get_json(META_SOURCE, API.format(level=level))


def fetch_features(level: str) -> tuple[list[dict], dict]:
    """(features, citation) for ADM1 / ADM2 of Turkey."""
    meta = fetch_meta(level)
    gj = cached_get_json(RAW_SOURCE, meta["gjDownloadURL"], timeout=300)
    cite = {k: meta.get(k) for k in ("boundaryID", "boundaryYearRepresented", "boundarySource", "boundaryLicense",
                                     "licenseSource", "boundarySourceURL", "sourceDataUpdateDate", "gjDownloadURL")}
    cite["citation"] = ("geoBoundaries gbOpen TUR %s (Runfola et al. 2020, https://www.geoboundaries.org); "
                        "source %s; license %s" % (level, meta.get("boundarySource"), meta.get("boundaryLicense")))
    return gj["features"], cite


def _name(f: dict) -> str:
    p = f.get("properties", {})
    return str(p.get("shapeName") or p.get("name") or "").strip()


def konya_province(features: list[dict]) -> BaseGeometry:
    geoms = [shape(f["geometry"]) for f in features if _name(f).lower() in {"konya", "konya province"}]
    if not geoms:
        names = sorted({_name(f) for f in features})
        raise RuntimeError(f"Konya not found among ADM1 names: {names[:90]}")
    return unary_union(geoms)


def konya_districts(features: list[dict], province: BaseGeometry, min_inside: float = 0.5) -> list[tuple[str, BaseGeometry]]:
    """ADM2 units whose area lies >= ``min_inside`` inside the province polygon."""
    out = []
    for f in features:
        g = shape(f["geometry"])
        if not g.is_valid:
            g = g.buffer(0)
        if g.area > 0 and g.intersection(province).area / g.area >= min_inside:
            out.append((_name(f), g))
    return out


def to_feature_collection(items: list[tuple[str, BaseGeometry]], simplify: float = SIMPLIFY_DEG) -> dict:
    from shapely.geometry import mapping
    feats = [{"type": "Feature", "properties": {"name": n},
              "geometry": mapping(g.simplify(simplify, preserve_topology=True))} for n, g in items]
    return {"type": "FeatureCollection", "features": feats}
