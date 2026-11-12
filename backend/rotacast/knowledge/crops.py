"""Crop knowledge base loader (docs/CONTRACTS.md section 2)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PATH = Path(__file__).with_name("crops.yaml")

FAMILIES = {
    "Poaceae", "Fabaceae", "Asteraceae", "Brassicaceae", "Amaranthaceae", "Solanaceae",
    "Malvaceae", "Cucurbitaceae", "Apiaceae", "Linaceae", "Polygonaceae", "Lamiaceae",
}
CATEGORIES = {"cereal", "legume", "oilseed", "root", "forage", "cover", "fiber"}
SEASONS = {"winter", "spring", "summer"}
SOWING_RULES = {"tmean_below", "tmean_above"}
STAGES = {"ini", "dev", "mid", "late"}
ROOT_TYPES = {"fibrous", "tap", "deep_tap"}
IRRIGATION = {"none", "optional", "required"}


@dataclass(frozen=True)
class Sowing:
    rule: str
    threshold_c: float
    window_doy: tuple[int, int]


@dataclass(frozen=True)
class Fao56:
    stage_days: tuple[int, int, int, int]
    kc: tuple[float, float, float]
    root_depth_m: tuple[float, float]
    p: float
    ky: float


@dataclass(frozen=True)
class Economics:
    yield_t_ha: dict
    price_usd_t: float


@dataclass(frozen=True)
class Crop:
    id: str
    name: dict
    family: str
    category: str
    season: str
    sowing: Sowing
    t_base_c: float
    gdd_to_maturity: float
    heat_stress_tmax_c: float
    frost_damage_tmin_c: float
    sensitive_stage: str
    fao56: Fao56
    drought_tolerance: int
    n_fixation_kg_ha: float
    residue_index: float
    rusle_c: float
    root_type: str
    forage_value: int
    disease_groups: tuple[str, ...]
    economics: Economics
    irrigation_typical: str
    notes: dict
    sources: tuple[str, ...]
    perennial_years: int | None = None

    @property
    def season_length_days(self) -> int:
        return sum(self.fao56.stage_days)

    @property
    def is_legume(self) -> bool:
        return self.category == "legume" or self.n_fixation_kg_ha > 0

    @property
    def is_cover(self) -> bool:
        return self.category == "cover"


def _err(cid: str, field: str, msg: str) -> ValueError:
    return ValueError(f"crop '{cid}': field '{field}': {msg}")


def _get(d: dict, key: str, cid: str, path: str | None = None) -> Any:
    if not isinstance(d, dict) or key not in d or d[key] is None:
        raise _err(cid, path or key, "missing required field")
    return d[key]


def _num(v: Any, cid: str, field: str, lo: float, hi: float) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise _err(cid, field, f"expected a number, got {v!r}")
    if not lo <= v <= hi:
        raise _err(cid, field, f"{v} outside [{lo}, {hi}]")
    return v


def _choice(v: Any, allowed: set, cid: str, field: str) -> str:
    if v not in allowed:
        raise _err(cid, field, f"{v!r} not in {sorted(allowed)}")
    return v


def _seq(v: Any, n: int, cid: str, field: str) -> list:
    if not isinstance(v, (list, tuple)) or len(v) != n:
        raise _err(cid, field, f"expected a list of {n} values")
    return list(v)


def _bilingual(v: Any, cid: str, field: str) -> dict:
    if not isinstance(v, dict) or not all(isinstance(v.get(k), str) and v[k].strip() for k in ("en", "tr")):
        raise _err(cid, field, "needs non-empty 'en' and 'tr' strings")
    return dict(v)


def _parse(raw: dict) -> Crop:
    cid = raw.get("id") if isinstance(raw, dict) else None
    if not isinstance(cid, str) or not cid:
        raise ValueError(f"crop entry without a valid 'id': {raw!r}")
    g = lambda k: _get(raw, k, cid)  # noqa: E731

    sw = g("sowing")
    win = _seq(_get(sw, "window_doy", cid, "sowing.window_doy"), 2, cid, "sowing.window_doy")
    for w in win:
        _num(w, cid, "sowing.window_doy", 1, 366)
    if win[0] > win[1]:
        raise _err(cid, "sowing.window_doy", "start after end")
    sowing = Sowing(
        rule=_choice(_get(sw, "rule", cid, "sowing.rule"), SOWING_RULES, cid, "sowing.rule"),
        threshold_c=_num(_get(sw, "threshold_c", cid, "sowing.threshold_c"), cid, "sowing.threshold_c", -10, 40),
        window_doy=(int(win[0]), int(win[1])),
    )

    f = g("fao56")
    days = _seq(_get(f, "stage_days", cid, "fao56.stage_days"), 4, cid, "fao56.stage_days")
    for d in days:
        _num(d, cid, "fao56.stage_days", 1, 400)
    kc = _seq(_get(f, "kc", cid, "fao56.kc"), 3, cid, "fao56.kc")
    for k in kc:
        _num(k, cid, "fao56.kc", 0, 1.5)
    rd = _seq(_get(f, "root_depth_m", cid, "fao56.root_depth_m"), 2, cid, "fao56.root_depth_m")
    for r in rd:
        _num(r, cid, "fao56.root_depth_m", 0.05, 4)
    if rd[0] > rd[1]:
        raise _err(cid, "fao56.root_depth_m", "min greater than max")
    fao = Fao56(
        stage_days=tuple(int(d) for d in days),
        kc=tuple(float(k) for k in kc),
        root_depth_m=(float(rd[0]), float(rd[1])),
        p=float(_num(_get(f, "p", cid, "fao56.p"), cid, "fao56.p", 0, 1)),
        ky=float(_num(_get(f, "ky", cid, "fao56.ky"), cid, "fao56.ky", 0, 2)),
    )

    e = g("economics")
    y = _get(e, "yield_t_ha", cid, "economics.yield_t_ha")
    if not isinstance(y, dict):
        raise _err(cid, "economics.yield_t_ha", "expected mapping")
    for k in ("rainfed", "irrigated"):
        _num(_get(y, k, cid, f"economics.yield_t_ha.{k}"), cid, f"economics.yield_t_ha.{k}", 0, 500)
    econ = Economics(
        yield_t_ha={k: float(v) for k, v in y.items()},
        price_usd_t=float(_num(_get(e, "price_usd_t", cid, "economics.price_usd_t"), cid, "economics.price_usd_t", 0, 1e5)),
    )

    dg = g("disease_groups")
    if not isinstance(dg, list) or not all(isinstance(x, str) for x in dg):
        raise _err(cid, "disease_groups", "expected a list of strings")
    src = g("sources")
    if not isinstance(src, list) or not src or not all(isinstance(x, str) for x in src):
        raise _err(cid, "sources", "expected a non-empty list of source ids")

    py = raw.get("perennial_years")
    if py is not None:
        py = int(_num(py, cid, "perennial_years", 1, 50))

    return Crop(
        id=cid,
        name=_bilingual(g("name"), cid, "name"),
        family=_choice(g("family"), FAMILIES, cid, "family"),
        category=_choice(g("category"), CATEGORIES, cid, "category"),
        season=_choice(g("season"), SEASONS, cid, "season"),
        sowing=sowing,
        t_base_c=float(_num(g("t_base_c"), cid, "t_base_c", -5, 20)),
        gdd_to_maturity=float(_num(g("gdd_to_maturity"), cid, "gdd_to_maturity", 1, 10000)),
        heat_stress_tmax_c=float(_num(g("heat_stress_tmax_c"), cid, "heat_stress_tmax_c", 15, 55)),
        frost_damage_tmin_c=float(_num(g("frost_damage_tmin_c"), cid, "frost_damage_tmin_c", -40, 10)),
        sensitive_stage=_choice(g("sensitive_stage"), STAGES, cid, "sensitive_stage"),
        fao56=fao,
        drought_tolerance=int(_num(g("drought_tolerance"), cid, "drought_tolerance", 1, 5)),
        n_fixation_kg_ha=float(_num(g("n_fixation_kg_ha"), cid, "n_fixation_kg_ha", 0, 500)),
        residue_index=float(_num(g("residue_index"), cid, "residue_index", 0, 1)),
        rusle_c=float(_num(g("rusle_c"), cid, "rusle_c", 0, 1)),
        root_type=_choice(g("root_type"), ROOT_TYPES, cid, "root_type"),
        forage_value=int(_num(g("forage_value"), cid, "forage_value", 0, 3)),
        disease_groups=tuple(dg),
        economics=econ,
        irrigation_typical=_choice(g("irrigation_typical"), IRRIGATION, cid, "irrigation_typical"),
        notes=_bilingual(g("notes"), cid, "notes"),
        sources=tuple(src),
        perennial_years=py,
    )


def load_crops(path: Path | None = None) -> dict[str, Crop]:
    """Load and validate the crop YAML; raises ValueError naming the crop and field."""
    p = Path(path) if path is not None else DEFAULT_PATH
    with open(p, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, list):
        raise ValueError("crops file must contain a list of crop entries")
    crops: dict[str, Crop] = {}
    for raw in data:
        crop = _parse(raw)
        if crop.id in crops:
            raise ValueError(f"crop '{crop.id}': field 'id': duplicate id")
        crops[crop.id] = crop
    return crops
