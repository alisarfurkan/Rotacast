# Rotacast — Proje Planı (taslak v0.1)

**Hackathon:** NASA Space Apps Challenge 2026, 14-15 Kasım 2026
**Kategori:** Field Shift: Adapting Farms with NASA Data
**Çalışma adı:** *Rotacast* (rotation + forecast). İsim değiştirilebilir.
**Durum:** Planlama aşaması. Kod yazılmadı.
**Demo bölgesi:** Konya Ovası (kesinleşti). Araç küresel çalışacak, hikâye Konya üzerinden anlatılacak.

---

## 0. Önce kurallar: bilmemiz gereken kısıtlar

| Kural | Kaynak | Bize etkisi |
|---|---|---|
| **"Teams are not allowed to begin working on the challenges prior to the hackathon."** | Participant FAQ | Proje kodu, veri hattı ve tasarım dosyaları **14 Kasım'dan önce üretilmemeli.** Fikir, araştırma ve araç öğrenme gri alanda ama savunulabilir. Kod sıfırdan event sırasında yazılacak. |
| Ürettiğimiz her şey açık kaynak (OSI lisansı) olmalı | Terms & Conditions | Repo **MIT lisanslı**, herkese açık GitHub. |
| NASA dışı veri ve kod da serbestçe erişilebilir veya açık lisanslı olmalı | T&C | SoilGrids (CC-BY 4.0) ve FAO tabloları uygun. Ticari ve kapalı veri kullanmıyoruz. |
| **Kullanılan her kaynak atıf almalı.** Atıf yoksa ödül geri alınabilir | T&C | `docs/SOURCES.md` ilk saatten itibaren tutulacak. |
| Gönderide **SI (yapay zekâ) kullanımı açıklanmalı** | FAQ | Claude kullanımımızı (kod üretimi, metin açıklamaları) açıkça yazacağız. Bunu bir artı olarak sunacağız. |
| Kaynaklar sekmesi, Project Submission Guide ve Judging Guide **13 Kasım'da** yayınlanacak | FAQ | 13 Kasım'da bu plan, bu belgelere göre güncellenecek (bkz. §12). |
| Takım en fazla 6 kişi olabilir, tek challenge seçilebilir | FAQ | — |

---

## 1. Jüri ne istiyor? Kazanmak için hedef listesi

**Geçmiş yılların jüri kriterleri** (2026 rehberi 13 Kasım'da kesinleşecek): *Influence/Impact, Creativity, Validity, Relevance, Presentation.* Her biri eşit ağırlıklı.

Challenge metni bize neredeyse bir **kabul listesi** veriyor. Bunların hepsini karşılayan çok az takım olacak:

| # | Challenge'ın istediği | Rotacast'te karşılığı |
|---|---|---|
| R1 | NASA EO + yerel toprak + ürün özellikleri + çiftçi öncelikleri | POWER, MODIS, SMAP, SRTM, GRACE + SoilGrids + ürün bilgi tabanı + öncelik kaydırıcıları |
| R2 | Tarlanın **boş kaldığı dönemleri** göstermek | NDVI fenolojisinden 25 yıllık **"Tarla Hafızası"** takvimi |
| R3 | Ürünün **savunmasız olduğu sezonları** göstermek | Su dengesi modelinden stres günleri, don ve sıcak stresi olasılıkları |
| R4 | **Mevcut rotasyon dahil en az 3 strateji** karşılaştırmak | Mevcut rotasyon + 3 arketip strateji, yan yana |
| R5 | Her strateji için **neden, kanıt, fayda, bilgi boşluğu, risk** | **Kanıt Kartları**: her iddia bir veri setine ve değere bağlı |
| R6 | Belirsizliği açıklamak, yerel uzmanın nerede gerektiğini belirtmek | 20+ yıllık ensemble ile P10/P50/P90 aralıkları ve "yerelde doğrula" etiketleri |
| R7 | Farklı çözünürlükteki verileri ortak gride harmonize etmek | Tarla noktası ve tampon alanında birleştirme. Yöntem `docs/METHODS.md`'de belgelenecek |
| R8 | Bilimsel terimleri açıklamak (ET, NDVI, anomali…) | Arayüzde terim üzerine gelince açılan açıklamalar |
| R9 | Uydu verisi ile yer ölçümü farkı | "Bu veri nereden geliyor?" panelleri, çözünürlük ve sınırlılıkları |
| R10 | Etkileşimli harita, zaman çizelgesi, **senaryo kaydırıcıları** | Harita + zaman çizelgesi + "+2 °C / −%20 yağış" kaydırıcıları |
| R11 | Çiftçi kısıtları (su, ekipman, pazar) | Girdi formu, sonuçlar bunlara göre filtrelenir |
| R12 | Aracın çiftçiyi **desteklediğini, yerine geçmediğini** vurgulamak | Her ekranda kalıcı not ve her kartta "yerel uzmana sor" alanı |

> **Strateji:** Diğer takımlar genelde birkaç maddeyi derinlemesine yapar. Biz bu 12 maddenin **hepsini görünür biçimde** karşılayacak, sunumda bu tabloyu göstereceğiz. Bu, Relevance ve Validity puanını garantiler.

---

## 2. Rakip analizi: 130 kişinin büyük kısmı ne yapacak?

Bu kategoride tipik takım projesi şu olacak:
1. Haritada NDVI katmanı ve birkaç grafik (Streamlit veya Leaflet)
2. "Bu bölgeye şu ürünü ek" diyen bir **LLM sohbet botu**. Sayılar modelden değil, LLM'in kendi tahmininden gelir.
3. Statik bir ürün tablosu

**Zayıf noktaları:** Bilimsel dayanak yok (LLM halüsinasyonu), belirsizlik yok, mevcut rotasyonla karşılaştırma yok ve tarla düzeyinde bir hikâye yok.

**Bizim farkımız (sunumdaki 5 ana mesaj):**
1. **Tarla Hafızası:** Çiftçiden veri istemeden, 25 yıllık uydu kaydından *bu tarlanın* gerçek ekim takvimini, boş dönemlerini ve kuraklık yıllarını çıkarıyoruz.
2. **Fiziksel model, LLM tahmini değil:** FAO-56 günlük su dengesi, NASA POWER iklim verisiyle 20+ geçmiş yıl üzerinde çalışıyor. Her rotasyon için bir **risk dağılımı** üretiyoruz, tek bir tahmin değil.
3. **İzlenebilir kanıt:** Her öneri cümlesi bir NASA veri setine ve sayıya bağlı. LLM yalnızca bu sayıları sade dile çeviriyor ve kaynak gösteriyor.
4. **İklim kayması merceği:** 1991–2005 ile 2010–2024 dönemleri karşılaştırılıyor: son don tarihi kaç gün kaydı, sıcak gün sayısı kaç arttı, yağış hangi aya kaydı. Challenge'ın adındaki "shift" tam olarak budur.
5. **Somut bir hikâye:** Konya Ovası. Türkiye'nin tahıl ambarı, GRACE'te belirgin yeraltı suyu düşüşü ve obruklar. "Bu rotasyon değişikliği tarla başına yılda X m³ su tasarrufu sağlar."

---

## 3. Ürün konsepti

**Tek cümle:** Rotacast, çiftçinin tarlasını haritada seçip mevcut ekim nöbetini ve önceliklerini girdiği, NASA'nın 25 yıllık uydu kayıtlarıyla tarlanın geçmişini okuyup alternatif rotasyonları su, toprak sağlığı ve risk açısından kanıtlarıyla karşılaştıran bir karar destek aracıdır.

### Kullanıcı akışı (demo senaryosu)
1. **Tarlanı bul:** Haritada nokta seçilir veya poligon çizilir. Konya demo tarlası tek tıkla açılır.
2. **Bize tarlanı anlat:** Mevcut rotasyon (ör. buğday → şeker pancarı → mısır), sulama imkânı (yok / kısıtlı / tam), ekipman ve pazar kısıtları.
3. **Önceliklerin:** Kaydırıcılar: su tasarrufu, toprak sağlığı, gelir, erozyon, iş yükü.
4. **Tarla Hafızası:** 25 yıllık NDVI şeridi. Boş dönemler, stres sezonları ve kuraklık yılları (ör. 2021) işaretli. Yanında iklim kayması kartı.
5. **Strateji karşılaştırması:** Mevcut rotasyon ve 3 arketip yan yana:
   - 💧 *Su Koruyucu*: düşük su ihtiyacı, kuraklığa dayanıklı ürünler
   - 🌱 *Toprak Kurucu*: baklagiller, örtü bitkileri, derin köklü ürünler
   - ⚖️ *Dengeli Gelir*: gelir ve risk dengesi
6. **Kanıt Kartı** (her strateji için): Neden önerildi, kanıt (veri seti ve değer), faydalar, bilgi boşlukları, yerelde kontrol edilmesi gereken riskler.
7. **Ne olursa?** Kaydırıcıları (+°C, −% yağış) oynayınca sıralama canlı olarak değişir.
8. **Rapor:** Ziraat mühendisiyle paylaşılabilecek tek sayfalık özet (yazdırılabilir).

---

## 4. Bilimsel motor (Validity puanının kaynağı)

Tüm hesaplar **deterministik ve açıklanabilir.** SI (LLM) sadece en son adımda anlatım için devreye girer.

### 4.1 İklim profili (NASA POWER, 1991→bugün, günlük)
- Büyüme derece-günleri (GDD), son ilkbahar ve ilk sonbahar donu tarihlerinin **olasılık dağılımı**
- Sıcak stresi günleri (Tmax > ürün eşiği), kurak periyotlar, aşırı yağış günleri
- Trendler: Sen eğimi ve Mann-Kendall testi. Erken dönem ile geç dönem karşılaştırması ("shift")
- Referans evapotranspirasyon **ET₀**: FAO-56 Penman-Monteith. POWER bunun için gereken her değişkeni veriyor (Tmax, Tmin, RH2M, WS2M, radyasyon). *14 Kasım'da kontrol edilecek:* ET₀ değerlerimizin FAO-56 örnek hesaplarıyla tutarlı olması.

### 4.2 Tarla Hafızası (MODIS MOD13Q1 NDVI, 250 m, 16 günlük, 2000→)
- Yıllık NDVI eğrisinden yumuşatma (Savitzky-Golay) ile fenoloji çıkarımı: yeşillenme, tepe, hasat
- **Boş dönem tespiti:** NDVI < eşik → ortalama boş pencere ("Temmuz–Ekim arası %80 olasılıkla boş"). Örtü bitkisi fırsatı buradan çıkar.
- **Stres yılları:** NDVI anomalisi (z-skoru) ve kuraklık yıllarıyla eşleştirme
- Opsiyonel: Landsat/HLS 30 m ile tarla ölçeğinde netlik (Tier 2)

### 4.3 Toprak ve arazi
- **SoilGrids** (ISRIC): kil, kum, organik karbon, pH, yığın yoğunluğu. Toprak su tutma kapasitesi (TAW) pedotransfer fonksiyonuyla (Saxton-Rawls) hesaplanır.
- **SRTM** eğim → RUSLE **LS** faktörü (erozyon riski)
- RUSLE **R** (yağış erozivitesi), POWER veya GPM IMERG yağışından yaklaşık formülle hesaplanır.

### 4.4 Ürün Bilgi Tabanı (`crops.yaml`, ~25 ürün)
Her ürün için: sıcaklık aralıkları, baz sıcaklık, GDD ihtiyacı, don toleransı, sezon uzunluğu, **FAO-56 Kc değerleri ve evre süreleri**, kök derinliği, kuraklık toleransı, N fiksasyonu (kg N/ha), anız/organik madde girdisi, toprak örtüsü (RUSLE C), botanik familya (hastalık ve zararlı döngüsü kırma), yem değeri, kaba gelir sınıfı.
Kaynaklar: FAO-56 tabloları, FAO ECOCROP ve literatür. **Her değerin kaynağı dosyada yazılı olacak.**
Konya için öncelikli ürünler: buğday, arpa, şeker pancarı, mısır, ayçiçeği, nohut, mercimek, fiğ, yonca, aspir, kanola, korunga, örtü bitkisi karışımları (fiğ+arpa, çavdar).

### 4.5 Rotasyon Simülatörü
- Her aday rotasyon (3–4 yıllık dizi ve ekim pencereleri) için **FAO-56 günlük kök bölgesi su dengesi** çalıştırılır. Bu, geçmiş 20–30 yılın her biri ayrı bir senaryo olarak (ensemble) yapılır.
- Çıktılar (P10/P50/P90 ile):
  - **Su:** sulama ihtiyacı (mm, ha başına m³), su stresi günleri, verim riski göstergesi (Ks ile yaklaşık)
  - **İklim riski:** kritik evrelerde don ve sıcak stresi olasılığı
  - **Toprak sağlığı:** N dengesi (baklagil katkısı), organik madde girdisi göstergesi, toprak örtülü gün sayısı
  - **Erozyon:** RUSLE ile göreli kayıp (R·K·LS·C)
  - **Zararlı ve hastalık döngüsü kırma:** familya çeşitliliği, aynı konakçının tekrar sayısı
  - **Ekonomi:** kaba gelir sınıfı (yerel fiyat girilebilir; girilmezse "yerel veri gerekli" uyarısı)
- **Aday üretimi:** iklime uygun ürünler filtrelenir, agronomik kurallarla (aynı familya üst üste gelmez, N yıllık periyotta en az bir baklagil, boş pencerede örtü bitkisi) yüzlerce dizi listelenir, numpy ile hızlıca simüle edilir. **Pareto cephesinden** birbirinden farklı 3 arketip seçilir.
- **Skorlama:** Göstergeler normalize edilir ve çiftçi öncelik ağırlıklarıyla birleştirilir. Ağırlıklar ekranda görünür.

### 4.5.1 Rotasyon çıktısının biçimi (ekim sırası)
Challenge, tek bir "doğru" ekim sırası istemiyor. Çiftçinin **seçenekleri keşfetmesini** istiyor: mevcut rotasyon dahil en az 3 stratejinin karşılaştırılması. Yine de her strateji **somut bir ekim sırası** olarak verilecek, soyut tavsiye olarak değil:

- **Yıl yıl, sezon sezon takvim:** Her yıl için hangi ürün, hangi ekim ve hasat penceresinde ekilecek. Pencereler don olasılıkları ve GDD'den hesaplanır.
- **Boşluk doldurma:** Tarla Hafızası'nın gösterdiği boş pencerelere örtü bitkisi veya ara ürün yerleştirilir.
- **Sıranın gerekçesi:** "Nohut buğdaydan sonra geliyor çünkü bir sonraki buğdaya ~X kg N/ha bırakıyor ve buğday hastalık döngüsünü kırıyor."
- **Görsel:** Çok yıllı takvim şeridi (Gantt benzeri) üzerinde ürünler, boş dönemler ve risk sezonları.

**Konya için başlangıç hipotezleri.** Motor bunları doğrulayacak veya reddedecek, kesin öneri değildir:

| Strateji | Örnek sıra (sonbahar/ilkbahar ekimleri) | Beklenen güçlü yanı |
|---|---|---|
| Mevcut (temel) | Buğday → şeker pancarı → mısır | Yüksek gelir, yüksek sulama ihtiyacı |
| 💧 Su Koruyucu | Buğday → nohut → arpa → aspir | Çok düşük sulama, kuraklığa dayanıklı |
| 🌱 Toprak Kurucu | Buğday → (yaz: örtü/fiğ) → mercimek → arpa+fiğ → korunga/yonca | N fiksasyonu, toprak örtüsü, organik madde |
| ⚖️ Dengeli Gelir | Buğday → şeker pancarı (kısıtlı sulama) → nohut → ayçiçeği | Gelir korunurken su ihtiyacı azalır |

### 4.6 Doğrulama (sunumda "neden bize güvenmelisiniz" bölümü)
- **SMAP L4 kök bölgesi nem**i ile modelimizin toprak suyu (bağıl) karşılaştırılır: korelasyon grafiği.
- NDVI anomalisi ile bilinen kuraklık yılları (ör. Konya 2021) tutarlı mı?
- **GRACE/GRACE-FO** bölgesel su depolama trendi, su tasarrufu mesajının bağlamı olarak kullanılır.
- Sınırlılıklar dürüstçe yazılır: 250 m piksel karışıklığı, yeniden analiz verisinin yerel hatası, Kc değerlerinin çeşide göre değişmesi.

### 4.6.1 Havza Görünümü (jüri şablonu: tarladan bölgeye)
Tarla düzeyindeki motor, **Konya Kapalı Havzası** genelinde örnek bir tarla ağı üzerinde çalıştırılır ve sonuçlar bölge ölçeğine toplanır. Bu, sunumun "etki" bölümüdür.

- **Örnekleme:** Havza sınırı içinde düzenli bir grid kurulur. Yalnızca **MODIS MCD12Q1 arazi örtüsünde "cropland"** olan noktalar alınır (~40–80 nokta). Her nokta, temsil ettiği ekili alanla ağırlıklandırılır.
- **Senaryo:** Mevcut rotasyon ile her strateji karşılaştırılır. Benimseme oranı bir kaydırıcıyla ayarlanır (%10 / %30 / %50 tarla bu stratejiye geçerse).
- **Çıktılar** (P10/P50/P90 bantlarıyla):
  - **Bölge için en iyi strateji(ler):** Hangi alt bölgede hangi stratejinin öne çıktığını gösteren harita
  - **Havza su bütçesi:** Toplam sulama talebindeki değişim (milyon m³/yıl). Bu değer **GRACE/GRACE-FO** ile ölçülen havza su depolama kaybı trendiyle aynı grafikte gösterilir: "Bu benimseme oranında yıllık açığın yaklaşık %X'i kapanır."
  - **Üretim projeksiyonu (x yıl):** Ürün bazında üretim değişimi (ton). Temel verim değerleri açık lisanslı istatistiklerden (FAOSTAT / TÜİK) alınır. Su stresi düzeltmesi motordan gelir. Ufuk 5 ve 10 yıl; iklim kayması trendi senaryoya eklenir.
- **Dürüst çerçeve:** Bu bir **senaryo analizidir, tahmin değil.** Varsayımlar (benimseme oranı, fiyatlar, verimler) ekranda görünür ve değiştirilebilir.

### 4.7 SI (LLM) katmanı
- Motorun ürettiği **olgu JSON'u** (her olgunun bir ID'si ve veri kaynağı var) LLM'e verilir. LLM sadece bunları sade Türkçe ve İngilizce anlatıya çevirir ve olgu ID'lerine atıf yapar. Yeni sayı üretmesi yasaktır.
- API anahtarı yoksa veya bağlantı koparsa **şablon tabanlı metin** devreye girer. Demo asla LLM'e bağımlı kalmaz.

---

## 5. Veri kaynakları ve erişim durumu

12 Kasım'da yalnızca erişilebilirlik testi yapıldı, proje kodu yazılmadı.

| Veri | Ne için | Erişim | Test |
|---|---|---|---|
| **NASA POWER** (günlük, AG topluluğu) | İklim, ET₀ girdileri, GWETROOT | REST, **kimlik doğrulama yok** | ✅ Çalışıyor (Konya noktası, ~0,7 sn) |
| **MODIS MOD13Q1 NDVI** (ORNL DAAC web servisi) | Tarla Hafızası | REST, **kimlik doğrulama yok** | ✅ Çalışıyor |
| **SoilGrids v2** (ISRIC REST) | Toprak özellikleri | REST, kimlik doğrulama yok | ⚠️ **503 hatası verdi.** Yedek gerekli: demo bölgesi önbelleği ve WCS veya GEE alternatifi |
| **SMAP L4** kök bölgesi nemi | Doğrulama | NASA Earthdata (AppEEARS veya GES DISC), giriş gerekli | Event'te |
| **SRTM** (30 m) | Eğim, LS faktörü | Earthdata, OpenTopography veya GEE | Event'te |
| **GRACE/GRACE-FO** (JPL mascon) | Su depolama trendi | PO.DAAC veya GEE | Event'te |
| **GPM IMERG** | Yağış yoğunluğu, R faktörü | GES DISC (Earthdata) | Tier 2 |
| **ECOSTRESS** (70 m ET ve LST) | Tarla ölçeğinde ısı ve ET | AppEEARS | Tier 3 |
| FAO-56 Kc tabloları, FAO ECOCROP | Ürün bilgi tabanı | Açık yayın | — |

**Önemli:** Earthdata hesabı açmak araç hazırlığıdır, proje çalışması değildir. Event'ten önce açılabilir.

---

## 6. Mimari ve teknoloji

```
[Tarayıcı: React + Vite + TypeScript + MapLibre GL + ECharts + Tailwind]
          │  REST/JSON
[Backend: Python 3.11 + FastAPI]
   ├─ connectors/   POWER, MODIS-ORNL, SoilGrids, SMAP, SRTM, GRACE (+ disk önbelleği)
   ├─ engine/       climate.py, phenology.py, soil.py, waterbalance.py (FAO-56),
   │                rotations.py (aday üretimi + Pareto), scoring.py, erosion.py
   ├─ knowledge/    crops.yaml (kaynak alanlarıyla)
   ├─ narrative/    Claude API ile anlatım + şablon yedeği
   └─ demo_cache/   Konya + 2 başka demo tarlası için önceden çekilmiş veriler
```
- **Tek container** kullanılacak: FastAPI derlenmiş frontend'i de sunar. Hugging Face Spaces (Docker) veya Render'a deploy edilir.
- **Demo güvenliği:** Demo tarlaları önbellekten anında açılır. Canlı API yalnızca yeni noktalar için kullanılır.
- **Neden Streamlit değil?** Rakiplerin çoğu Streamlit kullanacak ve görsel olarak hepsi aynı görünecek. Presentation puanı için özel bir arayüz kuruyoruz. Agent ekibiyle bu süre içinde yapılabilir.
- **Testler:** pytest ile motor birim testleri (FAO-56 örnek hesaplarıyla ET₀, su dengesi kütle korunumu, fenoloji). Frontend'de uçtan uca bir demo akışı testi.

---

## 7. Kapsam: neyi kesin yapıyoruz, neyi sonra?

**Tier 1, Zorunlu (24. saatte uçtan uca çalışmalı):**
POWER + MODIS + toprak (önbellekli) → iklim profili → Tarla Hafızası → ürün bilgi tabanı (≥15 ürün) → FAO-56 su dengesi → mevcut rotasyon + 3 arketip → skorlama → Kanıt Kartları (şablon metin) → harita ve karşılaştırma arayüzü.

**Tier 2, Fark yaratanlar:**
İklim kayması kartı, senaryo kaydırıcıları, SMAP doğrulama grafiği, SRTM ve RUSLE erozyon, GRACE paneli, LLM anlatımı (TR/EN), yazdırılabilir rapor.

**Tier 3, Zaman kalırsa:**
ECOSTRESS, Landsat/HLS 30 m, IMERG ile R faktörü, poligon çizimi, ek diller.

> **Kural:** Tier 1 uçtan uca çalışmadan Tier 2'ye geçilmez.

---

## 8. Ekip ve agent organizasyonu

**Orkestratör (Opus 5.5, ana oturum):** Arayüz sözleşmeleri (JSON şemaları), iş dağıtımı, kod incelemesi, bilimsel doğrulama, testler, entegrasyon kararları.

| İş paketi | Agent | İçerik |
|---|---|---|
| WP1 Veri bağlayıcıları | `coder` (Sonnet) | POWER, MODIS, SoilGrids istemcileri, önbellek, yedek mekanizması |
| WP2 Ürün bilgi tabanı | `coder` + `explorer` | crops.yaml, her değer için kaynak |
| WP3 Motor | `coder` (Sonnet) ×2 | İklim ve fenoloji / su dengesi, rotasyon ve skorlama |
| WP4 Frontend | `coder` (Sonnet) | Harita, Tarla Hafızası şeridi, karşılaştırma ve Kanıt Kartları |
| WP5 Anlatım katmanı | `coder` | Olgu JSON'u, LLM istemi, şablon yedeği |
| WP6 Doküman ve atıf | `editor` (Haiku) | SOURCES.md, README, SI açıklaması |
| Arama ve kontrol | `explorer` (Haiku) | Kod tabanında arama, tutarlılık kontrolleri |

**İnsan takım üyeleri** (takım kurulunca doldurulacak): sunum ve video, çiftçi perspektifi ve alan bilgisi, demo hikâyesi, UI testleri.

İş paketleri arasındaki sınırlar **sözleşmelerle** çizilir (`docs/CONTRACTS.md`: API uç noktaları ve veri şemaları). Böylece agent'lar paralel çalışırken birbirinin dosyasına dokunmaz.

---

## 9. Zaman çizelgesi (48 saatlik varsayım, yerel event saatine göre düzeltilecek)

| Saat | Hedef | Kontrol noktası |
|---|---|---|
| 0–2 | Repo, lisans, iskelet, sözleşmeler, SOURCES.md | Sözleşmeler onaylandı |
| 2–10 | WP1–WP4 paralel | POWER→ET₀ testi geçiyor, NDVI şeridi çiziliyor |
| 10–18 | Su dengesi, rotasyon üretimi, skorlama | Konya için 4 strateji sayısal çıktı veriyor |
| 18–24 | Entegrasyon, Kanıt Kartları, deploy #1 | **Tier 1 uçtan uca canlı** |
| 24–32 | Tier 2: iklim kayması, kaydırıcılar, SMAP doğrulama, erozyon | Doğrulama grafiği hazır |
| 32–38 | LLM anlatımı, TR/EN, rapor, UX cilası | Çiftçi gözüyle test |
| 38–44 | Video, slaytlar, gönderi metni, README, SI açıklaması | Taslak gönderi hazır |
| 44–48 | Tampon, son deploy, **gönderi** | Gönderildi (son dakikayı beklemeden) |

İnsanların uyku vardiyaları planlanacak. Agent'lar gece boyunca iyi tanımlanmış görevlerde çalışabilir.

---

## 10. Sunum ve demo stratejisi (Presentation + Influence)

- **Açılış (ilk 10 saniye):** Konya'daki obruk fotoğrafı (açık lisanslı) ve GRACE grafiği. "Konya Ovası'nın yeraltı suyu her yıl X cm düşüyor. Çiftçi bir sonraki ekim kararını neye bakarak veriyor?"
- **Problem → Tarla Hafızası → karşılaştırma → Kanıt Kartı → senaryo kaydırıcısı → etki rakamı** ("Toprak Kurucu stratejisi, mevcut rotasyona göre medyan X m³/ha/yıl daha az su kullanıyor ve toprağı yılda Y gün daha uzun örtülü tutuyor").
- **Küresel ölçek:** "Konya'yı seçtik ama araç dünyanın her noktasında çalışıyor." Canlı olarak başka bir kıtada bir nokta seçilerek gösterilir (ör. ABD Kansas, Hindistan Pencap).
- **Dürüstlük slaytı:** Neyi bilmiyoruz, nerede yerel uzman gerekiyor. Validity puanını artırır.
- **SI kullanımı:** "SI sayıları uydurmuyor, NASA verisinden hesaplanan sayıları anlatıyor" ve geliştirmede agent ekibi kullanıldı.
- Gönderi formatı (video süresi, slayt sayısı) 13 Kasım'da yayınlanacak rehbere göre kesinleşecek.

---

## 11. Riskler ve önlemler

| Risk | Olasılık | Önlem |
|---|---|---|
| SoilGrids veya başka bir API event sırasında çöker | **Yüksek** (bugün 503 verdi) | Demo bölgeleri önbellekte, varsayılan toprak sınıfı yedeği, arayüzde "veri eksik" etiketi |
| Kapsam büyür, hiçbir şey bitmez | Yüksek | Tier kuralı, 24. saat kontrol noktası |
| 250 m MODIS pikseli küçük tarlada karışık sinyal verir | Orta | Dürüstçe belirtilir. Tier 3'te HLS 30 m |
| Ürün parametreleri yanlış olur | Orta | Her değerin kaynağı yazılı, FAO-56 tablolarına bağlı kalınır |
| LLM halüsinasyonu | Orta | Sadece olgu JSON'u kullanılır, ID atfı zorunlu, şablon yedeği var |
| Erken çalışma kuralı ihlali algısı | Düşük–Orta | Event'ten önce kod yok. Repo commit geçmişi 14 Kasım'da başlar |
| Earthdata girişleri gecikir | Düşük | Hesaplar önceden açılır |

---

## 12. Açık sorular ve 13 Kasım yapılacaklar

**Karar:** Takım yapısı, imkânlar ve dış etkenler planı sınırlamıyor. Hedef, ortaya çıkabilecek en iyi ürün. Gerekli API anahtarları (Claude, Earthdata) ve deploy hesabı ihtiyaç anında eklenecek. Bunlar olmadan da çalışan yedekler (şablon metin, önbellek) zaten planda var.

**13 Kasım (kaynaklar yayınlanınca):**
- [ ] Challenge Resources sekmesini oku. Önerilen veri setleri ve araçlar bu planla uyumlu mu?
- [ ] Judging & Awards Guide: kriterleri ve ağırlıkları §1'e işle
- [ ] Project Submission Guide: video ve slayt formatını §10'a işle
- [ ] SoilGrids'i tekrar test et, yedek kararını kesinleştir
