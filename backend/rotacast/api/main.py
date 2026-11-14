"""FastAPI app: POST /api/field/analyze, GET /api/zones, /api/crops, /api/basin/konya, /api/health.

Run: uvicorn rotacast.api.main:app --port 8000
"""
from __future__ import annotations

import json
import mimetypes
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..knowledge.crops import load_crops
from ..report import DEFAULT_ROTATION, get_field_report
from ..zones import lookup as zone_lookup

app = FastAPI(title="Rotacast API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


class RotationStepIn(BaseModel):
    crop_id: str
    irrigation: str = "none"


class Constraints(BaseModel):
    water_access: str = "limited"
    max_irrigated_share: float = 0.5


class Priorities(BaseModel):
    water: float = 0.3
    soil: float = 0.25
    income: float = 0.25
    erosion: float = 0.1
    risk: float = 0.1


class Scenario(BaseModel):
    delta_t_c: float = 0.0
    precip_change_pct: float = 0.0


class AnalyzeRequest(BaseModel):
    lat: float = Field(37.60, ge=-90, le=90)
    lon: float = Field(32.75, ge=-180, le=180)
    current_rotation: list[RotationStepIn] = [RotationStepIn(**s) for s in DEFAULT_ROTATION]
    constraints: Constraints = Constraints()
    priorities: Priorities = Priorities()
    scenario: Scenario = Scenario()
    lang: str = "tr"


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/crops")
def crops():
    return [{"id": c.id, "name": dict(c.name), "category": c.category, "season": c.season,
             "irrigation_typical": c.irrigation_typical} for c in load_crops().values()]


@app.get("/api/zones")
def zones():
    """Konya agro-microclimate zones, province boundary and lakes (scripts/build_konya_zones.py; CONTRACTS.md §6)."""
    try:
        return JSONResponse({"zones": zone_lookup.zones_geojson(), "boundary": zone_lookup.boundary_geojson(),
                             "lakes": zone_lookup.lakes_geojson()})
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="zones not built")


def field_zone(lat: float, lon: float, field_elevation_m: float | None) -> dict:
    """Zone block attached to a field report. Raises HTTP 422 outside Konya or on a lake."""
    if not zone_lookup.inside_konya(lat, lon):
        raise HTTPException(status_code=422, detail={
            "code": "outside_konya", "message": "Rotacast currently covers Konya province only."})
    lake = zone_lookup.lake_at(lat, lon)
    if lake:
        raise HTTPException(status_code=422, detail={"code": "on_lake", "lake": lake,
                                                     "message": f"The point is on the surface of {lake}."})
    z = zone_lookup.zone_at(lat, lon)
    band = z["elevation_m"]
    position = None
    if field_elevation_m is not None:
        if field_elevation_m < (band["p10"] + band["p50"]) / 2:
            position = "low"
        elif field_elevation_m > (band["p50"] + band["p90"]) / 2:
            position = "high"
        else:
            position = "mid"
    return {"id": z["id"], "key": z["key"], "color": z["color"],
            "name": {"tr": z["name_tr"], "en": z["name_en"]}, "desc": {"tr": z["desc_tr"], "en": z["desc_en"]},
            "elevation_m": band, "field_elevation_m": field_elevation_m, "elevation_position": position,
            "stations": z["stations"]}


@app.post("/api/field/analyze")
def analyze(req: AnalyzeRequest):
    field_zone(req.lat, req.lon, None)  # reject points outside Konya before any data download
    try:
        report = get_field_report(req.model_dump())
        report = {**report, "zone": field_zone(req.lat, req.lon, report.get("location", {}).get("elevation_m"))}
        return JSONResponse(report)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:  # data source failure
        raise HTTPException(status_code=502, detail=f"analysis failed: {type(e).__name__}: {e}")


_BASIN = Path(__file__).resolve().parents[3] / "data" / "demo" / "basin_report_konya.json"


@app.get("/api/basin/konya")
def basin_konya():
    """Precomputed Konya Closed Basin scenario report (scripts/build_basin_report.py; schema CONTRACTS.md §5)."""
    if not _BASIN.is_file():
        raise HTTPException(status_code=404, detail="basin report not built")
    return JSONResponse(json.loads(_BASIN.read_text(encoding="utf-8")))


_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"
# Windows' registry often lacks .mjs; without this the MapLibre worker is served as text/plain and GeoJSON layers fail.
mimetypes.add_type("text/javascript", ".mjs")
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
