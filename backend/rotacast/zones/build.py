"""Build ``data/zones/konya_zones.geojson`` from district boundaries, SRTM elevation, OSM lakes, MGM and NASA POWER.

Run via ``python backend/scripts/build_konya_zones.py``. Every network response is cached, so a re-run is offline.
"""
from __future__ import annotations

import json
import math
import re
from datetime import date

import numpy as np
from shapely import contains_xy
from shapely.affinity import scale
from shapely.geometry import Polygon, box, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from ..connectors import terrain
from ..connectors.cache import cached_get_bytes, cached_get_json
from . import RAW_CACHE, ZONES_DIR, boundary, mgm
from .definitions import (LAKE_BUFFER_KM, LAKE_EFFECT, LAKES, TOROS_ELEVATION_DISTRICTS, TOROS_MAX_LAT,
                          TOROS_MIN_ELEV_M, ZONES, district_zone_map)

GRID_DEG = 0.01
TERRAIN_ZOOM = 9                     # ~240 m/px at 38 N, plenty for 0.01 deg cells
KM_PER_DEG = 111.32
SIMPLIFY_DEG = 0.002                 # ~200 m
CLOSE_DEG = 0.02                     # ~2 km morphological smoothing of the Taurus elevation mask
MIN_PATCH_KM2 = 25.0                 # smaller elevation patches stay in their district's zone
NOMINATIM = "https://nominatim.openstreetmap.org/search"
POWER_CLIM = "https://power.larc.nasa.gov/api/temporal/climatology/point"
POWER_PARAMS = "T2M,T2M_MAX,T2M_MIN,FROST_DAYS,RH2M"
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


# --- geometry helpers ---------------------------------------------------------------------------------------------
def area_km2(g: BaseGeometry) -> float:
    """Approximate area (km^2) of a lon/lat geometry: lon scaled by cos(latitude of its centroid)."""
    if g.is_empty:
        return 0.0
    k = math.cos(math.radians(g.centroid.y))
    return g.area * k * KM_PER_DEG ** 2


def buffer_km(g: BaseGeometry, km: float) -> BaseGeometry:
    """Buffer a lon/lat geometry by ``km`` using a local equirectangular projection."""
    lat0 = g.centroid.y
    k = math.cos(math.radians(lat0))
    proj = scale(g, xfact=k * KM_PER_DEG, yfact=KM_PER_DEG, origin=(0, 0))
    return scale(proj.buffer(km), xfact=1 / (k * KM_PER_DEG), yfact=1 / KM_PER_DEG, origin=(0, 0))


def cells_to_geometry(lons: np.ndarray, lats: np.ndarray, step: float = GRID_DEG) -> BaseGeometry:
    """Union of grid-cell squares centred on (lons, lats)."""
    h = step / 2
    return unary_union([box(x - h, y - h, x + h, y + h) for x, y in zip(lons, lats)])


def fill_small_holes(p: BaseGeometry, min_km2: float = 25.0) -> BaseGeometry:
    """Remove interior rings smaller than ``min_km2`` from a polygon."""
    if p.geom_type != "Polygon":
        return p
    keep = [r for r in p.interiors if area_km2(Polygon(r)) >= min_km2]
    return Polygon(p.exterior, keep)


def grid_inside(geom: BaseGeometry, step: float = GRID_DEG) -> tuple[np.ndarray, np.ndarray]:
    minx, miny, maxx, maxy = geom.bounds
    xs = np.arange(math.floor(minx / step) * step + step / 2, maxx, step)
    ys = np.arange(math.floor(miny / step) * step + step / 2, maxy, step)
    gx, gy = np.meshgrid(xs, ys)
    gx, gy = gx.ravel(), gy.ravel()
    keep = contains_xy(geom, gx, gy)
    return gx[keep], gy[keep]


# --- data ---------------------------------------------------------------------------------------------------------
def elevation_at(lons: np.ndarray, lats: np.ndarray, z: int = TERRAIN_ZOOM) -> np.ndarray:
    """Elevation (m) at points from AWS terrain tiles (SRTM-derived), nearest pixel at zoom ``z``."""
    n = 2 ** z * terrain.TILE
    px = (lons + 180.0) / 360.0 * n
    s = np.sin(np.radians(lats))
    py = (0.5 - np.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    tx, ty = (px // terrain.TILE).astype(int), (py // terrain.TILE).astype(int)
    out = np.full(lons.shape, np.nan)
    for x, y in sorted(set(zip(tx.tolist(), ty.tolist()))):
        png = cached_get_bytes(f"{RAW_CACHE}/{terrain.SOURCE_ID}", terrain.URL.format(z=z, x=x, y=y))
        tile = terrain.decode_terrarium(png)
        sel = (tx == x) & (ty == y)
        ix = np.clip((px[sel] - x * terrain.TILE).astype(int), 0, terrain.TILE - 1)
        iy = np.clip((py[sel] - y * terrain.TILE).astype(int), 0, terrain.TILE - 1)
        out[sel] = tile[iy, ix]
    return out


def fetch_lake(name: str) -> BaseGeometry:
    r = cached_get_json("osm_lakes", NOMINATIM, {"q": name, "format": "geojson", "polygon_geojson": 1,
                                                 "limit": 3, "countrycodes": "tr"})
    geoms = [shape(f["geometry"]) for f in r["features"]
             if f["properties"].get("category") == "water" and "Konya" in f["properties"].get("display_name", "")]
    geoms = [g for g in geoms if g.geom_type in ("Polygon", "MultiPolygon")]
    if not geoms:
        raise RuntimeError(f"lake polygon not found: {name}")
    return max(geoms, key=lambda g: g.area)


def station_location(name: str) -> tuple[float, float]:
    r = cached_get_json("osm_places", NOMINATIM, {"q": f"{name}, Konya", "format": "json", "limit": 1,
                                                  "countrycodes": "tr"})
    if not r:
        raise RuntimeError(f"station town not found: {name}")
    return float(r[0]["lat"]), float(r[0]["lon"])


def power_climatology(lat: float, lon: float) -> dict:
    r = cached_get_json("nasa_power_climatology", POWER_CLIM, {"parameters": POWER_PARAMS, "community": "AG",
                                                               "longitude": round(lon, 3), "latitude": round(lat, 3),
                                                               "format": "JSON"})
    p = r["properties"]["parameter"]
    frost = p["FROST_DAYS"]
    return {
        "period": "-".join(re.findall(r"(?:19|20)\d\d", r.get("header", {}).get("range", ""))[:2]) or None,
        "grid": "0.5 x 0.625 deg (~50 km)",
        "t2m_mean_c": p["T2M"]["ANN"],
        "frost_days_yr": frost["ANN"],
        "spring_frost_days": round(sum(frost[m] for m in ("MAR", "APR", "MAY")), 1),
        "autumn_frost_days": round(sum(frost[m] for m in ("SEP", "OCT", "NOV")), 1),
        "hottest_month_mean_c": max(p["T2M"][m] for m in MONTHS),
        "coldest_month_mean_c": min(p["T2M"][m] for m in MONTHS),
        "rh2m_pct": p["RH2M"]["ANN"],
    }


# --- assembly -----------------------------------------------------------------------------------------------------
def build(verbose: bool = True) -> dict:
    log = print if verbose else (lambda *a, **k: None)
    adm1, cite1 = boundary.fetch_features("ADM1")
    province = boundary.konya_province(adm1)
    adm2, cite2 = boundary.fetch_features("ADM2")
    districts = boundary.konya_districts(adm2, province)
    dmap = district_zone_map()
    log(f"province + {len(districts)} districts")

    lakes = {n: fetch_lake(n) for n in LAKES}
    water = unary_union(list(lakes.values()))
    log("lakes:", {n: round(area_km2(g)) for n, g in lakes.items()})

    lons, lats = grid_inside(province)
    elev = elevation_at(lons, lats)
    log(f"grid: {lons.size} cells, elevation {np.nanmin(elev):.0f}-{np.nanmax(elev):.0f} m")

    zone_geom: dict[int, BaseGeometry] = {}
    for zid in {z["id"] for z in ZONES}:
        zone_geom[zid] = unary_union([g for n, g in districts if dmap[n] == zid])

    # Rule 1: Taurus highlands across district lines.
    ring = unary_union([g for n, g in districts if n in TOROS_ELEVATION_DISTRICTS])
    sel = (elev >= TOROS_MIN_ELEV_M) & (lats < TOROS_MAX_LAT) & contains_xy(ring, lons, lats)
    toros_extra = None
    if sel.any():
        raw = cells_to_geometry(lons[sel], lats[sel])
        # Morphological closing + opening (~2 km) and a minimum patch size remove speckle at the elevation threshold.
        smooth = raw.buffer(CLOSE_DEG).buffer(-2 * CLOSE_DEG).buffer(CLOSE_DEG)
        parts = [p for p in getattr(smooth, "geoms", [smooth]) if area_km2(p) >= MIN_PATCH_KM2]
        toros_extra = unary_union([fill_small_holes(p) for p in parts]).intersection(ring) if parts else None
    if toros_extra is not None and not toros_extra.is_empty:
        for zid in zone_geom:
            if zid != 1:
                zone_geom[zid] = zone_geom[zid].difference(toros_extra)
        zone_geom[1] = unary_union([zone_geom[1], toros_extra])
        log(f"Toros rule moved {area_km2(toros_extra):.0f} km2")

    # Rule 2: lake effect around Beyşehir Gölü (applied after rule 1, so the shore wins over the mountain).
    lake_zone = next(z["id"] for z in ZONES if z["key"] == "beysehir")
    shore = buffer_km(lakes[LAKE_EFFECT], LAKE_BUFFER_KM).intersection(province)
    for zid in zone_geom:
        if zid != lake_zone:
            zone_geom[zid] = zone_geom[zid].difference(shore)
    zone_geom[lake_zone] = unary_union([zone_geom[lake_zone], shore])

    # Clip to the province, remove lake surfaces, tidy.
    for zid in zone_geom:
        zone_geom[zid] = zone_geom[zid].intersection(province).difference(water).buffer(0)

    stations = mgm.fetch_all()
    features = []
    for z in ZONES:
        g = zone_geom[z["id"]]
        inside = contains_xy(g, lons, lats)
        e = elev[inside]
        st = []
        for code in z["stations"]:
            s = stations[code]
            lat, lon = station_location(s["name"])
            st.append({**s, "lat": lat, "lon": lon, "nasa_power": power_climatology(lat, lon)})
        share = sorted(((n, area_km2(dg.intersection(g)) / max(area_km2(g), 1e-9)) for n, dg in districts),
                       key=lambda t: -t[1])
        props = {k: z[k] for k in ("id", "key", "color", "name_tr", "name_en", "desc_tr", "desc_en")}
        props.update(
            area_km2=round(area_km2(g)),
            districts=[{"name": n, "share": round(s, 3)} for n, s in share if s >= 0.01],
            elevation_m={"p10": round(float(np.nanpercentile(e, 10))), "p50": round(float(np.nanpercentile(e, 50))),
                         "p90": round(float(np.nanpercentile(e, 90)))},
            stations=st,
        )
        features.append({"type": "Feature", "properties": props,
                         "geometry": mapping(g.simplify(SIMPLIFY_DEG, preserve_topology=True))})
        log(f"zone {z['id']} {z['key']:10} {props['area_km2']:6} km2  elev p50 {props['elevation_m']['p50']} m")

    meta = {
        "built": date.today().isoformat(),
        "method": "Expert zones on district boundaries, refined by SRTM elevation (Taurus rule) and a lake buffer; "
                  "profiled with MGM 1991-2020 classifications and NASA POWER 2001-2025 climatology.",
        "rules": {"toros_min_elev_m": TOROS_MIN_ELEV_M, "toros_max_lat": TOROS_MAX_LAT,
                  "toros_elevation_districts": sorted(TOROS_ELEVATION_DISTRICTS),
                  "lake_buffer_km": LAKE_BUFFER_KM, "lake_effect": LAKE_EFFECT},
        "sources": {
            "boundaries": [cite1["citation"], cite2["citation"]],
            "elevation": f"AWS Terrain Tiles (terrarium, SRTM-derived), zoom {TERRAIN_ZOOM}, sampled on a "
                         f"{GRID_DEG} deg grid: https://registry.opendata.aws/terrain-tiles/",
            "lakes": "OpenStreetMap contributors via Nominatim (ODbL): " + ", ".join(LAKES),
            "climate_classes": f"MGM İklim Sınıflandırmaları ({mgm.PERIOD}): {mgm.URL}",
            "climatology": "NASA POWER climatology API (MERRA-2, 0.5 x 0.625 deg), community AG: " + POWER_CLIM,
        },
    }
    zones_fc = {"type": "FeatureCollection", "meta": meta, "features": features}
    province_fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "Konya"},
         "geometry": mapping(province.simplify(SIMPLIFY_DEG / 2, preserve_topology=True))}]}
    lakes_fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": n},
         "geometry": mapping(g.intersection(province).simplify(SIMPLIFY_DEG, preserve_topology=True))}
        for n, g in lakes.items()]}
    districts_fc = boundary.to_feature_collection(
        [(n, g.intersection(province)) for n, g in districts], simplify=SIMPLIFY_DEG)

    ZONES_DIR.mkdir(parents=True, exist_ok=True)
    for name, fc in (("konya_zones", zones_fc), ("konya_boundary", province_fc), ("konya_lakes", lakes_fc),
                     ("konya_districts", districts_fc)):
        (ZONES_DIR / f"{name}.geojson").write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")),
                                                   encoding="utf-8")
    return {"zones": zones_fc, "province": province, "lakes": lakes, "districts": districts,
            "grid": (lons, lats, elev)}


def render_preview(result: dict, path, px_per_deg: int = 260) -> None:
    """Quick PNG of zones, district lines and lakes (for review, not for the app)."""
    from PIL import Image, ImageDraw

    minx, miny, maxx, maxy = result["province"].bounds
    k = math.cos(math.radians((miny + maxy) / 2))
    w, h = int((maxx - minx) * px_per_deg * k) + 20, int((maxy - miny) * px_per_deg) + 20
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)

    def pts(coords):
        return [((x - minx) * px_per_deg * k + 10, (maxy - y) * px_per_deg + 10) for x, y in coords]

    def polys(g):
        return [g] if g.geom_type == "Polygon" else list(getattr(g, "geoms", []))

    # Largest first, so zones that sit inside another zone's hole are painted on top.
    for f in sorted(result["zones"]["features"], key=lambda f: -f["properties"]["area_km2"]):
        for p in polys(shape(f["geometry"])):
            d.polygon(pts(p.exterior.coords), fill=f["properties"]["color"])
    for _, g in result["districts"]:
        for p in polys(g.intersection(result["province"])):
            d.line(pts(p.exterior.coords), fill="#555555", width=1)
    for g in result["lakes"].values():
        for p in polys(g.intersection(result["province"])):
            d.polygon(pts(p.exterior.coords), fill="#9ecae1", outline="#3182bd")
    for f in result["zones"]["features"]:
        c = shape(f["geometry"]).representative_point()
        (x, y), = pts([(c.x, c.y)])
        d.text((x - 4, y - 6), str(f["properties"]["id"]), fill="black")
    img.save(path)
