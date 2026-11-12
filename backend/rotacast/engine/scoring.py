"""Scoring of rotation strategies relative to the baseline (current) rotation.

Each of the five dimensions is turned into a 0-100 sub-score where the baseline is exactly 50:

* "lower is better" (water, erosion, risk):   s = 50 + 50 * clip((b - x) / max(b, eps), -1, 1)
* "higher is better" (soil, income):          s = 50 + 50 * clip((x - b) / max(|b|, eps), -1, 1)

So halving water use vs. the baseline gives 75, using no water gives 100, doubling it gives 0.
The total is the priority-weighted mean of the sub-scores (weights are re-normalised to sum to 1).
"""
from __future__ import annotations

import numpy as np

DEFAULT_PRIORITIES = {"water": 0.3, "soil": 0.25, "income": 0.25, "erosion": 0.1, "risk": 0.1}
DIMENSIONS = ("water", "soil", "income", "erosion", "risk")
# floors that keep the relative change defined when the baseline value is ~0
_EPS = {"water": 500.0, "soil": 0.05, "income": 100.0, "erosion": 0.05, "risk": 0.05}
_LOWER_IS_BETTER = {"water", "erosion", "risk"}


def _p50(v) -> float:
    if isinstance(v, dict):
        return float(v.get("p50", 0.0))
    return float(v)


def soil_composite(ind: dict) -> float:
    """Soil-health composite 0-1: 40 % N balance (-10..+30 kg N/ha/yr -> 0..1), 30 % residue index,
    30 % share of the year with living soil cover."""
    n_term = float(np.clip((float(ind.get("n_balance_kg_ha_yr", 0.0)) + 10.0) / 40.0, 0.0, 1.0))
    res = float(np.clip(float(ind.get("residue_index", 0.0)), 0.0, 1.0))
    cover = float(np.clip(float(ind.get("soil_cover_days_yr", 0.0)) / 365.0, 0.0, 1.0))
    return 0.4 * n_term + 0.3 * res + 0.3 * cover


def risk_index(ind: dict) -> float:
    """Climate/yield risk 0-1: 30 % frost-hit probability, 30 % heat-hit probability, 40 % downside yield
    loss (1 - P10 of the yield ratio)."""
    yr10 = ind.get("yield_ratio", 1.0)
    yr10 = float(yr10.get("p10", 1.0)) if isinstance(yr10, dict) else float(yr10)
    r = 0.3 * float(ind.get("frost_risk", 0.0)) + 0.3 * float(ind.get("heat_risk", 0.0)) + 0.4 * (1.0 - yr10)
    return float(np.clip(r, 0.0, 1.0))


def dimension_values(ind: dict) -> dict:
    """Scalar value per scoring dimension from an ``indicators`` dict."""
    return {
        "water": _p50(ind.get("water_m3_ha_yr", 0.0)),
        "soil": soil_composite(ind),
        "income": _p50(ind.get("income_usd_ha_yr", 0.0)),
        "erosion": float(ind.get("erosion_rel", 1.0)),
        "risk": risk_index(ind),
    }


def _subscore(dim: str, x: float, b: float) -> float:
    eps = _EPS[dim]
    if dim in _LOWER_IS_BETTER:
        rel = (b - x) / max(b, eps)
    else:
        rel = (x - b) / max(abs(b), eps)
    return float(50.0 + 50.0 * np.clip(rel, -1.0, 1.0))


def score(indicators: dict, baseline: dict, priorities: dict | None = None) -> dict:
    """Return ``{"score": 0-100, "breakdown": {dim: 0-100}}`` for ``indicators`` relative to ``baseline``."""
    pr = dict(DEFAULT_PRIORITIES)
    if priorities:
        pr.update({k: float(v) for k, v in priorities.items() if k in pr})
    total_w = sum(max(v, 0.0) for v in pr.values())
    if total_w <= 0:
        pr, total_w = dict(DEFAULT_PRIORITIES), 1.0
    x, b = dimension_values(indicators), dimension_values(baseline)
    breakdown = {d: round(_subscore(d, x[d], b[d]), 2) for d in DIMENSIONS}
    total = sum(max(pr[d], 0.0) * breakdown[d] for d in DIMENSIONS) / total_w
    return {"score": round(float(total), 2), "breakdown": breakdown}
