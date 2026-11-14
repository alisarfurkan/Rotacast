"""Official climate classifications of MGM (Turkish State Meteorological Service) stations in Konya, 1991-2020.

Source pages: ``https://www.mgm.gov.tr/iklim/iklim-siniflandirmalari.aspx?m=<STATION>``. Each page lists, for one
station, the Aydeniz drought coefficient, Erinç precipitation-effectiveness index, De Martonne aridity index,
Trewartha winter/summer mean temperatures and the Thornthwaite climate class. Pages are cached as raw HTML under
``data/cache/mgm_climate_class``.
"""
from __future__ import annotations

import html
import re

from ..connectors.cache import cached_get_bytes

SOURCE_ID = "mgm_climate_class"
URL = "https://www.mgm.gov.tr/iklim/iklim-siniflandirmalari.aspx"
PERIOD = "1991-2020"

# MGM station code -> display name. These are all MGM stations listed for Konya province.
STATIONS = {
    "KONYA": "Konya", "CUMRA": "Çumra", "EREGLI KONYA": "Ereğli", "HADIM": "Hadim", "ILGIN": "Ilgın",
    "KARAPINAR": "Karapınar", "KULU": "Kulu", "SEYDISEHIR": "Seydişehir", "YUNAK": "Yunak",
    "AKSEHIR": "Akşehir", "BEYSEHIR": "Beyşehir", "CIHANBEYLI": "Cihanbeyli",
}


def page_url(station: str) -> str:
    return f"{URL}?m={station}"


def _text(raw: bytes) -> str:
    t = raw.decode("utf-8", errors="ignore")
    t = re.sub(r"<script.*?</script>", " ", t, flags=re.S | re.I)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)))


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def parse(raw: bytes) -> dict:
    """Extract the classification values from one MGM page (raises ValueError when the layout is not found)."""
    s = _text(raw)
    pats = {
        "aydeniz": r"Aydeniz İklim Sınıflandırması Kuraklık Katsayısı ([\d,.-]+) İklim Tipi (.+?) Erinç",
        "erinc": r"Erinç İklim Sınıflandırması Yağış Etkinlik İndisi ([\d,.-]+) İklim Tipi (.+?) DeMartonne",
        "de_martonne": r"DeMartonne İklim Sınıflandırması Kuraklık İndisi ([\d,.-]+) İklim Tipi (.+?) Trewartha",
        "trewartha_winter": r"Kış mevsimi iklim tipi (.+?), \(([\d,.-]+)\)",
        "trewartha_summer": r"Yaz mevsimi iklim tipi (.+?) \(([\d,.-]+)\)",
        "thornthwaite": r"Thornthwaite İklim Sınıflandırması İklim Sınıfı (\S+) (.+?) İklim Sınıflandırmaları Hakkında",
    }
    out: dict = {}
    for key, p in pats.items():
        m = re.search(p, s)
        if not m:
            raise ValueError(f"MGM page layout changed: {key} not found")
        a, b = m.group(1).strip(), m.group(2).strip()
        if key.startswith("trewartha"):
            out[key] = {"type": a, "mean_temp_c": _num(b)}
        elif key == "thornthwaite":
            out[key] = {"class": a, "explanation": b}
        else:
            out[key] = {"index": _num(a), "type": b}
    return out


def fetch_station(station: str) -> dict:
    data = parse(cached_get_bytes(SOURCE_ID, page_url(station)))
    data.update(station=station, name=STATIONS.get(station, station), period=PERIOD, url=page_url(station))
    return data


def fetch_all() -> dict[str, dict]:
    return {code: fetch_station(code) for code in STATIONS}
