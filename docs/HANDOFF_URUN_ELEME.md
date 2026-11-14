# Devir: Bölgelere ürün eleme ve entegrasyon (2026-11-14)

Yeni oturum için başlangıç noktası. Önce bunu, sonra `docs/STATUS.md`'yi oku.

## Durum
- Dal: `feature/konya-zones` (GitHub'a gönderildi, commit `1ffd36a`). `main`'e birleştirme ve PR **yok**, kullanıcı istemiyor.
  `feature/modes` dalına dokunulmayacak.
- Konya 7 zirai-mikroklima bölgesine ayrıldı ve uygulamada çalışıyor (METHODS §10, CONTRACTS §6).
- Ürün araştırması bitti, **commit edilmedi**:
  - Rapor: `reports/Konya bölgeleri ürün araştırması.md` (7 bölge × Liste A geleneksel / Liste B yenilikçi / elenenler,
    31 ürün × 7 bölge matrisi U/Ş/X/?, veri kalitesi ve çelişkiler bölümü)
  - Notlar: `research_notes/Konya bölgeleri ürün araştırması/` (bolge1..7, genel_yuksek_deger_urunler.md)
  - Başka bir yapay zekanın araştırması: `research_notes/.../diger_yz_1.md` (doğrulanmamış). Kullanıcı başka araştırmalar da getirebilir.

## Kullanıcının kararı: tahmine yer yok
Uygulamaya yalnızca resmî/birincil kaynakla desteklenen ürünler girer:

| Kademe | Ölçüt | Uygulamada |
|---|---|---|
| ✅ Kanıtlı | Resmî kaynakta o ilçede üretim (TÜİK, İl Tarım, TÜRKPATENT coğrafi işaret, bakanlık belgesi) | Bölge önerisi |
| 🧪 Pilot | Konya'da belgelenmiş resmî deneme/proje (birincil kaynak) | "Deneme aşamasında" etiketi, öneri değil |
| ❌ Kanıtsız | Sadece agronomik çıkarım / başka bölge benzetmesi | Girmez |

Su ihtiyacı ve don uygunluğu tahminle doldurulmaz: su = FAO-56 Kc × bölge iklimi (projenin motoru, "model hesabı" etiketi);
don = FAO ECOCROP sıcaklık eşikleri × bölge don günü verisi (`data/zones/konya_zones.geojson` istasyon profilleri).
Raporlardaki "ÇK" (çıkarım) değerleri uygulamaya girmez.

## Sıradaki adımlar
1. (Kullanıcı varsa) diğer yapay zeka araştırmalarını al, `research_notes/.../diger_yz_N.md` olarak kaydet.
2. **Doğrulama**, kaynak bazında gruplayarak (agent sayısını az tut, kullanıcı token'a hassas; tahmini 80–120k token):
   - Konya İl Tarım "çevre dostu tarımsal ürün" PDF'i: https://konya.tarimorman.gov.tr/Belgeler/cevredostutarimsalurun.pdf
     (diger_yz_1'in ana dayanağı: ilçe bazlı adaçayı, kekik, nane, karabuğday, çemen, kişniş, kantaron, aronya)
   - Lavanta distilasyon tesisi: Güneysınır mı (bizim rapor) Hüyük mü (diger_yz_1)?
   - Sorgum projesi (Ereğli/Karapınar) ve "%60 daha az su" iddiası
   - TÜRKPATENT coğrafi işaretler (Hüyük Çileği 722, Akşehir Kirazı 75, Ereğli Beyaz Kirazı 406, Seydişehir Karpuzu 1700, Akçabelen Şeker Fasulyesi 447 vb.)
   - Havza bazlı destekleme modeli katsayıları ve su kısıtlı 19 ilçe listesi (resmî tebliğ)
   - Pilot haberleri (Antep fıstığı Hadim/Taşkent/Bozkır, kenevir Çumra/Kulu, ketencik Kulu, agrivoltaik) → birincil kaynağa kadar
   - Ulaşılamayan: `konyatarimistilce2025.pdf` (404). Daha yeni ilçe verisi için TÜİK biruni tekrar denenebilir.
3. Çıktı: tek **eleme tablosu** (ürün × bölge, kademe, birincil kaynak linki, doğrulandı/doğrulanamadı) →
   `data/zones/zone_crops.json` gibi bir veri dosyası + METHODS/SOURCES güncellemesi.
4. Uygulamaya entegrasyon: ZoneCard'da "bu bölgede geleneksel / önerilen / pilot ürünler"; çok yıllık ve tıbbi-aromatik ürünler
   için ayrı "özel ürünler" modülü gerekebilir (motor tek sezonluk; STATUS bilinen sorun 1).
5. Daha sonra (planlandı, başlanmadı): Basin View yerine "Bölge etkisi" sekmesi (su / ekonomi / sanayi-değer zinciri / sosyal kartlar;
   TÜİK ilçe verisi + girdi-çıktı çarpanları; GRACE su kartında bağlam olarak kalır).

## Commit edilmemiş diğer dosyalar
- `.claude/launch.json` (modes deneme girişi) ve `docs/HANDOFF_MODES.md`: bu işin parçası değil, commit'e katma.
- Ayrı klasörde modes deneme worktree'si: `C:\Veri Merkezim\01-Projelerim\Rotacast-modes` (dal `try/modes`), istenirse kaldırılabilir.
