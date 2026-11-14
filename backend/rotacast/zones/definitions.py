"""Expert definition of the Konya agro-microclimate zones (docs/METHODS.md, section "Konya zones").

Zones follow district (ilçe) boundaries, refined by two physical rules:

* **Toros highlands:** cells at or above ``TOROS_MIN_ELEV_M`` south of ``TOROS_MAX_LAT`` in the districts listed in
  ``TOROS_ELEVATION_DISTRICTS`` join the Toros zone (mountain climate does not stop at a district line).
* **Lake effect:** land within ``LAKE_BUFFER_KM`` of Beyşehir Gölü joins the Beyşehir zone.

The lake surfaces themselves are not part of any zone. District names match geoBoundaries ADM2 ``shapeName``.
MGM stations (1991-2020 climate classifications) give each zone its official climate profile.
"""
from __future__ import annotations

TOROS_MIN_ELEV_M = 1500.0
TOROS_MAX_LAT = 37.75
TOROS_ELEVATION_DISTRICTS = {"Seydişehir", "Akören", "Meram", "Güneysınır", "Halkapınar", "Ereğli", "Beyşehir"}
LAKE_BUFFER_KM = 8.0
LAKE_EFFECT = "Beyşehir Gölü"
LAKES = ("Beyşehir Gölü", "Tuz Gölü", "Suğla Gölü")

ZONES: list[dict] = [
    {
        "id": 1, "key": "toros", "color": "#4E79A7",
        "name_tr": "Güney Toroslar dağ kuşağı", "name_en": "Southern Taurus highlands",
        "districts": ["Hadim", "Taşkent", "Bozkır", "Ahırlı", "Yalıhüyük", "Derebucak"],
        "stations": ["HADIM"],
        "desc_tr": "Akdeniz etkili dağ iklimi. Yükselti nedeniyle serin yaz ve soğuk kış, yamaçlarda daha fazla yağış. "
                   "Bakı etkisi güçlü: güneye bakan yamaçlar sıcak ve kuru, kuzeye bakanlar serin ve nemli. "
                   "Vadi tabanı ile yüksek yamaç arasında ürün takvimi değişebilir.",
        "desc_en": "Mediterranean-influenced mountain climate: cool summers, cold winters, more orographic rain. "
                   "Strong aspect effect (south slopes warm and dry, north slopes cool and moist). "
                   "Crop calendars differ between valley floors and upper slopes.",
    },
    {
        "id": 2, "key": "seydisehir", "color": "#59A14F",
        "name_tr": "Seydişehir–Suğla nemli geçiş ovası", "name_en": "Seydişehir–Suğla humid transition basin",
        "districts": ["Seydişehir", "Akören"],
        "stations": ["SEYDISEHIR"],
        "desc_tr": "Akdeniz–karasal geçiş. Toroslardan gelen nemli hava ve Suğla Gölü etkisi. Çevre dağlardan inen soğuk "
                   "hava ovada birikir: ilkbahar ve sonbaharda don çukuru riski. Resmî sınıflandırmada nemli, ama yazın "
                   "güçlü su açığı var.",
        "desc_en": "Mediterranean–continental transition with moist air from the Taurus and the Suğla lake effect. "
                   "Cold air pools on the plain: spring and autumn frost-pocket risk. Officially humid, yet with a strong "
                   "summer water deficit.",
    },
    {
        "id": 3, "key": "beysehir", "color": "#76B7B2",
        "name_tr": "Beyşehir Gölü çevresi", "name_en": "Beyşehir lake district",
        "districts": ["Beyşehir", "Hüyük"],
        "stations": ["BEYSEHIR"],
        "desc_tr": "Göl etkili Akdeniz–karasal geçiş. Göl nedeniyle daha yüksek bağıl nem ve yumuşamış sıcaklık "
                   "değişimleri. Kış yağışında Akdeniz, yaz sıcaklığında karasal karakter. Göl kıyısı ile yüksek "
                   "kesimler arasında belirgin fark.",
        "desc_en": "Lake-moderated Mediterranean–continental transition: higher humidity and damped temperature swings. "
                   "Mediterranean winter rain, continental summer heat; clear contrast between shore and uplands.",
    },
    {
        "id": 4, "key": "west", "color": "#B07AA1",
        "name_tr": "Batı geçiş kuşağı (Akşehir–Ilgın–Yunak)", "name_en": "Western transition belt (Akşehir–Ilgın–Yunak)",
        "districts": ["Akşehir", "Tuzlukçu", "Doğanhisar", "Ilgın", "Kadınhanı", "Derbent", "Yunak", "Çeltik"],
        "stations": ["AKSEHIR", "ILGIN", "YUNAK"],
        "desc_tr": "Akdeniz etkisi zayıflamış, karasal özellikler güçlenmiş. Batıdaki dağ ve göl sistemlerinden kısmi "
                   "nem etkisi: merkez ovadan daha nemli. Kış donları belirgin, rakım ve yamaç yönüne göre yerel farklar.",
        "desc_en": "Weakened Mediterranean influence, stronger continental traits. Some moisture from the western "
                   "mountains and lakes: wetter than the central plain. Marked winter frosts; local contrasts by "
                   "elevation and slope.",
    },
    {
        "id": 5, "key": "central", "color": "#EDC948",
        "name_tr": "Merkez ova (Konya–Çumra)", "name_en": "Central plain (Konya–Çumra)",
        "districts": ["Selçuklu", "Meram", "Karatay", "Çumra", "Sarayönü", "Güneysınır"],
        "stations": ["KONYA", "CUMRA"],
        "desc_tr": "Karasal yarı kurak step. Sıcak ve kurak yaz, soğuk kış, düşük yağış ve yüksek buharlaşma. "
                   "Geceleri hızlı sıcaklık kaybı. Sulanan geniş parseller çevrelerine göre daha serin ve nemli.",
        "desc_en": "Continental semi-arid steppe: hot dry summers, cold winters, low rain and high evaporation, fast "
                   "night-time cooling. Large irrigated parcels are locally cooler and moister.",
    },
    {
        "id": 6, "key": "north", "color": "#9C755F",
        "name_tr": "Kuzey step ve Tuz Gölü çevresi", "name_en": "Northern steppe and Tuz Gölü fringe",
        "districts": ["Cihanbeyli", "Kulu", "Altınekin"],
        "stations": ["CIHANBEYLI", "KULU"],
        "desc_tr": "Kurak–yarı kurak, kışları soğuk step. Açık ve düz arazide kuvvetli rüzgâr. Tuz Gölü çevresinde "
                   "soğuk-kurak ve tuzlu step etkisi, tuzlu ve alkali topraklar.",
        "desc_en": "Arid to semi-arid steppe with cold winters and strong winds on open flat land. Around Tuz Gölü: "
                   "cold, dry, saline steppe with salty and alkaline soils.",
    },
    {
        "id": 7, "key": "karapinar", "color": "#F28E2B",
        "name_tr": "Karapınar–Ereğli çok kurak kuşak", "name_en": "Karapınar–Ereğli very dry belt",
        "districts": ["Karapınar", "Ereğli", "Emirgazi", "Halkapınar"],
        "stations": ["KARAPINAR", "EREGLI KONYA"],
        "desc_tr": "Çok kurak karasal. Çok düşük yağış, güçlü buharlaşma, yazın yüksek sıcaklık, kışın don riski. "
                   "Çıplak toprak ve rüzgâr erozyonu. Sulanan parseller ile çevredeki kuru alan arasında belirgin fark.",
        "desc_en": "Very dry continental: very low rain, strong evaporation, hot summers, winter frost. Bare soil and "
                   "wind erosion; sharp contrast between irrigated parcels and the dry surroundings.",
    },
]


def district_zone_map() -> dict[str, int]:
    out: dict[str, int] = {}
    for z in ZONES:
        for d in z["districts"]:
            if d in out:
                raise ValueError(f"district {d} assigned twice")
            out[d] = z["id"]
    return out
