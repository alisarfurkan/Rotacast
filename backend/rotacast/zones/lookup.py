"""Runtime lookups against the prebuilt Konya zone files (``data/zones/*.geojson``)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.prepared import prep

from . import ZONES_DIR


@lru_cache(maxsize=4)
def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def zones_geojson(zones_dir: Path = ZONES_DIR) -> dict:
    return _load(str(zones_dir / "konya_zones.geojson"))


def boundary_geojson(zones_dir: Path = ZONES_DIR) -> dict:
    return _load(str(zones_dir / "konya_boundary.geojson"))


def lakes_geojson(zones_dir: Path = ZONES_DIR) -> dict:
    return _load(str(zones_dir / "konya_lakes.geojson"))


@lru_cache(maxsize=4)
def _prepared(zones_dir: str) -> tuple:
    d = Path(zones_dir)
    province = prep(shape(boundary_geojson(d)["features"][0]["geometry"]))
    lakes = [(f["properties"]["name"], prep(shape(f["geometry"]))) for f in lakes_geojson(d)["features"]]
    zones = [(f["properties"], prep(shape(f["geometry"]))) for f in zones_geojson(d)["features"]]
    return province, lakes, zones


def inside_konya(lat: float, lon: float, zones_dir: Path = ZONES_DIR) -> bool:
    province, _, _ = _prepared(str(zones_dir))
    return province.contains(Point(lon, lat))


def lake_at(lat: float, lon: float, zones_dir: Path = ZONES_DIR) -> str | None:
    _, lakes, _ = _prepared(str(zones_dir))
    p = Point(lon, lat)
    return next((name for name, g in lakes if g.contains(p)), None)


def zone_at(lat: float, lon: float, zones_dir: Path = ZONES_DIR) -> dict | None:
    """Properties of the zone containing (lat, lon); ``None`` outside Konya or on a lake.

    Points that fall in a simplification gap between two zones (a few hundred metres at most) get the nearest zone.
    """
    province, _, zones = _prepared(str(zones_dir))
    p = Point(lon, lat)
    if not province.contains(p) or lake_at(lat, lon, zones_dir):
        return None
    for props, g in zones:
        if g.contains(p):
            return props
    best = min(zones_geojson(zones_dir)["features"], key=lambda f: shape(f["geometry"]).distance(p))
    return best["properties"]
