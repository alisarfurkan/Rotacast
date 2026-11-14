"""FastAPI app: POST /api/field/analyze, GET /api/crops, GET /api/health. Run: uvicorn rotacast.api.main:app --port 8000"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from ..field_inputs import FieldDetails, FieldPolygon
from ..knowledge.crops import load_crops
from ..report import DEFAULT_ROTATION, get_field_report

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
    field_polygon: FieldPolygon | None = None   # CONTRACTS section 6.1
    field_details: FieldDetails | None = None

    @field_validator("field_polygon", "field_details", mode="before")
    @classmethod
    def _empty_is_none(cls, v):  # CONTRACTS 6.1: null, {} and [] mean "not given"
        return None if v in ({}, []) else v


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/crops")
def crops():
    return [{"id": c.id, "name": dict(c.name), "category": c.category, "season": c.season,
             "irrigation_typical": c.irrigation_typical} for c in load_crops().values()]


@app.post("/api/field/analyze")
def analyze(req: AnalyzeRequest):
    try:
        return JSONResponse(get_field_report(req.model_dump()))
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
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
