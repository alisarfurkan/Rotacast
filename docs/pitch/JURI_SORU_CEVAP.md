# Jüri soruları: kısa cevaplar

**Altın kural:** Bilmediğimiz bir şey sorulursa "Bunu henüz hesaplamıyoruz, sebebi şu" deyin. Uydurmayın.
Cevaplar kısa olsun: önce 1–2 cümle söyleyin, detayı ancak sorarlarsa verin.

---

## En çok dikkat edilecek 5 soru

**1. "Su bu kadar azalırken gelir nasıl artıyor?"**
> Su harcayan pancar ve mısırın yerine nohut, buğday ve az sulanan patates geliyor. Ama gösterdiğimiz gelir **brüt
> gelir**, yani tohum, gübre ve işçilik masrafları düşülmedi. Asıl söylediğimiz şu: su tasarrufu çiftçiye gelir
> kaybettirmiyor.

❌ "Çiftçi %55 daha fazla kazanır" demeyin.

**2. "Verim düşüyor, bitkiyi susuz mu bırakıyorsunuz?"**
> Evet, biraz. Bu bilinçli bir tercih: az suyla biraz daha düşük verim. Bu kaybı gelir hesabına zaten katıyoruz.
> Riskten kaçınan çiftçi için ayrıca "düşük risk" kartı var.

**3. "GRACE'teki kaybın %41'ini mi kurtarıyorsunuz? Emin misiniz?"**
> Bu kesin bir rakam değil, bir senaryo. Söylediğimiz şu: sulu tarlaların sadece %10'u değişse bile etkisi,
> kaybın kendisiyle aynı büyüklükte oluyor.

❌ "Konya'nın su sorununun %41'ini çözüyoruz" demeyin.

**4. "Modeli neyle doğruladınız?"**
> Sahada ölçümle doğrulama yapmadık, hackathon süresi yetmedi. Ama sonuçları resmî verilerle karşılaştırdık:
> havzanın toplam su ihtiyacı yayımlanmış rakamların aralığına düşüyor, ekim deseni TÜİK'e uyuyor ve uydu
> tarladaki gerçek ürün geçmişini doğru gösteriyor. Sonraki adımımız NASA SMAP toprak nemi verisiyle
> karşılaştırma yapmak.

**5. "Yapay zekâ kullandınız mı?"**
> Kod yazarken yapay zekâ asistanından yardım aldık ve bunu beyan ettik. Hangi verinin kullanılacağı, bölgeler, ürün
> listesi ve kurallar bizim kararımız. Uygulamanın gösterdiği hiçbir sayıyı yapay zekâ üretmiyor; hepsi simülasyondan geliyor.

---

## Veri soruları

**"Hangi NASA verilerini kullanıyorsunuz?"**
> Hava durumu için NASA POWER, tarlanın geçmişi için MODIS, su kaybı için GRACE, arazi yüksekliği için SRTM.
> Yağışı düzeltmek için ayrıca CHIRPS kullanıyoruz.

⚠️ CHIRPS bir NASA verisi değil. Slaytta görünen IMERG'i ise yalnızca yedek olarak kullanıyoruz, çünkü Konya'da hatalı
veriler verdi. Bu soru gelirse bunu açıkça söyleyin; hatayı fark etmiş olmamız lehimize olur.

**"NASA POWER 50 km'lik kareler halinde. Tek bir tarla için bu fazla kaba değil mi?"**
> Sıcaklık 50 km içinde pek değişmez. Asıl sorun yağıştaydı: NASA, Çumra'ya yılda 533 mm yağış düşüyor diyordu,
> gerçekte 302 mm. Bunu daha ince çözünürlüklü uydu yağışıyla düzelttik.

**"Uydu tek bir tarlayı ayırt edebiliyor mu?"**
> MODIS'in bir pikseli 250 metre, yani küçük tarlalarda birkaç tarla karışabilir. Bu yüzden uydu geçmişini sadece
> kanıt olarak gösteriyoruz, hesaba katmıyoruz. Bir sonraki adımda 30 metrelik Landsat/Sentinel verisine geçmek istiyoruz.

---

## Model soruları

**"Simülasyon nasıl çalışıyor?"**
> Birleşmiş Milletler'in (FAO) standart yöntemiyle toprağın içindeki suyu gün gün hesaplıyoruz. Çumra'da 179 farklı ürün
> sırasını, son 25 yılın gerçek havasıyla deniyoruz. Böylece kötü, normal ve iyi bir yılda ne olacağını görüyoruz.

**"Geleceği mi tahmin ediyorsunuz?"**
> Hayır. Geçmişte yaşanmış havayla deneme yapıyoruz, üstüne de son yıllardaki ısınma eğilimini ekliyoruz.

**"İklim modeli kullanıyor musunuz?"**
> Hayır, bilerek kullanmadık. Tek bir tarla ölçeğinde gerçekte ölçülmüş eğilim daha güvenilir.

**"Kartların kuralları neler?"**
> Kuralımız iki tane: hiçbir kart bugünkünden fazla su ve fazla erozyon önermez; yalnızca o bölgede yetiştiği resmî
> kaynakla belgelenmiş ürünler önerilir. Çiftçi öncelik verdiği şeyleri değiştirebilir ama bu iki kuralı esnetemez.

**"Yonca neden yok?"**
> Yonca çok yıllık bir bitki, modelimiz ise ürünleri sezon sezon hesaplıyor. Ayrıca yonca çok su istediği için
> zaten dikkatli olunması gereken ürünler arasında.

---

## Bölge ve ürün soruları

**"Bölgeleri nasıl belirlediniz?"**
> Meteoroloji'nin 12 istasyonunun iklim sınıflamasına, yüksekliğe (Toroslar) ve Beyşehir Gölü'ne uzaklığa bakarak
> Konya'yı 7 bölgeye ayırdık. Bölgeleri bilgisayara otomatik buldurmayı da denedik ama çok yavaştı ve daha iyi bir
> sonuç vermedi.

**"Ürünlerin o bölgede yetiştiğini nereden biliyorsunuz?"**
> Her ürünü TÜİK, kalkınma ajansı raporları, coğrafi işaret kayıtları ve İl Tarım'ın yayınları gibi resmî kaynaklardan
> tek tek kontrol ettik. Kanıt bulamadığımız ürünleri (kivi, kinoa gibi) hiç göstermiyoruz.

**"Kimyonun geliri neden yazmıyor?"**
> Güvenilir bir çiftçi satış fiyatı bulamadık, bu yüzden uydurmak yerine "hesaplanmadı" yazdık. Su ihtiyacını ise
> bilimsel makalelerdeki değerlerle hesaplıyoruz.

---

## Kullanım soruları

**"Bunu kim kullanacak?"**
> Çiftçi ve ziraat mühendisi birlikte. Araç karar vermiyor, kararı veriyle destekliyor.

**"Konya dışında çalışır mı?"**
> Kullandığımız veriler bütün dünyayı kapsıyor. Başka bir bölgeye taşımak için o bölgenin ürün listesini ve
> bölgelerini hazırlamak yeterli. Her rakamın arkasında durabilmek için şimdilik Konya'ya odaklandık.

**"Yeni bir tarlaya tıklayınca neden yavaş açılıyor?"**
> İlk seferde 25 yıllık veri indiriliyor, sonrasında kayıtlı veriden hızlıca açılıyor. Örnek tarlalar internetsiz de çalışıyor.

**"Açık kaynak mı?"**
> Evet, GitHub'da herkese açık. Projeyi indiren herkes örnek tarlaları internetsiz de çalıştırabilir.

---

## Ezberlenecek sayılar

| Konu | Sayı |
|---|---|
| GRACE'e göre Konya'nın su kaybı | Yılda ~534 milyon m³ (yılda 1,22 cm) |
| Sulu tarlaların %10'u değişirse | Yılda ~220 milyon m³ tasarruf, kaybın ~%40'ı |
| Çumra'da şu anki su kullanımı | 4.829 m³/ha |
| Dengeli kartla su kullanımı | 1.340 m³/ha |
| Yağış düzeltmesi (Çumra) | 533 mm → 302 mm |
| Simülasyon sayısı | 179 ürün sırası × 25 yıl = 4.475 |
| Kapsam | 7 bölge, 21 ürün, 12 meteoroloji istasyonu |

---

## ⚠️ Commit tarihleri

İlk commit'ler 12–13 Kasım tarihli, yani etkinlik başlamadan önce atılmış. Repo artık herkese açık olduğu için bunu
görebilirler. Saklamaya ya da tarihleri değiştirmeye çalışmayın. Sorulursa ne olduysa olduğu gibi anlatın.
