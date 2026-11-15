"""FieldReport assembly (CONTRACTS section 4): connectors -> engine -> deterministic bilingual evidence."""
from __future__ import annotations

import copy
import dataclasses
import json
import math
import threading
from collections import OrderedDict
from datetime import date

import numpy as np
import pandas as pd

from .connectors import modis, power, precip, soil as soil_mod, terrain as terrain_mod
from .engine.climate import add_et0, climate_profile
from .engine.phenology import analyze_ndvi
from .engine.cards import pick_cards, zone_policy
from .engine.specialty_water import simulate_specialty_water, water_models
from .engine.rotations import (IRRIGATION_EFFICIENCY, Rotation, RotationStep, generate_candidates, pick_strategies,
                               simulate_rotation)
from .engine.scoring import DEFAULT_PRIORITIES, score
from .field_inputs import normalize_details, normalize_polygon
from .knowledge.crops import load_crops
from .zones import lookup as zone_lookup
from pydantic import ValidationError

WEATHER_START_YEAR = 1991
NDVI_START = date(2000, 2, 1)
N_START_YEARS = 25

DEFAULT_ROTATION = [
    {"crop_id": "wheat_winter", "irrigation": "none"},
    {"crop_id": "sugar_beet", "irrigation": "full"},
    {"crop_id": "maize_grain", "irrigation": "full"},
]

SOURCES = {
    "nasa_power": {"name": "NASA POWER", "detail": "Daily weather, 0.5°×0.625° grid", "url": "https://power.larc.nasa.gov/"},
    "gpm_imerg": {"name": "NASA GPM IMERG (via SERVIR ClimateSERV)", "detail": "Satellite rain, 0.1° daily; used to bias-correct POWER rain",
                  "url": "https://gpm.nasa.gov/data/imerg"},
    "chirps": {"name": "CHIRPS v2.0 (via SERVIR ClimateSERV)", "detail": "Satellite-gauge rain, 0.05° daily; used to bias-correct POWER rain",
               "url": "https://www.chc.ucsb.edu/data/chirps"},
    "modis_mod13q1": {"name": "MODIS MOD13Q1 NDVI", "detail": "16-day composites, 250 m pixel",
                      "url": "https://modis.ornl.gov/data/modis_webservice.html"},
    "fao56": {"name": "FAO Irrigation and Drainage Paper 56", "detail": "ET0, crop coefficients, root-zone water balance",
              "url": "https://www.fao.org/4/x0490e/x0490e00.htm"},
    "soilgrids": {"name": "ISRIC SoilGrids 2.0", "detail": "250 m soil properties, 0–30 cm", "url": "https://soilgrids.org/"},
    "soil_default": {"name": "Regional default soil", "detail": "Documented regional default (SoilGrids unavailable)",
                     "url": "https://soilgrids.org/"},
    "srtm_terrain_tiles": {"name": "SRTM terrain tiles", "detail": "AWS Open Data terrain tiles, SRTM-derived",
                           "url": "https://registry.opendata.aws/terrain-tiles/"},
    "pereira2024_kc": {"name": "Pereira, Mota, Raziei, Paredes (2024), Irrigation Science 42(6)",
                       "detail": "Crop coefficients, root depth and depletion fraction of cumin and fenugreek (Tables 7 and 8)",
                       "url": "https://doi.org/10.1007/s00271-024-00960-4"},
    "ugur_kan2016_kimyon": {"name": "Uğur & Kan (2016), Selçuk Tarım Bilimleri Dergisi 3(2):205-209",
                            "detail": "Rain-fed cumin sowing and harvest dates, Central Anatolia (Ankara-Gölbaşı)",
                            "url": "https://dergipark.org.tr/en/download/article-file/3082658"},
    "cemen_ankara2016": {"name": "Selçuk Tarım Bilimleri Dergisi 3(2):210-214 (2016)",
                         "detail": "Rain-fed fenugreek sowing and harvest dates, Central Anatolia (Ankara-Gölbaşı)",
                         "url": "https://dergipark.org.tr/en/download/article-file/3082673"},
    "reyhani2015_kimyon": {"name": "Reyhani & Khashei Siuki (2015), Water and Soil 29(5):1047-1056",
                           "detail": "Lysimeter growth-stage lengths of cumin",
                           "url": "https://doi.org/10.22067/jsw.v29i5.24171"},
    "irrigation_efficiency": {"name": "FAO Irrigation Water Management Training Manual No. 5: Irrigation Methods (Brouwer, Prins, Kay, Heibloem, 1989)",
                              "detail": "Typical field application efficiency: surface ~0.60, sprinkler ~0.75, drip ~0.90. Surface is "
                                        "split into flood 0.55 and furrow 0.65 by our assumption; rounded values, not measured on the field",
                              "url": "https://www.fao.org/4/s8684e/s8684e00.htm"},
    "user": {"name": "User-provided field data / Kullanıcı beyanı",
             "detail": "Values typed in by the user (field boundary, soil, crops, water); not verified", "url": ""},
}

# Representative (clay %, sand %) per USDA texture class: area centroids of each class in the USDA texture triangle
# (class boundaries as in connectors/soil.py usda_texture_class; centroid of the clay/sand plane, rounded).
# Used only when the user names a texture class without clay/sand. See docs/METHODS.md section 11.
TEXTURE_CLAY_SAND = {
    "clay": (63, 20), "clay loam": (33, 33), "silty clay loam": (33, 10), "silty clay": (47, 7),
    "loam": (18, 42), "silt loam": (13, 22), "sandy loam": (10, 65), "sandy clay loam": (27, 61),
    "sandy clay": (41, 52), "loamy sand": (6, 82), "sand": (3, 92), "silt": (5, 8),
}
TEXTURE_TR = {"clay": "killi", "clay loam": "killi tın", "silty clay loam": "siltli killi tın", "silty clay": "siltli kil",
              "loam": "tın", "silt loam": "siltli tın", "sandy loam": "kumlu tın", "sandy clay loam": "kumlu killi tın",
              "sandy clay": "kumlu kil", "loamy sand": "tınlı kum", "sand": "kumlu", "silt": "silt"}

DISCLAIMER = {
    "en": "Rotacast is a decision-support tool, not a guarantee. Results come from satellite and reanalysis data and "
          "simplified models; check them with your agronomist or local extension service before changing your rotation.",
    "tr": "Rotacast bir karar destek aracıdır, kesin sonuç vaat etmez. Sonuçlar uydu ve yeniden analiz verilerine ve "
          "basitleştirilmiş modellere dayanır; rotasyonunuzu değiştirmeden önce ziraat mühendisiniz veya ilçe tarım "
          "müdürlüğünüzle mutlaka görüşün.",
}

ARCH_ORDER = ["water_saver", "soil_builder", "balanced_income"]


# ------------------------------------------------------------------ helpers
def _clean(o):
    """Recursively convert to JSON-safe python (numpy -> python, NaN/inf -> None, tuples -> lists)."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        v = float(o)
        return v if math.isfinite(v) else None
    if isinstance(o, (pd.Timestamp, date)):
        return o.isoformat()[:10]
    if o is pd.NaT:
        return None
    return o


def _num(x, nd: int, lang: str) -> str:
    s = f"{x:,.{nd}f}"
    if lang == "tr":
        s = s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return s


_MONTHS = {"en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
           "tr": ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]}


def _doy_label(doy: int, lang: str) -> str:
    d = date(2001, 1, 1).toordinal() + int(doy) - 1
    d = date.fromordinal(d)
    return f"{_MONTHS[lang][d.month - 1]} {d.day}" if lang == "en" else f"{d.day} {_MONTHS[lang][d.month - 1]}"


class Facts:
    """Fact registry: ids f1, f2, ... in insertion order; identical keys are reused."""

    def __init__(self):
        self.items: list[dict] = []
        self._keys: dict[str, str] = {}

    def add(self, key: str, en: str, tr: str, value, unit: str, source_id: str) -> str:
        if key in self._keys:
            return self._keys[key]
        fid = f"f{len(self.items) + 1}"
        self._keys[key] = fid
        self.items.append({"id": fid, "text": {"en": en, "tr": tr}, "value": value, "unit": unit, "source_id": source_id})
        return fid


IRRIGATION_MODES = ("none", "deficit", "full")
_IRRIGATION_ALIASES = {"limited": "deficit"}  # older clients sent the water-access word for a crop step


def _irrigation_mode(value) -> str:
    """Per-step irrigation mode the water balance understands; unknown values raise instead of silently meaning 'none'."""
    mode = _IRRIGATION_ALIASES.get(value or "none", value or "none")
    if mode not in IRRIGATION_MODES:
        raise ValueError(f"unknown irrigation mode: {value!r} (expected one of {', '.join(IRRIGATION_MODES)})")
    return mode


def normalize_request(req: dict | None) -> dict:
    req = dict(req or {})
    cons = {"water_access": "limited", "max_irrigated_share": 0.5}
    cons.update(req.get("constraints") or {})
    pri = dict(DEFAULT_PRIORITIES)
    pri.update({k: float(v) for k, v in (req.get("priorities") or {}).items() if v is not None})
    scen = {"delta_t_c": 0.0, "precip_change_pct": 0.0}
    scen.update({k: float(v) for k, v in (req.get("scenario") or {}).items() if v is not None})
    rot = [{"crop_id": s["crop_id"], "irrigation": _irrigation_mode(s.get("irrigation"))}
           for s in (req.get("current_rotation") or DEFAULT_ROTATION)]
    lat, lon = float(req.get("lat", 37.60)), float(req.get("lon", 32.75))
    try:
        poly = normalize_polygon(req.get("field_polygon"))
        details = normalize_details(req.get("field_details"))
    except ValidationError as e:
        raise ValueError(f"invalid field input: {e.errors()[0]['msg']}") from e
    out = {"lat": lat, "lon": lon, "current_rotation": rot,
           "constraints": cons, "priorities": pri, "scenario": scen, "lang": req.get("lang", "tr"),
           "label": req.get("label")}
    if poly:  # lat/lon come from the polygon centroid
        out["lat"], out["lon"] = float(poly["centroid"][1]), float(poly["centroid"][0])
        out["polygon"] = poly
    if details:
        out["details"] = details
    return out


def _apply_scenario(wx: pd.DataFrame, scen: dict, lat: float) -> pd.DataFrame:
    dt, dp = scen["delta_t_c"], scen["precip_change_pct"]
    if not dt and not dp:
        return wx
    w = wx.drop(columns=["et0"], errors="ignore").copy()
    w.attrs = dict(wx.attrs)
    for c in ("tmax", "tmin", "tmean"):
        w[c] = w[c] + dt
    w["precip"] = (w["precip"] * (1.0 + dp / 100.0)).clip(lower=0.0)
    return add_et0(w, lat, w.attrs.get("elevation_m", 0.0))


def _start_years(first: int, last: int, n_main: int) -> list[int]:
    ys = [y for y in range(first, last + 1) if y + n_main + 1 <= last]
    return ys[-N_START_YEARS:]


def _n_main(steps, crops) -> int:
    return sum(1 for s in steps if crops[s.crop_id].category != "cover") or 1


def _p50(b):
    return b["p50"] if isinstance(b, dict) else b


# ------------------------------------------------------------------ facts + evidence
def _climate_facts(F: Facts, climate: dict, fm: dict, soil: dict, lat_label: str) -> dict:
    ids: dict = {}
    ann = climate.get("annual") or []
    if ann:
        p = float(np.mean([a["precip_mm"] for a in ann]))
        e = float(np.mean([a["et0_mm"] for a in ann]))
        d = e - p
        ids["deficit"] = F.add(
            "deficit", f"On average {_num(p, 0, 'en')} mm of rain falls per year but the atmosphere demands "
                       f"{_num(e, 0, 'en')} mm (reference ET0): a deficit of {_num(d, 0, 'en')} mm.",
            f"Yılda ortalama {_num(p, 0, 'tr')} mm yağmur düşüyor, ancak bitkilerin ihtiyacı (referans ET0) "
            f"{_num(e, 0, 'tr')} mm; açık {_num(d, 0, 'tr')} mm.", round(d, 1), "mm", "nasa_power")
    metrics = {m["id"]: m for m in (climate.get("shift") or {}).get("metrics", [])}
    sh = climate.get("shift") or {}
    per = f"{sh.get('early', ['', ''])[0]}–{sh.get('early', ['', ''])[1]}", f"{sh.get('late', ['', ''])[0]}–{sh.get('late', ['', ''])[1]}"
    m = metrics.get("heat_days_35")
    if m and m.get("early") is not None and m.get("late") is not None:
        pv = m.get("p_value")
        pe = f", p = {_num(pv, 3, 'en')}" if pv is not None else ""
        pt = f", p = {_num(pv, 3, 'tr')}" if pv is not None else ""
        ids["heat"] = F.add(
            "heat", f"Days above 35 °C changed from {_num(m['early'], 1, 'en')} per year ({per[0]}) to "
                    f"{_num(m['late'], 1, 'en')} per year ({per[1]}){pe}.",
            f"35 °C üzeri gün sayısı yılda {_num(m['early'], 1, 'tr')} günden ({per[0]}) {_num(m['late'], 1, 'tr')} güne "
            f"({per[1]}) değişti{pt}.", round(m["late"] - m["early"], 2), "days/yr", "nasa_power")
    m = metrics.get("et0_mm")
    if m and m.get("early") is not None and m.get("late") is not None:
        pv = m.get("p_value")
        pe = f", p = {_num(pv, 3, 'en')}" if pv is not None else ""
        pt = f", p = {_num(pv, 3, 'tr')}" if pv is not None else ""
        ids["et0"] = F.add(
            "et0", f"Yearly reference ET0 went from {_num(m['early'], 0, 'en')} mm ({per[0]}) to "
                   f"{_num(m['late'], 0, 'en')} mm ({per[1]}){pe}.",
            f"Yıllık referans ET0 {_num(m['early'], 0, 'tr')} mm'den ({per[0]}) {_num(m['late'], 0, 'tr')} mm'ye "
            f"({per[1]}) çıktı{pt}.", round(m["late"] - m["early"], 1), "mm", "nasa_power")
    ff = ((climate.get("frost") or {}).get("frost_free_days") or {}).get("p50")
    if ff is not None:
        ids["frost_free"] = F.add(
            "frost_free", f"The median frost-free period is {_num(ff, 0, 'en')} days.",
            f"Ortanca donsuz dönem {_num(ff, 0, 'tr')} gün.", round(ff, 0), "days", "nasa_power")
    # field memory
    yrs = fm.get("years") or []
    if yrs:
        n = len(yrs)
        cnt = {k: sum(1 for y in yrs if y.get("pattern") == k) for k in ("winter_crop", "summer_crop", "double_crop", "fallow")}
        top = max(cnt, key=cnt.get)
        names = {"winter_crop": ("a winter crop", "kışlık ürün"), "summer_crop": ("a summer crop", "yazlık ürün"),
                 "double_crop": ("a double crop", "çift ürün"), "fallow": ("fallow", "nadas")}
        ids["pattern"] = F.add(
            "pattern", f"Satellite greenness suggests {names[top][0]} in {cnt[top]} of {n} years "
                       f"(winter {cnt['winter_crop']}, summer {cnt['summer_crop']}, double {cnt['double_crop']}, "
                       f"fallow {cnt['fallow']}).",
            f"Uydu yeşillik verisi {n} yılın {cnt[top]} tanesinde {names[top][1]} gösteriyor "
            f"(kışlık {cnt['winter_crop']}, yazlık {cnt['summer_crop']}, çift ürün {cnt['double_crop']}, "
            f"nadas {cnt['fallow']}).", cnt[top], "years", "modis_mod13q1")
        sy = fm.get("stress_years") or []
        ids["stress_years"] = F.add(
            "stress_years", f"{len(sy)} of {n} years showed below-normal greenness (stress years)"
                            + (f": {', '.join(str(y) for y in sy[:8])}." if sy else "."),
            f"{n} yılın {len(sy)} tanesinde yeşillik normalin altında kaldı (stresli yıllar)"
            + (f": {', '.join(str(y) for y in sy[:8])}." if sy else "."), len(sy), "years", "modis_mod13q1")
    bw = [w for w in (fm.get("bare_windows") or []) if w["end_doy"] - w["start_doy"] >= 30]
    if bw:
        w = max(bw, key=lambda w: (w["end_doy"] - w["start_doy"]) * w["probability"])
        L = w["end_doy"] - w["start_doy"] + 1
        pr = int(round(w["probability"] * 100))
        ids["bare"] = F.add(
            "bare", f"The field is typically bare for about {L} days between {_doy_label(w['start_doy'], 'en')} and "
                    f"{_doy_label(w['end_doy'], 'en')} (probability {pr}%).",
            f"Tarla genellikle {_doy_label(w['start_doy'], 'tr')} – {_doy_label(w['end_doy'], 'tr')} arasında yaklaşık "
            f"{L} gün boş kalıyor (olasılık %{pr}).", L, "days", "modis_mod13q1")
    if soil.get("taw_mm_per_m") is not None:
        tx = soil.get("texture_class", "")
        TR = TEXTURE_TR
        ids["soil"] = F.add(
            "soil", f"The soil is {tx} and holds about {_num(soil['taw_mm_per_m'], 0, 'en')} mm of plant-available "
                    f"water per metre of depth.",
            f"Toprak {TR.get(tx, tx)} yapıda ve her metre derinlikte yaklaşık {_num(soil['taw_mm_per_m'], 0, 'tr')} mm "
            f"bitkinin kullanabileceği su tutuyor.", round(soil["taw_mm_per_m"], 0), "mm/m", soil.get("source_id", "soilgrids"))
    return ids


def _precip_fact(F: Facts, pc: dict | None, ids: dict) -> None:
    if not pc:
        return
    nm = {"gpm_imerg": "GPM IMERG 0.1°", "chirps": "CHIRPS 0.05°"}.get(pc["source_id"], pc["source_id"])
    s_, p_ = pc["sat_mean_mm"], pc["power_mean_mm"]
    ids["precip"] = F.add(
        "precip_corr", f"Satellite rain ({nm}) shows {_num(s_, 0, 'en')} mm/yr versus {_num(p_, 0, 'en')} mm/yr in the coarse "
                       f"POWER grid; we corrected POWER month by month.",
        f"Uydu yağışı ({nm}) yılda {_num(s_, 0, 'tr')} mm gösteriyor; iri NASA POWER ızgarasında {_num(p_, 0, 'tr')} mm/yıl. "
        f"POWER verisini ay ay düzelttik.", round(s_, 1), "mm/yr", pc["source_id"])


def _crop_chain(strategy: dict, crops: dict, lang: str) -> str:
    names = [crops[s["crop_id"]].name[lang] for s in strategy.get("steps", [])]
    return " → ".join(names)


def _dir(delta, lang, less, more):
    return (less if delta < 0 else more)[0 if lang == "en" else 1]


def _strategy_deltas(F: Facts, st: dict, base: dict, ids: dict) -> dict:
    """Register facts for strategy-vs-baseline deltas; returns {name: (fact_id, delta, base, new)}."""
    sid = st["id"]
    I, B = st["indicators"], base["indicators"]
    out = {}

    def reg(name, key, en, tr, delta, unit, new, old):
        out[name] = (F.add(f"{sid}:{key}", en, tr, round(delta, 3), unit, "fao56"), delta, old, new)

    wn, wo = _p50(I["water_m3_ha_yr"]), _p50(B["water_m3_ha_yr"])
    dw = wn - wo
    if sid == "baseline":
        inn = _p50(I["income_usd_ha_yr"])
        out["water"] = (F.add("baseline:water", f"Your current rotation uses {_num(wn, 0, 'en')} m³/ha of irrigation water per year.",
                              f"Mevcut rotasyonunuz yılda {_num(wn, 0, 'tr')} m³/ha sulama suyu kullanıyor.",
                              round(wn, 0), "m3/ha/yr", "fao56"), 0.0, wo, wn)
        out["income"] = (F.add("baseline:income", f"Its median gross margin is {_num(inn, 0, 'en')} USD/ha per year.",
                               f"Ortanca brüt kârı yılda {_num(inn, 0, 'tr')} USD/ha.", round(inn, 0), "USD/ha/yr", "fao56"),
                         0.0, inn, inn)
        for k, (en, tr) in (("heat_risk", ("heat", "sıcak")), ("frost_risk", ("frost", "don"))):
            v = I[k]
            out[k] = (F.add(f"baseline:{k}",
                            f"In {_num(v * 100, 0, 'en')}% of simulated years a crop in the current rotation suffers {en} damage.",
                            f"Simüle edilen yılların %{_num(v * 100, 0, 'tr')} kadarında mevcut rotasyondaki bir ürün {tr} zararı görüyor.",
                            round(v, 3), "probability", "fao56"), v, v, v)
        return out
    if abs(dw) >= 1:
        reg("water", "water",
            f"Irrigation water use is {_num(wn, 0, 'en')} m³/ha per year versus {_num(wo, 0, 'en')} in the current "
            f"rotation ({_num(abs(dw), 0, 'en')} m³/ha {'less' if dw < 0 else 'more'}).",
            f"Sulama suyu kullanımı yılda {_num(wn, 0, 'tr')} m³/ha; mevcut rotasyonda {_num(wo, 0, 'tr')} "
            f"({_num(abs(dw), 0, 'tr')} m³/ha {'daha az' if dw < 0 else 'daha fazla'}).", dw, "m3/ha/yr", wn, wo)
    inn, ino = _p50(I["income_usd_ha_yr"]), _p50(B["income_usd_ha_yr"])
    di = inn - ino
    reg("income", "income",
        f"Median gross margin is {_num(inn, 0, 'en')} USD/ha per year versus {_num(ino, 0, 'en')} now "
        f"({_num(abs(di), 0, 'en')} USD/ha {'lower' if di < 0 else 'higher'}).",
        f"Ortanca brüt kâr yılda {_num(inn, 0, 'tr')} USD/ha; şimdiki rotasyonda {_num(ino, 0, 'tr')} "
        f"({_num(abs(di), 0, 'tr')} USD/ha {'düşük' if di < 0 else 'yüksek'}).", di, "USD/ha/yr", inn, ino)
    dn = I["n_balance_kg_ha_yr"] - B["n_balance_kg_ha_yr"]
    reg("n", "n",
        f"Nitrogen left for the next crop is {_num(I['n_balance_kg_ha_yr'], 0, 'en')} kg/ha per year versus "
        f"{_num(B['n_balance_kg_ha_yr'], 0, 'en')} now.",
        f"Sonraki ürüne kalan azot yılda {_num(I['n_balance_kg_ha_yr'], 0, 'tr')} kg/ha; şimdi "
        f"{_num(B['n_balance_kg_ha_yr'], 0, 'tr')}.", dn, "kg/ha/yr", I["n_balance_kg_ha_yr"], B["n_balance_kg_ha_yr"])
    er = I["erosion_rel"]
    reg("erosion", "erosion",
        f"Modelled erosion is {_num(er * 100, 0, 'en')}% of the current rotation's level.",
        f"Hesaplanan erozyon, mevcut rotasyonun %{_num(er * 100, 0, 'tr')} düzeyinde.", er - 1.0, "ratio", er, 1.0)
    dc = I["soil_cover_days_yr"] - B["soil_cover_days_yr"]
    reg("cover", "cover",
        f"The soil is covered by crop canopy {_num(I['soil_cover_days_yr'], 0, 'en')} days per year versus "
        f"{_num(B['soil_cover_days_yr'], 0, 'en')} now.",
        f"Toprak yılda {_num(I['soil_cover_days_yr'], 0, 'tr')} gün bitki örtüsüyle kaplı; şimdi "
        f"{_num(B['soil_cover_days_yr'], 0, 'tr')} gün.", dc, "days/yr", I["soil_cover_days_yr"], B["soil_cover_days_yr"])
    ds = _p50(I["stress_days_yr"]) - _p50(B["stress_days_yr"])
    reg("stress", "stress",
        f"Water-stress days are {_num(_p50(I['stress_days_yr']), 0, 'en')} per year versus "
        f"{_num(_p50(B['stress_days_yr']), 0, 'en')} now.",
        f"Su stresi günleri yılda {_num(_p50(I['stress_days_yr']), 0, 'tr')}; şimdi {_num(_p50(B['stress_days_yr']), 0, 'tr')}.",
        ds, "days/yr", _p50(I["stress_days_yr"]), _p50(B["stress_days_yr"]))
    dp = I["pest_break"] - B["pest_break"]
    reg("pest", "pest",
        f"The disease and pest break index is {_num(I['pest_break'], 2, 'en')} versus {_num(B['pest_break'], 2, 'en')} now.",
        f"Hastalık-zararlı kırma endeksi {_num(I['pest_break'], 2, 'tr')}; şimdi {_num(B['pest_break'], 2, 'tr')}.",
        dp, "index", I["pest_break"], B["pest_break"])
    for k, (en, tr) in (("heat_risk", ("heat", "sıcak")), ("frost_risk", ("frost", "don"))):
        v = I[k]
        out[k] = (F.add(f"{sid}:{k}",
                        f"In {_num(v * 100, 0, 'en')}% of simulated years a crop in this rotation suffers {en} damage.",
                        f"Simüle edilen yılların %{_num(v * 100, 0, 'tr')} kadarında bu rotasyondaki bir ürün {tr} zararı görüyor.",
                        round(v, 3), "probability", "fao56"), v, B[k], v)
    yn, yo = _p50(I["yield_ratio"]), _p50(B["yield_ratio"])
    out["yield"] = (F.add(f"{sid}:yield", f"Median relative yield is {_num(yn * 100, 0, 'en')}% of potential versus "
                                          f"{_num(yo * 100, 0, 'en')}% now.",
                          f"Ortanca bağıl verim potansiyelin %{_num(yn * 100, 0, 'tr')}'i; şimdi %{_num(yo * 100, 0, 'tr')}.",
                          round(yn - yo, 3), "ratio", "fao56"), yn - yo, yo, yn)
    return out


GAPS = [
    {"text": {"en": "Weather comes from a 0.5° NASA POWER grid cell (reanalysis); its rainfall can differ from your field, "
                    "especially in showers and hilly terrain.",
              "tr": "Hava verisi 0,5° çözünürlüklü NASA POWER ızgarasından (yeniden analiz) geliyor; özellikle sağanak "
                    "yağışlarda ve engebeli arazide tarlanıza düşen yağmur bundan farklı olabilir."}},
    {"text": {"en": "The satellite sees a 250 m MODIS pixel that can mix your field with neighbouring parcels, so the "
                    "inferred crop history is approximate.",
              "tr": "Uydu 250 m'lik bir MODIS pikselini görüyor; bu piksel tarlanız ile komşu parselleri karıştırabilir, "
                    "bu yüzden çıkarılan ekim geçmişi yaklaşıktır."}},
    {"text": {"en": "Crop water use relies on generic FAO crop coefficients, not on your variety, sowing density or "
                    "management.",
              "tr": "Bitki su tüketimi, çeşidinize, ekim sıklığınıza veya yönetiminize değil, genel FAO bitki "
                    "katsayılarına dayanıyor."}},
    {"text": {"en": "Income is estimated GROSS income: rough price x modelled yield minus irrigation water cost. Seed, fertiliser, "
                    "fuel, labour and rent are not deducted, so it is not profit; real income also depends on contracts, "
                    "quality and the market in the year you sell.",
              "tr": "Gelir, tahmini BRÜT gelirdir: kaba fiyat x modellenen verim, eksi sulama suyu maliyeti. Tohum, gübre, yakıt, "
                    "işçilik ve kira düşülmez, yani kâr değildir; gerçek gelir ayrıca sözleşmelere, kaliteye ve sattığınız "
                    "yıldaki piyasaya bağlıdır."}},
]


def _evidence(st: dict, base: dict, deltas: dict, ids: dict, crops: dict, base_crops: set) -> dict:
    arch = st["archetype"]
    why, benefits, risks = [], [], []
    d = deltas
    chain_en, chain_tr = _crop_chain(st, crops, "en"), _crop_chain(st, crops, "tr")

    def item(text_en, text_tr, facts):
        return {"text": {"en": text_en, "tr": text_tr}, "facts": [f for f in facts if f]}

    g = lambda k: d[k][0] if k in d else None  # noqa: E731
    if arch == "baseline":
        why.append(item("This is the rotation you entered; every other option is compared against it.",
                        "Bu, sizin girdiğiniz rotasyon; diğer seçeneklerin hepsi buna göre karşılaştırılıyor.",
                        [g("water"), g("income")]))
        why.append(item("Your area has a large water deficit, so irrigated crops in the rotation depend on well or canal water.",
                        "Bölgenizde büyük bir su açığı var; bu yüzden rotasyondaki sulu ürünler kuyu veya kanal suyuna bağlıdır.",
                        [ids.get("deficit"), ids.get("precip")]))
        if ids.get("pattern"):
            why.append(item("Satellite greenness records show what has actually been grown here.",
                            "Uydu yeşillik kayıtları buraya gerçekte ne ekildiğini gösteriyor.", [ids["pattern"]]))
    else:
        if arch == "water_saver":
            if "water" in d:
                w = d["water"]
                why.append(item(
                    f"Crops chosen here ({chain_en}) need {_dir(w[1], 'en', ('less', 'daha az'), ('more', 'daha fazla'))} irrigation water than your current rotation.",
                    f"Burada seçilen ürünler ({chain_tr}) mevcut rotasyonunuza göre {_dir(w[1], 'tr', ('less', 'daha az'), ('more', 'daha fazla'))} sulama suyu istiyor.",
                    [w[0]]))
            why.append(item("Your area loses far more water to evaporation than it receives as rain, so every cubic metre saved counts.",
                            "Bölgenizde buharlaşmayla kaybedilen su yağmurdan çok fazla; tasarruf edilen her metreküp önemli.",
                            [ids.get("deficit"), ids.get("precip"), ids.get("et0")]))
            if "stress" in d:
                why.append(item("Fewer days of water stress mean the crops cope better in dry years.",
                                "Daha az su stresi günü, ürünlerin kurak yıllarla daha iyi başa çıkması demek.", [d["stress"][0]]))
        elif arch == "soil_builder":
            why.append(item(f"The sequence ({chain_en}) returns more organic matter and nitrogen to the soil.",
                            f"Bu sıralama ({chain_tr}) toprağa daha fazla organik madde ve azot bırakıyor.",
                            [g("n"), g("cover")]))
            if ids.get("bare"):
                why.append(item("Your field sits bare for a long stretch each year; keeping it covered protects the soil.",
                                "Tarlanız her yıl uzun süre boş kalıyor; üzerini kapalı tutmak toprağı korur.", [ids["bare"]]))
            why.append(item("More ground cover and a lower share of bare days reduce erosion.",
                            "Daha fazla toprak örtüsü ve daha az çıplak gün, erozyonu azaltır.", [g("erosion"), g("cover")]))
        elif arch == "low_risk":
            why.append(item(f"Every crop in this rotation ({chain_en}) is documented in your zone by an official source.",
                            f"Bu rotasyondaki her ürün ({chain_tr}) bölgenizde resmî bir kaynakla belgelenmiş.",
                            [g("income"), g("water")]))
            why.append(item("It is the option with the lowest weather and yield risk among those that stay within your current water use and erosion.",
                            "Mevcut su kullanımınızı ve erozyon düzeyinizi aşmayan seçenekler içinde hava ve verim riski en düşük olanı.",
                            [g("yield"), g("stress"), g("heat_risk")]))
        elif arch in ("balanced_transition", "innovative"):
            sp = next((p for p in st.get("parts", []) if p["kind"] == "specialty"), None)
            share = round(100 * (sp["share"] if sp else 0))
            rest = 100 - share
            if sp and sp.get("crop"):
                c_en, c_tr = sp["crop"]["name"]["en"], sp["crop"]["name"]["tr"]
                why.append(item(f"About {rest} % of the field stays on {chain_en}; about {share} % tries {c_en}, a crop documented in your zone.",
                                f"Tarlanın yaklaşık %{rest}'i {chain_tr} rotasyonunda kalıyor; %{share}'inde bölgenizde belgelenmiş {c_tr} deneniyor.",
                                [g("income"), g("water")]))
            else:
                why.append(item(f"About {rest} % of the field stays on {chain_en}; about {share} % is set aside for a specialty crop documented in your zone.",
                                f"Tarlanın yaklaşık %{rest}'i {chain_tr} rotasyonunda kalıyor; %{share}'i bölgenizde belgelenmiş bir özel ürüne ayrılıyor.",
                                [g("income"), g("water")]))
            why.append(item("Water is the scarce input in your area, so no part of the plan may use more irrigation water than today.",
                            "Bölgenizde kıt olan girdi su; bu yüzden planın hiçbir parçası bugünkünden fazla sulama suyu kullanamaz.",
                            [ids.get("deficit"), g("water")]))
        else:  # balanced_income
            why.append(item(f"The sequence ({chain_en}) keeps income close to, or above, your current level while cutting other costs.",
                            f"Bu sıralama ({chain_tr}) geliri mevcut düzeyin yakınında veya üstünde tutarken diğer maliyetleri düşürüyor.",
                            [g("income"), g("water")]))
            why.append(item("Water is the scarce input in your area, so income per cubic metre matters.",
                            "Bölgenizde kıt olan girdi su; bu yüzden metreküp başına gelir önemli.", [ids.get("deficit")]))
            if ids.get("heat"):
                why.append(item("Summer heat days are increasing, so spreading crops across different seasons lowers the risk.",
                                "Yaz sıcak günleri artıyor; ürünleri farklı mevsimlere yaymak riski azaltır.", [ids["heat"]]))
        why = why[:3]
        # benefits (only favourable)
        if "water" in d and d["water"][1] <= -0.05 * max(d["water"][2], 1):
            benefits.append(item("Saves irrigation water compared with your current rotation.",
                                 "Mevcut rotasyonunuza göre sulama suyundan tasarruf sağlar.", [d["water"][0]]))
        if d["income"][1] >= 0.03 * max(abs(d["income"][2]), 1):
            benefits.append(item("Raises the median income per hectare.", "Hektar başına ortanca geliri artırır.", [d["income"][0]]))
        if d["n"][1] >= 10:
            benefits.append(item("Leaves more nitrogen for the following crop, so less fertiliser is needed.",
                                 "Sonraki ürün için daha fazla azot bırakır; böylece daha az gübre gerekir.", [d["n"][0]]))
        if d["erosion"][3] < 0.95:
            benefits.append(item("Lowers soil erosion.", "Toprak erozyonunu azaltır.", [d["erosion"][0]]))
        if d["cover"][1] >= 15:
            benefits.append(item("Keeps the soil covered for more days.", "Toprağı daha fazla gün kapalı tutar.", [d["cover"][0]]))
        if d["pest"][1] >= 0.1:
            benefits.append(item("Breaks disease and pest cycles better by changing crop families.",
                                 "Ürün ailelerini değiştirerek hastalık ve zararlı döngülerini daha iyi keser.", [d["pest"][0]]))
        if "stress" in d and d["stress"][1] <= -3:
            benefits.append(item("Reduces days of water stress.", "Su stresi günlerini azaltır.", [d["stress"][0]]))
        if d["yield"][1] >= 0.03:
            benefits.append(item("Improves the expected yield relative to potential.",
                                 "Potansiyele göre beklenen verimi artırır.", [d["yield"][0]]))
    # risks
    new_crops = {s["crop_id"] for s in st.get("steps", [])} - base_crops
    if arch != "baseline" and new_crops:
        nm_en = ", ".join(crops[c].name["en"] for c in sorted(new_crops))
        nm_tr = ", ".join(crops[c].name["tr"] for c in sorted(new_crops))
        risks.append({"text": {"en": f"New crops for you ({nm_en}): confirm there is a buyer, a delivery point and a fair price nearby.",
                               "tr": f"Sizin için yeni ürünler ({nm_tr}): yakınlarda alıcı, teslim noktası ve uygun fiyat olduğundan emin olun."},
                      "check_with": "market"})
        risks.append({"text": {"en": "Check that certified seed of suitable varieties is available locally and on time.",
                               "tr": "Uygun çeşitlerin sertifikalı tohumunun yerelde ve zamanında bulunabildiğini kontrol edin."},
                      "check_with": "extension_service"})
        risks.append({"text": {"en": "A new crop brings new diseases and weeds; ask an agronomist about the spray and weed-control plan.",
                               "tr": "Yeni ürün yeni hastalık ve yabancı otlar getirir; ilaçlama ve yabancı ot mücadele planı için ziraat mühendisine danışın."},
                      "check_with": "agronomist"})
    if "heat_risk" in d and d["heat_risk"][1] > 0.2:
        risks.append({"text": {"en": "Heat damage is likely in a notable share of years for at least one crop; consider earlier sowing or heat-tolerant varieties.",
                               "tr": "En az bir ürün için yılların kayda değer bir bölümünde sıcak zararı olası; erken ekim veya sıcağa dayanıklı çeşitleri değerlendirin."},
                      "facts": [d["heat_risk"][0]], "check_with": "agronomist"})
    if "frost_risk" in d and d["frost_risk"][1] > 0.2:
        risks.append({"text": {"en": "Frost damage is likely in a notable share of years for at least one crop; check sowing dates and frost-tolerant varieties.",
                               "tr": "En az bir ürün için yılların kayda değer bir bölümünde don zararı olası; ekim tarihlerini ve dona dayanıklı çeşitleri gözden geçirin."},
                      "facts": [d["frost_risk"][0]], "check_with": "agronomist"})
    if arch != "baseline" and d["income"][1] < 0:
        risks.append({"text": {"en": "Median gross income is lower than your current rotation; check whether the saving elsewhere is worth it to you.",
                               "tr": "Ortanca brüt gelir mevcut rotasyonunuzdan düşük; başka alanlardaki kazancın sizin için değip değmediğini değerlendirin."},
                      "facts": [d["income"][0]], "check_with": "market"})
    if arch != "baseline" and any(s.get("irrigation") != "none" for s in st.get("steps", [])):
        risks.append({"text": {"en": "Irrigated years need a reliable water source and permit; confirm your quota for these seasons.",
                               "tr": "Sulu yıllar güvenilir bir su kaynağı ve izin gerektirir; bu sezonlar için su payınızı doğrulayın."},
                      "check_with": "extension_service"})
    for p in st.get("parts", []):
        if p["kind"] == "specialty" and p.get("water_modeled"):
            risks.append({"text": {"en": "Only the water need of the specialty share is in the numbers (the card's water covers the whole field); its income, yield and frost or heat risk are not modelled: there is no verified price or crop parameter.",
                                   "tr": "Özel ürün payından yalnızca su ihtiyacı sayılara girdi (kartın su değeri tüm tarlayı kapsar); gelir, verim ile don veya sıcak riski modellenmedi: doğrulanmış fiyat veya bitki parametresi yok."},
                          "check_with": "extension_service"})
        elif p["kind"] == "specialty" and not p.get("modeled"):
            risks.append({"text": {"en": "The specialty share is not in the numbers yet: the model has no sourced water and yield parameters for these crops.",
                                   "tr": "Özel ürün payı henüz sayılarda yok: modelde bu ürünler için kaynaklı su ve verim parametresi bulunmuyor."},
                          "check_with": "extension_service"})
        if p["kind"] == "specialty" and any(c and c.get("documented_yield") for c in [p.get("crop"), *(p.get("options") or [])]):
            risks.append({"text": {"en": "Income for the specialty share is not computed: there is no verified farm-gate price, and the yield shown is a Konya province mean, not a forecast for your field.",
                                   "tr": "Özel ürün payının geliri hesaplanmadı: doğrulanmış çiftlik kapısı fiyatı yok ve gösterilen verim Konya il ortalamasıdır, tarlanız için tahmin değildir."},
                          "check_with": "market"})
        if p["kind"] == "specialty" and p.get("crop"):
            risks.append({"text": {"en": "Specialty crops need a buyer or processor before sowing; a contract lowers the market risk. Investment and labour are not modelled.",
                                   "tr": "Özel ürünlerde ekimden önce alıcı veya işleyici bulunmalı; sözleşme pazar riskini azaltır. Yatırım ve işçilik modellenmedi."},
                          "check_with": "market"})
    if st.get("trials"):
        risks.append({"text": {"en": "Pilot crops are at the official pilot stage; commercial success is not yet verified. Try them only on 5–10 % of the field.",
                               "tr": "Pilot ürünler resmî pilot aşamasında; ticari başarı henüz doğrulanmadı. Yalnızca tarlanın %5–10'unda deneyin."},
                      "check_with": "extension_service"})
    feas = st.get("feasibility") or {}
    if feas.get("fraction", 1.0) < 0.9:
        risks.append({"text": {"en": "In some historical years the sowing and harvest dates of this sequence did not fit; timing may be tight.",
                               "tr": "Geçmiş yılların bir kısmında bu sıralamanın ekim ve hasat tarihleri birbirine uymadı; zamanlama sıkışık olabilir."},
                      "check_with": "agronomist"})
    return {"why": why, "benefits": benefits, "gaps": copy.deepcopy(GAPS), "risks": risks}




# ------------------------------------------------------------------ user-provided field details (CONTRACTS section 6)
_REASON_LABEL = {"no_equipment": ("no equipment", "ekipman yok"), "no_buyer": ("no buyer", "alıcı yok"),
                 "not_wanted": ("not wanted", "istenmiyor")}
_METHOD_LABEL = {"flood": ("flood irrigation", "salma sulama"), "furrow": ("furrow irrigation", "karık sulama"),
                 "sprinkler": ("sprinkler irrigation", "yağmurlama sulama"), "drip": ("drip irrigation", "damla sulama")}


def _tx(sp_or_name, lang):
    return TEXTURE_TR.get(sp_or_name, sp_or_name) if lang == "tr" else sp_or_name


def override_soil(sp, u: dict):
    """SoilProfile with the user's values replacing the SoilGrids ones (CONTRACTS 6.2). Hydraulics are recomputed."""
    clay, sand = u.get("clay_pct"), u.get("sand_pct")
    rep = TEXTURE_CLAY_SAND.get(u.get("texture_class"))
    changed = clay is not None or sand is not None or rep is not None
    if changed:
        c = clay if clay is not None else (rep[0] if rep else sp.clay_pct)
        s = sand if sand is not None else (rep[1] if rep else sp.sand_pct)
        if c + s > 100:  # only one of the two was given: shrink the inferred one
            if clay is None:
                c = 100.0 - s
            else:
                s = 100.0 - c
        silt = max(0.0, 100.0 - c - s)
    else:
        c, s, silt = sp.clay_pct, sp.sand_pct, sp.silt_pct
    soc = u.get("soc_gkg", sp.soc_gkg)
    ph = u.get("ph", sp.ph)
    prof = soil_mod.build_profile(float(c), float(s), float(silt), float(soc), float(ph), sp.bulk_density, "user")
    if u.get("texture_class"):
        prof = dataclasses.replace(prof, texture_class=u["texture_class"])
    return prof


def scale_yields(crops: dict, declared: dict, rotation: list[dict]):
    """Per-request copy of ``crops`` with potential yields scaled to the user's declared yields; returns (crops, yield_check).
    Factor = declared / regional reference (irrigated tier if the crop is irrigated in the current rotation, else rainfed)."""
    out, check = dict(crops), []
    irrigated = {s["crop_id"] for s in rotation if s["irrigation"] != "none"}
    in_rot = {s["crop_id"] for s in rotation}
    for cid, dec in declared.items():
        cr = crops[cid]
        y = cr.economics.yield_t_ha
        tier = "irrigated" if (cid in irrigated or (cid not in in_rot and cr.irrigation_typical == "required")) else "rainfed"
        ref = float(y.get(tier, y["irrigated"]))
        f = float(dec) / ref
        out[cid] = dataclasses.replace(cr, economics=dataclasses.replace(
            cr.economics, yield_t_ha={k: float(v) * f for k, v in y.items()}))
        check.append({"crop_id": cid, "declared_t_ha": float(dec), "regional_t_ha": round(ref, 2), "factor": round(f, 3)})
    return out, check


def _declared_pattern(crop) -> str:
    return "winter_crop" if crop.season == "winter" else "summer_crop"


def _bi(en, tr):
    return {"en": en, "tr": tr}


def _user_block(F: Facts, r: dict, crops: dict, sp_model, sp, fm: dict, base_raw: dict, quota: dict | None,
                yield_check: list) -> dict:
    """User-input facts (source ``user``), the ``user_inputs`` list and the history / irrigation checks."""
    poly, d = r.get("polygon"), r.get("details") or {}
    items: list[dict] = []
    fid: dict[str, str] = {}
    out: dict = {}

    def add(iid, label_en, label_tr, value, model, key, f_en, f_tr, f_val, unit):
        fid[iid] = F.add(f"user:{key}", f_en, f_tr, f_val, unit, "user")
        items.append({"id": iid, "label": _bi(label_en, label_tr), "value": value, "model": model, "fact": fid[iid]})

    if poly:
        a = poly["area_ha"]
        v = _bi(f"{_num(a, 2, 'en')} ha", f"{_num(a, 2, 'tr')} ha")
        add("polygon", "Field boundary", "Tarla sınırı", v, None, "polygon",
            f"You drew the field boundary: {_num(a, 2, 'en')} ha. Weather and satellite data are still taken for the boundary's centre.",
            f"Tarla sınırını çizdiniz: {_num(a, 2, 'tr')} ha. Hava ve uydu verisi hâlâ sınırın merkezi için alınıyor.",
            round(a, 2), "ha")
    if "soil" in d:
        u = d["soil"]
        pe, pt = [], []
        if u.get("texture_class"):
            pe.append(u["texture_class"])
            pt.append(_tx(u["texture_class"], "tr"))
        if "clay_pct" in u:
            pe.append(f"clay {_num(u['clay_pct'], 0, 'en')} %")
            pt.append(f"kil %{_num(u['clay_pct'], 0, 'tr')}")
        if "sand_pct" in u:
            pe.append(f"sand {_num(u['sand_pct'], 0, 'en')} %")
            pt.append(f"kum %{_num(u['sand_pct'], 0, 'tr')}")
        if "soc_gkg" in u:
            pe.append(f"organic carbon {_num(u['soc_gkg'], 0, 'en')} g/kg")
            pt.append(f"organik karbon {_num(u['soc_gkg'], 0, 'tr')} g/kg")
        if "ph" in u:
            pe.append(f"pH {_num(u['ph'], 1, 'en')}")
            pt.append(f"pH {_num(u['ph'], 1, 'tr')}")
        nm = "SoilGrids" if sp_model.source_id == "soilgrids" else "Regional default"
        nm_tr = "SoilGrids" if sp_model.source_id == "soilgrids" else "Bölgesel varsayılan"
        model = _bi(f"{nm}: {sp_model.texture_class}, clay {_num(sp_model.clay_pct, 0, 'en')} %, sand {_num(sp_model.sand_pct, 0, 'en')} %",
                    f"{nm_tr}: {_tx(sp_model.texture_class, 'tr')}, kil %{_num(sp_model.clay_pct, 0, 'tr')}, kum %{_num(sp_model.sand_pct, 0, 'tr')}")
        add("soil", "Soil", "Toprak", _bi(", ".join(pe), ", ".join(pt)), model, "soil",
            f"You entered soil data ({', '.join(pe)}); the soil then holds about {_num(sp.taw_mm_per_m, 0, 'en')} mm of "
            f"plant-available water per metre (satellite estimate: {_num(sp_model.taw_mm_per_m, 0, 'en')} mm/m).",
            f"Toprak bilgisi girdiniz ({', '.join(pt)}); toprak bu durumda metre başına yaklaşık {_num(sp.taw_mm_per_m, 0, 'tr')} mm "
            f"bitkiye yarayışlı su tutuyor (uydu tahmini: {_num(sp_model.taw_mm_per_m, 0, 'tr')} mm/m).",
            round(sp.taw_mm_per_m, 0), "mm/m")
    if "excluded_crops" in d:
        ex = d["excluded_crops"]
        pe = ", ".join(f"{crops[c].name['en']} ({_REASON_LABEL[x][0]})" for c, x in ex.items())
        pt = ", ".join(f"{crops[c].name['tr']} ({_REASON_LABEL[x][1]})" for c, x in ex.items())
        add("excluded_crops", "Crops left out", "Hariç tutulan ürünler", _bi(pe, pt), None, "excluded_crops",
            f"You asked to leave out: {pe}. They are not used in the other options.",
            f"Şu ürünleri hariç tutmak istediniz: {pt}. Diğer seçeneklerde kullanılmıyorlar.", len(ex), "crops")
    if "irrigation_method" in d:
        m = d["irrigation_method"]
        e = IRRIGATION_EFFICIENCY[m]
        add("irrigation_method", "Irrigation method", "Sulama yöntemi",
            _bi(f"{_METHOD_LABEL[m][0]} (efficiency {_num(e, 2, 'en')})", f"{_METHOD_LABEL[m][1]} (verim {_num(e, 2, 'tr')})"),
            _bi("Net crop need, no application losses", "Net bitki ihtiyacı, uygulama kaybı yok"), "irrigation_method",
            f"You irrigate by {_METHOD_LABEL[m][0]}: typically {_num(e * 100, 0, 'en')}% of the water pumped reaches the crop, "
            f"so water use is the crop need divided by {_num(e, 2, 'en')}.",
            f"{_METHOD_LABEL[m][1]} yapıyorsunuz: pompalanan suyun tipik olarak %{_num(e * 100, 0, 'tr')}'i bitkiye ulaşır; "
            f"su kullanımı bitki ihtiyacının {_num(e, 2, 'tr')} değerine bölünmesiyle bulunur.", e, "ratio")
    if quota:
        q, qh = quota["quota_m3_yr"], quota["quota_m3_ha_yr"]
        if quota["basis"] == "field_total":
            ve = f"{_num(q, 0, 'en')} m³/yr ({_num(qh, 0, 'en')} m³/ha)"
            vt = f"{_num(q, 0, 'tr')} m³/yıl ({_num(qh, 0, 'tr')} m³/ha)"
        else:
            ve, vt = f"{_num(q, 0, 'en')} m³/ha/yr", f"{_num(q, 0, 'tr')} m³/ha/yıl"
        add("water_quota", "Water quota", "Su kotası", _bi(ve, vt), None, "water_quota",
            f"Your water quota is {ve}.", f"Su kotanız {vt}.", round(qh, 1), "m3/ha/yr")
    if yield_check:
        def lst(key, lang, f=lambda y: y):
            return ", ".join(f"{crops[y['crop_id']].name[lang]} {_num(y[key], 1, lang)} t/ha" for y in yield_check)
        pe, pt = lst("declared_t_ha", "en"), lst("declared_t_ha", "tr")
        me, mt = lst("regional_t_ha", "en"), lst("regional_t_ha", "tr")
        add("yields", "Your yields", "Verimleriniz", _bi(pe, pt), _bi(f"Regional reference: {me}", f"Bölgesel referans: {mt}"),
            "yields", f"You reported yields of {pe}; income is scaled to them (regional reference: {me}).",
            f"Bildirdiğiniz verimler: {pt}; gelir bunlara göre ölçeklendi (bölgesel referans: {mt}).", len(yield_check), "crops")
    if "history" in d:
        sat = {y["year"]: y.get("pattern") for y in (fm.get("years") or [])}
        yrs, n_ok, n_cnt = [], 0, 0
        for h in d["history"]:
            dp = _declared_pattern(crops[h["crop_id"]])
            sp_ = sat.get(h["year"])
            agree = None if sp_ is None else bool(sp_ == dp or sp_ == "double_crop")
            if agree is not None:
                n_cnt += 1
                n_ok += int(agree)
            yrs.append({"year": h["year"], "crop_id": h["crop_id"], "declared_pattern": dp, "satellite_pattern": sp_, "agree": agree})
        out["history_check"] = {"n_years": n_cnt, "n_agree": n_ok, "agreement": round(n_ok / n_cnt, 3) if n_cnt else None, "years": yrs}
        pe = ", ".join(f"{h['year']} {crops[h['crop_id']].name['en']}" for h in d["history"])
        pt = ", ".join(f"{h['year']} {crops[h['crop_id']].name['tr']}" for h in d["history"])
        if n_cnt:
            me, mt = f"Satellite agrees in {n_ok} of {n_cnt} years", f"Uydu {n_cnt} yılın {n_ok} tanesinde uyumlu"
        else:
            me, mt = "No satellite data for these years", "Bu yıllar için uydu verisi yok"
        add("history", "Crop history", "Ekim geçmişi", _bi(pe, pt), _bi(me, mt), "history",
            f"You reported past crops ({pe}). {me}.", f"Geçmiş ürünleri bildirdiniz ({pt}). {mt}.", n_ok, "years")
    if "irrigation_applied_m3_ha" in d:
        mod = base_raw.get("irrigation_m3_ha_by_crop") or {}
        chk = []
        for cid, dec in d["irrigation_applied_m3_ha"].items():
            m = mod.get(cid)
            chk.append({"crop_id": cid, "declared_m3_ha": float(dec), "modelled_m3_ha": None if m is None else round(m, 0),
                        "diff_pct": round((dec - m) / m * 100.0, 1) if m else None})
        out["irrigation_check"] = chk
        pe = ", ".join(f"{crops[c['crop_id']].name['en']} {_num(c['declared_m3_ha'], 0, 'en')} m³/ha" for c in chk)
        pt = ", ".join(f"{crops[c['crop_id']].name['tr']} {_num(c['declared_m3_ha'], 0, 'tr')} m³/ha" for c in chk)
        mm = [c for c in chk if c["modelled_m3_ha"] is not None]
        me = ", ".join(f"{crops[c['crop_id']].name['en']} {_num(c['modelled_m3_ha'], 0, 'en')} m³/ha" for c in mm)
        mt = ", ".join(f"{crops[c['crop_id']].name['tr']} {_num(c['modelled_m3_ha'], 0, 'tr')} m³/ha" for c in mm)
        model = _bi(f"Model: {me}", f"Model: {mt}") if mm else None
        add("irrigation_applied", "Water you applied", "Uyguladığınız su", _bi(pe, pt), model, "irrigation_applied",
            f"You reported applying {pe} per season; this is compared with the model, which is not changed.",
            f"Sezon başına {pt} su uyguladığınızı bildirdiniz; bu değer modelle karşılaştırılır, model değişmez.", len(chk), "crops")
    out["user_inputs"] = items
    out["_fid"] = fid
    return out


def _user_evidence(ev: dict, st: dict, deltas: dict, ufid: dict, quota: dict | None, details: dict, crops: dict) -> None:
    """Evidence items that depend on user inputs (excluded crops, water quota)."""
    base = st["archetype"] == "baseline"
    ex = details.get("excluded_crops")
    if ex and not base and "excluded_crops" in ufid:
        pe = ", ".join(f"{crops[c].name['en']} ({_REASON_LABEL[x][0]})" for c, x in ex.items())
        pt = ", ".join(f"{crops[c].name['tr']} ({_REASON_LABEL[x][1]})" for c, x in ex.items())
        ev["why"].append({"text": {"en": f"Left out as you asked: {pe}.", "tr": f"İsteğiniz üzerine dışarıda bırakıldı: {pt}."},
                          "facts": [ufid["excluded_crops"]]})
    if quota and "water_quota" in ufid:
        w = _p50(st["indicators"]["water_m3_ha_yr"])
        qh = quota["quota_m3_ha_yr"]
        if w > qh:
            facts = [ufid["water_quota"]] + ([deltas["water"][0]] if base and "water" in deltas else [])
            if base:
                en = (f"Your current rotation needs about {_num(w, 0, 'en')} m³/ha of water per year, more than your quota of "
                      f"{_num(qh, 0, 'en')} m³/ha; check your permit and the well or canal capacity.")
                tr = (f"Mevcut rotasyonunuz yılda yaklaşık {_num(w, 0, 'tr')} m³/ha su istiyor; kotanız {_num(qh, 0, 'tr')} m³/ha. "
                      f"Su iznini ve kuyu ya da kanal kapasitesini kontrol edin.")
            else:
                en = (f"This option needs about {_num(w, 0, 'en')} m³/ha of water per year, above your quota of {_num(qh, 0, 'en')} "
                      f"m³/ha; it is shown only because too few options fit the quota.")
                tr = (f"Bu seçenek yılda yaklaşık {_num(w, 0, 'tr')} m³/ha su istiyor; kotanız {_num(qh, 0, 'tr')} m³/ha'nın üzerinde. "
                      f"Kotaya sığan seçenek yeterince olmadığı için gösteriliyor.")
            ev["risks"].append({"text": {"en": en, "tr": tr}, "facts": facts, "check_with": "extension_service"})
    # make every user value reachable from the evidence drawer (facts with source_id "user")
    used = [ufid[k] for k in ("polygon", "soil", "irrigation_method", "water_quota", "yields") if k in ufid]
    if used:
        ev["why"].append({"text": {"en": "Calculated with the field data you entered.",
                                   "tr": "Girdiğiniz tarla bilgileriyle hesaplandı."}, "facts": used})
    checks = [ufid[k] for k in ("history", "irrigation_applied") if k in ufid]
    if base and checks:
        ev["why"].append({"text": {"en": "Your own records, compared with the satellite and the model (they do not change the result).",
                                   "tr": "Kendi kayıtlarınız uydu ve modelle karşılaştırıldı (sonucu değiştirmez)."}, "facts": checks})


# ------------------------------------------------------------------ main builder
def _simulate_all(cands, wx, soil, crops, last_year, base_idx, eff=1.0):
    out = []
    for r in cands:
        n = _n_main(r.steps, crops)
        ys = _start_years(WEATHER_START_YEAR, last_year, n)
        out.append(simulate_rotation(r, wx, soil, crops, ys, baseline_erosion_index=base_idx, irrigation_efficiency=eff))
    return out


def _simulate_single(policy, crops, constraints, wx, soil, last_year, base_idx) -> dict:
    """One-crop-every-year simulation of each modelled specialty and pilot crop (its share of the field is small,
    so it is treated as its own block). Rain-fed unless the crop needs irrigation and the farmer has access,
    then deficit irrigation."""
    out = {}
    access = (constraints or {}).get("water_access", "limited")
    for rec in policy["special"] + policy["pilots"]:
        if not rec["modeled"]:
            continue
        cid = rec["engine_ids"][0]
        if cid in out:
            continue
        need = getattr(crops[cid], "irrigation_typical", "optional") == "required"
        irr = "deficit" if need and access != "none" else "none"
        rot = Rotation(id=f"single_{cid}", name=crops[cid].name, archetype="candidate", steps=[RotationStep(cid, 1, irr)])
        out[cid] = simulate_rotation(rot, wx, soil, crops, _start_years(WEATHER_START_YEAR, last_year, 1),
                                     baseline_erosion_index=base_idx)
    return out


def _simulate_water(policy, wx, soil, last_year) -> dict:
    """Water-only bands of the specialty crops of this zone that have a water model (cumin, fenugreek)."""
    models = water_models()
    out = {}
    for rec in policy["special"]:
        mid = rec.get("water_model")
        if mid in models and mid not in out:
            try:
                out[mid] = simulate_specialty_water(models[mid], wx, soil, _start_years(WEATHER_START_YEAR, last_year, 1))
            except Exception:  # no covered season: the specialty then stays unmodelled
                continue
    return out


def _water_fact(F: Facts, p: dict) -> str:
    """Fact of the water-only specialty part: season water need and what full irrigation would add."""
    w, c = p["water"], p["crop"]
    etc, eta, irr = w["etc_mm"]["p50"], w["rainfed_eta_mm"]["p50"], w["irr_need_full_m3_ha"]["p50"]
    n_en, n_tr = c["name"]["en"], c["name"]["tr"]
    return F.add(
        f"specialty_water:{w['model']}",
        f"{n_en} uses about {_num(etc, 0, 'en')} mm of water over the season (ETc); in Konya it is grown rain-fed, where rain and "
        f"soil water supply about {_num(eta, 0, 'en')} mm; full irrigation would need about {_num(irr, 0, 'en')} m³/ha more water. "
        f"Income and yield effects were not computed.",
        f"{n_tr} sezonda yaklaşık {_num(etc, 0, 'tr')} mm su tüketir (ETc); Konya'da kuru tarımla yetiştirilir, yağış ve toprak "
        f"suyu yaklaşık {_num(eta, 0, 'tr')} mm karşılar; tam sulamada yaklaşık {_num(irr, 0, 'tr')} m³/ha ek su gerekir. "
        f"Gelir ve verim etkisi hesaplanmadı.", round(etc, 0), "mm", "pereira2024_kc")


def build_field_report(req: dict | None = None) -> dict:
    r = normalize_request(req)
    lat, lon = r["lat"], r["lon"]
    crops = load_crops()
    for s in r["current_rotation"]:
        if s["crop_id"] not in crops:
            raise ValueError(f"unknown crop_id: {s['crop_id']}")
    last_year = date.today().year - 1
    poly, details = r.get("polygon"), r.get("details") or {}
    yield_check: list = []
    if details.get("yields_t_ha"):  # per-request copy; the cached knowledge base is never mutated
        crops, yield_check = scale_yields(crops, details["yields_t_ha"], r["current_rotation"])
    eff = IRRIGATION_EFFICIENCY[details["irrigation_method"]] if details.get("irrigation_method") else 1.0
    quota = None
    if details.get("water_quota_m3_yr") is not None:
        q = details["water_quota_m3_yr"]
        quota = {"quota_m3_yr": q, "basis": "field_total" if poly else "per_ha",
                 "quota_m3_ha_yr": q / poly["area_ha"] if poly else q}

    wx0 = power.fetch_daily(lat, lon, date(WEATHER_START_YEAR, 1, 1), date(last_year, 12, 31))
    pcorr, extra_gaps = None, []
    try:  # POWER's 0.5 deg cell is too wet for many plains: rescale it month by month to satellite rain
        sat = precip.fetch_precip_daily(lat, lon, date(WEATHER_START_YEAR, 1, 1), date(last_year, 12, 31))
        wx0 = precip.bias_correct_power(wx0, sat)
        pcorr = wx0.attrs["precip_correction"]
        extra_gaps.append({"text": {
            "en": "Rain is POWER's daily pattern rescaled month by month to satellite totals (5–10 km pixels); a single storm over your "
                  "field can still differ.",
            "tr": "Yağış, NASA POWER'ın günlük deseninin aylık uydu toplamlarına (5–10 km piksel) göre ölçeklenmiş hâli; "
                  "tarlanıza düşen tek bir sağanak yine de farklı olabilir."}})
    except Exception:  # degrade gracefully: raw POWER rain, say so
        extra_gaps.append({"text": {
            "en": "Satellite rainfall was unavailable, so rain is raw NASA POWER and may be too high on dry plains.",
            "tr": "Uydu yağış verisine ulaşılamadı; yağış ham NASA POWER değeri ve kurak ovalarda gerçekte olandan yüksek olabilir."}})
    elev_p = float(wx0.attrs.get("elevation_m") or 0.0)
    wx_obs = add_et0(wx0, lat, elev_p)
    wx_obs.attrs = dict(wx0.attrs)
    climate = climate_profile(wx_obs, lat)
    wx_sim = _apply_scenario(wx_obs, r["scenario"], lat)

    try:
        ndvi = modis.fetch_ndvi(lat, lon, NDVI_START, date.today())
        fm = analyze_ndvi(ndvi)
    except Exception:  # degrade gracefully: no field memory
        fm = {"ndvi": [], "years": [], "bare_probability": [], "bare_windows": [], "stress_years": []}
    sp_model = soil_mod.fetch_soil(lat, lon)
    sp = override_soil(sp_model, details["soil"]) if details.get("soil") else sp_model
    soil = {"clay_pct": sp.clay_pct, "sand_pct": sp.sand_pct, "silt_pct": sp.silt_pct, "soc_gkg": sp.soc_gkg, "ph": sp.ph,
            "texture_class": sp.texture_class, "taw_mm_per_m": sp.taw_mm_per_m, "source_id": sp.source_id}
    try:
        tr = terrain_mod.fetch_terrain(lat, lon)
    except Exception:
        tr = {"elevation_m": elev_p, "slope_pct": None, "source_id": "nasa_power"}
    terrain = {"elevation_m": tr.get("elevation_m"), "slope_pct": tr.get("slope_pct")}

    # baseline + candidates
    steps = [RotationStep(crop_id=s["crop_id"], year=i + 1, irrigation=s["irrigation"])
             for i, s in enumerate(r["current_rotation"])]
    base_rot = Rotation(id="baseline", name={"en": "Current rotation", "tr": "Mevcut rotasyon"}, archetype="baseline", steps=steps)
    base = simulate_rotation(base_rot, wx_sim, sp, crops, _start_years(WEATHER_START_YEAR, last_year, _n_main(steps, crops)),
                             irrigation_efficiency=eff)
    base_idx = base.get("erosion_index") or None
    zone = zone_lookup.zone_at(lat, lon)
    policy = zone_policy(zone_lookup.zone_crops(zone["key"]) if zone else None, crops, {s.crop_id for s in steps})
    cons = dict(r["constraints"])
    if policy:  # only crops verified in the zone may enter generated candidates
        cons["exclude_crops"] = sorted(set(cons.get("exclude_crops") or ()) | set(policy["exclude"]))
    if details.get("excluded_crops"):
        cons["exclude_crops"] = sorted(set(cons.get("exclude_crops") or ()) | set(details["excluded_crops"]))
    if quota:  # the quota replaces water access: it alone bounds irrigation (CONTRACTS 6.2)
        has_water = quota["quota_m3_ha_yr"] > 0
        cons["water_access"] = "full" if has_water else "none"
        cons["max_irrigated_share"] = 1.0 if has_water else 0.0
    cands = generate_candidates(crops, climate, fm, cons)
    sims = _simulate_all(cands, wx_sim, sp, crops, last_year, base_idx, eff)
    if quota:  # drop candidates above the per-ha quota; keep them (marked) if fewer than 3 would remain
        qh = quota["quota_m3_ha_yr"]
        within = [x for x in sims if _p50(x["indicators"]["water_m3_ha_yr"]) <= qh]
        relaxed = sum(1 for x in within if x.get("feasible", True)) < 3
        quota["n_candidates_excluded"] = 0 if relaxed else len(sims) - len(within)
        quota["relaxed"] = relaxed
        if not relaxed:
            sims = within
    results = [base] + sims
    card_info = None
    if policy:
        extra = _simulate_single(policy, crops, cons, wx_sim, sp, last_year, base_idx)
        picked, notes = pick_cards(results, r["priorities"], policy, extra, extra,
                                   _simulate_water(policy, wx_sim, sp, last_year))
        card_info = {"zone": zone["key"], "notes": notes, "allowed_crops": policy["allowed"],
                     "caution_crops": policy["caution"],
                     "limits": {"water_m3_ha_yr_max": base["indicators"]["water_m3_ha_yr"]["p50"],
                                "erosion_rel_max": max(base["indicators"].get("erosion_rel", 1.0), 1.0)}}
    else:
        picked = pick_strategies(results, r["priorities"])
    cand_names = {c.id: c.name for c in cands}

    # facts + evidence
    F = Facts()
    ids = _climate_facts(F, climate, fm, soil, "")
    _precip_fact(F, pcorr, ids)
    base_s = picked[0]
    ub = _user_block(F, r, crops, sp_model, sp, fm, base, quota, yield_check) if (poly or details) else {}
    ufid = ub.pop("_fid", {})
    if quota:
        quota["baseline_exceeds"] = bool(_p50(base_s["indicators"]["water_m3_ha_yr"]) > quota["quota_m3_ha_yr"])
    base_crops = {s["crop_id"] for s in base_s["steps"]}
    ordered = picked if policy else [picked[0]] + [s for a in ARCH_ORDER for s in picked[1:] if s["archetype"] == a]
    base_chain = {"en": _crop_chain(base_s, crops, "en"), "tr": _crop_chain(base_s, crops, "tr")}
    strategies = []
    water_src: set = set()
    for st in ordered:
        deltas = _strategy_deltas(F, st, base_s, ids)
        ev = _evidence(st, base_s, deltas, ids, crops, base_crops)
        for p in st.get("parts", []):
            if p.get("water_modeled"):
                fid = _water_fact(F, p)
                ev["why"].append({"text": {"en": F.items[int(fid[1:]) - 1]["text"]["en"], "tr": F.items[int(fid[1:]) - 1]["text"]["tr"]},
                                  "facts": [fid]})
                water_src.update(water_models()[p["water"]["model"]].sources)
        ev["gaps"] = ev["gaps"] + copy.deepcopy(extra_gaps)
        if poly:
            ev["gaps"].append({"text": {
                "en": "Your field boundary is recorded, but the 250 m MODIS pixel and the 0.5° weather grid still describe the "
                      "surroundings, so the boundary does not sharpen these results yet (planned: 30 m HLS imagery).",
                "tr": "Tarla sınırınız kaydedildi, ancak 250 m'lik MODIS pikseli ve 0,5° hava ızgarası hâlâ çevreyi tanımlıyor; "
                      "bu yüzden sınır sonuçları henüz keskinleştirmiyor (planlanan: 30 m HLS görüntüleri)."}})
        _user_evidence(ev, st, deltas, ufid, quota, details, crops)
        out = {k: st[k] for k in ("id", "archetype", "name", "cycle_years", "calendar", "indicators", "score",
                                   "score_breakdown", "feasibility") if k in st}
        if st["archetype"] == "baseline" or st.get("rotation_id") not in cand_names:
            out["rotation_name"] = {"en": _crop_chain(st, crops, "en"), "tr": _crop_chain(st, crops, "tr")}
        else:
            out["rotation_name"] = cand_names[st["rotation_id"]]
        for k in ("coverage", "water_coverage", "trials"):
            if k in st:
                out[k] = st[k]
        if "parts" in st:
            out["parts"] = [{**p, "rotation_name": cand_names.get(p["rotation_id"], base_chain)} if p["kind"] == "rotation" else p
                            for p in st["parts"]]
        out["steps"] = st["steps"]
        if quota:
            out["exceeds_quota"] = bool(_p50(st["indicators"]["water_m3_ha_yr"]) > quota["quota_m3_ha_yr"])
        out["evidence"] = ev
        strategies.append(out)

    used = {f["source_id"] for f in F.items} | {"nasa_power", "fao56", soil["source_id"], "srtm_terrain_tiles"}
    used |= water_src
    if pcorr:
        used.add(pcorr["source_id"])
    if fm.get("years"):
        used.add("modis_mod13q1")
    if "irrigation_method" in details:
        used.add("irrigation_efficiency")
    sources = [{"id": k, **SOURCES[k]} for k in SOURCES if k in used]

    lab = r.get("label") or ("Çumra, Konya" if abs(lat - 37.60) < 0.1 and abs(lon - 32.75) < 0.1 else f"{lat:.2f}, {lon:.2f}")
    report = {
        "location": {"lat": lat, "lon": lon, "elevation_m": terrain["elevation_m"] if terrain["elevation_m"] is not None else elev_p,
                     "label": lab},
        "sources": sources,
        "climate": climate,
        "field_memory": fm,
        "soil": soil,
        "terrain": terrain,
        "strategies": strategies,
        "facts": F.items,
        "disclaimer": DISCLAIMER,
        "scenario": r["scenario"],
        "precip_correction": pcorr,
        "cards": card_info,
    }
    if poly:
        report["location"]["area_ha"] = round(poly["area_ha"], 2)
        report["location"]["polygon"] = {"type": "Polygon", "coordinates": [poly["ring"]]}
    if ub.get("user_inputs"):
        report["user_inputs"] = ub["user_inputs"]
    if "irrigation_method" in details:
        report["irrigation"] = {"method": details["irrigation_method"], "efficiency": eff, "source_id": "irrigation_efficiency"}
    if quota:
        report["quota"] = {k: (round(v, 1) if k == "quota_m3_ha_yr" else v) for k, v in quota.items()}
    if yield_check:
        report["yield_check"] = yield_check
    for k in ("history_check", "irrigation_check"):
        if k in ub:
            report[k] = ub[k]
    return _clean(report)


# ------------------------------------------------------------------ cached entry point
_CACHE: OrderedDict[str, dict] = OrderedDict()
_LOCK = threading.Lock()
CACHE_SIZE = 16


def get_field_report(req: dict | None) -> dict:
    key = json.dumps({k: v for k, v in normalize_request(req).items() if k != "lang"}, sort_keys=True)
    with _LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
    rep = build_field_report(req)
    with _LOCK:
        _CACHE[key] = rep
        while len(_CACHE) > CACHE_SIZE:
            _CACHE.popitem(last=False)
    return rep
