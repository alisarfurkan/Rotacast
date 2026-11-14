# Tek yıllık özel ürünler: motor parametreleri araştırması (2026-11-14, DOĞRULANMADI)

Amaç: kimyon, anason, çemen, kişniş, çörekotu, karabuğday, rezene için `crops.yaml` parametreleri.
Durum: **hiçbiri motora eklenmedi.** Su için Kc kaynakları kısmen bulundu; gelir için gereken Konya verimi ve
çiftçi fiyatı bulunamadı. Kural "tahmine yer yok" olduğu için eksik ürün eklenmiyor.

## Bulunan Kc kaynakları (yalnız arama özetlerinden; tam metinle kontrol edilmeli)

| Ürün | Kc ini / dev / mid / end | Evre süreleri (gün) | Kaynak | Not |
|---|---|---|---|---|
| Kimyon | 0.65 / 0.92 / 1.21 / 0.85 | 24 / 40 / 31 / 19 | Birjand lizimetre çalışması, J. Water & Soil (Ferdowsi Üniv.) https://jsw.um.ac.ir/article_38177_en.html | Kaynak metinde tutarsızlık var, tam makaleyle kontrol |
| Kişniş | 0.66 / 1.19 / 1.36 / 0.98 (Kcb 0.21 / 0.72 / 1.10 / 0.79) | ? | ASCE J. Irrig. Drain. Eng., yarı kurak, 2010–2011, doi 10.1061/(ASCE)IR.1943-4774.0000561 | Tek ve çift Kc |
| Çörekotu | çok dağınık: 0.59/0.91/1.29/0.78 (Irrig. Sci. 2013, doi 10.1007/s00271-013-0412-2); 0.75/1.02/1.21/0.80 (Fasa); 0.39/0.53/0.59/0.28 (Birjand) | ? | https://link.springer.com/article/10.1007/s00271-013-0412-2 | Hangi değerin Konya'ya uyduğu belirsiz |
| Karabuğday | 0.58 / 0.59 / 1.10 / 0.74 | ? | Theor. Appl. Climatol. 2014, Japonya tarla ölçümü | İklim farklı |
| Rezene | 0.70 / 0.95 / 1.15 / 0.90 | 20 / ? / 60 / ? | Meena vd., Hindistan, pan yöntemi (lizimetre değil) | Zayıf kaynak |
| Çemen | bulunamadı | | | |
| Anason | bulunamadı (Arjantin tezi var, değerler görülmedi) | | https://editorial.unca.edu.ar/ | |

### Pereira, Mota, Raziei, Paredes (2024), Irrigation Science 42(6), doi 10.1007/s00271-024-00960-4 (açık erişim)
Tablolar makale sayfasından okundu (2026-11-14), değerler tablodaki gibi:

| Ürün | Tablo | Kc ini / mid / end | Kök derinliği (m) | p | Not |
|---|---|---|---|---|---|
| Kişniş | T7 standart | 0.60 / 1.10 / 1.05 | 0.30–0.50 (T8) | 0.30 | T4 gözlem (Silva 2013): 0.82 / 1.07 / 0.93 |
| Çemen | T7 standart | 0.60 / 1.00 / 0.75 | 0.30–0.80 (T8) | 0.40 | |
| Kimyon | T6 gözlem | 0.65 / 1.21 / 0.85 | – | – | Reyhani & Siuki 2015, Birjand, karasal kurak, drenajlı lizimetre |
| Çörekotu | T6 gözlem | 0.59 / 1.29 / 0.78 | – | – | Ghamarnia vd. 2014, Kermanshah, yarı kurak |
| Karabuğday | T6 gözlem | 0.58 / 1.10 / 0.74 | – | – | Yan vd. 2015, Japonya, nemli |
| Rezene | T6 gözlem | 0.35 / 1.15 / 0.45 | – | – | Mohammed vd. 2020, Mısır, kurak |
| Anason | yok | | | | Makalede yer almıyor |

Standart (T7) değer yalnız kişniş ve çemen için var; diğerleri tek çalışmalık gözlem. Evre süreleri bu tablolarda yok.

## Konya verimi (TÜİK 2024, "2026 Konya Tarımı", İl Tarım ve Orman Müdürlüğü, Tablo 6, s. 17)
https://konya.tarimorman.gov.tr/Belgeler/kitap/%C4%B0l_Tar%C4%B1m_ve_Orman_Ocak_26_4DonemV2.pdf

| Ürün | 2023 alan (da) / üretim (t) | 2024 alan (da) / üretim (t) | 2024 ortalama verim | Not |
|---|---|---|---|---|
| Kimyon | 43.266 / 2.990 | 62.210 / 3.129 | ~50 kg/da (0,50 t/ha) | Türkiye üretiminin %18,4'ü (2024) |
| Anason | 5.719 / 447 | 15.365 / 1.106 | ~72 kg/da (0,72 t/ha) | |
| Rezene | tablo metni bozuk okundu | | | PDF'te elle kontrol |
| Çörekotu, kişniş, çemen, karabuğday | kitapta yok | | | |

Dikkat: bunlar çoğu kuru tarım olan il ortalamaları. Motor `yield_t_ha.irrigated` alanına su kısıtsız potansiyel
verim (Ym) bekliyor; il ortalaması bunun yerine konamaz, yalnız `rainfed` kalibrasyon değeri olabilir.

## Bulunamayanlar (gelir hesabı için şart)
- **Konya verimi:** TÜİK ilçe verisi (`konyatarimistilce2025.pdf` 404). Tek bulunan: Konya kimyon denemesi 54–69 kg/da
  (Selçuk Üniv. 2003, https://dergipark.org.tr/en/download/article-file/3076162), deneme verisi, ortalama değil.
  Kimyon üretiminin %26'sı Konya'da (TÜİK 2023, https://www.agrifoodscience.com/index.php/TURJAF/article/view/6969).
- **Çiftçi fiyatı (TL/kg):** Konya Ticaret Borsası / İzmir Ticaret Borsası bültenlerinde aranmalı; aramada çıkmadı.
- **Sıcaklık eşikleri, GDD:** FAO ECOCROP sayfalarından alınabilir, henüz bakılmadı.

## Önerilen yol
1. Pereira 2024 PDF'i (Kc, evre, kök derinliği, p) → su tarafı.
2. TÜİK biruni veya İl Tarım kitabından Konya ekim alanı/üretim → verim.
3. İTB veya Konya TB bülteninden 2024–2025 fiyat → gelir.
4. ECOCROP → don/sıcak eşikleri.
Dördü de olan ürün `crops.yaml`'a girer; kartlarda "hesapta yok" uyarısı kendiliğinden kalkar.
