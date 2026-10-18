# Canlı fikstür/oran ve otomatik maç analizi

## Yalnızca arşivdeki ligler
Bültenden yalnızca arşivdeki liglere ait maçlar uygulamaya alınır (`app/providers/iddaa_leagues.py`: bülten kodu -> arşiv lig kodu). Diğerleri sayılarıyla raporlanır
(`excluded_leagues`). Eşleme, her kodun takımlarının arşivdeki lige ait **güncel sezon** takımlarıyla eşleşme oranına bakılarak doğrulanır:
`node mobile/check_leagues.mjs <veri.bin.gz> mobile/weekly.json` (şüpheli kod <%70). Örnek: `İFAK` FA Kupası çıktı (alt lig takımları) ve alınmadı.
Bülten kodu yeni bir lige aitse ve arşivde varsa `IDDAA_TO_ARCHIVE` tablosuna ekleyin. Belçika (B1) ve Portekiz (P1) bu bültende görülmedi.
**Arşiv güncelliği:** Arşiv 17 Eylül 2026'da bitiyorsa, sonrasındaki maçlar (form, puan durumu) yoktur. Güncel Football-Data dosyasını içe aktarıp
`mobile/build.py` ile yeniden derleyin (README > Arşivi içe aktarma).

## Haftalık bülten PDF'i (güncel yöntem)
Resmi iddaa/Nesine haftalık bülten PDF'i (metin katmanlı) `backend/app/providers/iddaa_pdf.py` ile okunur: sütunlar başlık satırının x-konumlarına göre
eşlenir, her maç dikey olarak en yakın satıra atanır. Yalnızca futbol alınır; 1X2'nin tamamı olmayan maçlar (bir seçenek "-" ise) atlanır.
Doğrulama: örnek bültende 861 maç okundu ve her pazarın marjı aynı dar bantta çıktı (1X2/KG/ÜA/İY ≈ %17,5; toplam gol ≈ %20,8; İY/MS ≈ %25,7),
sütun kayması olsaydı bu tutmazdı (`tests/test_bulletin_model.py`).
```bash
cd backend
PYTHONPATH=. python -m app.providers.iddaa_pdf bulten.pdf --year 2026 --out ../mobile/weekly.json
PYTHONPATH=. python ../mobile/build.py     # uygulamayı bülten gömülü yeniden üretir
```
Model (`app/models/bulletin_model.py`, JS ikizi `mobile/engine.js`): 1X2, 2,5/3,5 ü/a, KG ve toplam gol aralıkları tek (λ ev, λ dep) çiftine uydurulur
(uyum hatası tipik olarak <1 puan); ilk yarı oranlarından ayrı İY modeli; İY/MS ortak dağılımı. Bülten oranları tek bir Poisson ile tutarlı çıktığı için pazarlar arası
belirgin tutarsızlık yoktur; model aynı bahisçinin oranlarından türediğinden EV ≈ −marj'dır, avantaj kanıtı değildir.

## Kaynaklar hakkında net bilgi
- **Bet365, Nesine, SofaScore:** Bunların herkese açık resmi API'sini bulamadım ve kullanım koşulları otomatik veri çekmeyi kısıtlayabilir.
  Bu nedenle bu sitelerden kazıma (scraping) bağlayıcısı **yazılmadı**. Bu bahisçilerin oranları, lisanslı sağlayıcının döndürdüğü kadarıyla
  gelir (hangi bahisçinin hangi bölgede/planda olduğu hesabınıza bağlıdır; doğrulanmadı) veya bülten **elle yapıştırılır**.
- **The Odds API (v4):** Bağlayıcı yazıldı (`app/providers/odds_api.py`). Yapı resmi dokümandan (h2h/totals, `apiKey`, kota kredisi) alındı;
  **anahtar olmadığı için canlı çağrı denenmedi**, ayrıştırma ve hata yönetimi sahte yanıtlarla test edildi. Spor anahtarı eşlemesi
  (`app/services/teams.py: SPORT_TO_DIVISION`) bellekten yazıldı, doğrulanmadı; gerçek liste `GET /v4/sports` ile gelir.
- **API-Football (istatistik/oran):** Dokümanına erişilemedi (403), doğrulanmadığı için bağlayıcı yazılmadı. Takım istatistikleri şimdilik kendi
  arşivinizden (şut, korner, kart, form, karşılıklı geçmiş) hesaplanır.

## Bülteni içeri almanın yolları
> Not: Mobil uygulamadan yapıştırma, dosyadan yükleme ve telefon yer imi bölümleri kaldırıldı; uygulama yalnızca haftalık bülten PDF'inden gömülen bülteni gösterir (aşağıdaki "Haftalık bülten PDF'i"). Aşağıdaki diğer yöntemler yalnızca arka uç/tarihçe içindir.
1. Metni yapıştır (tek satır, sekmeli veya takımlar/oranlar alt alta çok satırlı düzen).
2. Bülten sayfasını tarayıcıdan "Farklı kaydet" ile .html kaydedip uygulamaya yükle (etiketler soyulur, site'ye özgü seçici yoktur, tarayıcıda okunur).
3. .txt/.csv dosyası.
4. Lisanslı API (The Odds API) ile otomatik çekme (aşağıda).
0. **Yalnızca telefon (sunucusuz):** Uygulamadaki Bülten sekmesi > "Telefonda tek dokunuş kurulumu": yer imi kodu telefon tarayıcısında bülten sayfasında çalışır, metni panoya kopyalar; uygulamaya yapıştırınca otomatik ayrıştırılır. Telefonda denenmedi.
5. **Tek dokunuş (yer imi + gelen kutusu, bilgisayar gerekir):** Sunucuyu çalıştırın, `http://localhost:8000/bookmarklet` sayfasındaki bağlantıyı yer imlerine sürükleyin.
   Kendi tarayıcınızda Nesine/bahisçi bülteni açıkken yer imine tıklayın: sayfada görünen metin sunucuya gönderilir (ve panoya kopyalanır);
   `http://localhost:8000/app` açıkken Bülten sekmesi maçları kendiliğinden listeler. Liste sayfada yüklenmeden (kaydırma gerekebilir) görünmez.
   Yer imi yalnızca sizin açtığınız sayfanın metnini okur; siteye ayrı istek göndermez. Sitelere sunucu tarafından bağlanan kazıyıcı ve bot koruması aşma kodu yazılmadı.

## Kurulum
`.env` içine `ODDS_API_KEY=...` (ve isteğe bağlı `ODDS_API_REGIONS=eu`). Sunucuyu çalıştırın: `uvicorn app.api.main:app`.
- `GET /api/live/status` anahtar/kota durumu · `POST /api/live/refresh {"sport_keys":["soccer_epl"]}` oranları çekip saklar (zaman damgalı, tekrar yazılmaz)
- `GET /api/live/fixtures` yaklaşan maçlar + bahisçi başına 1X2 (eksik oran işaretlenir) · `POST /api/bulletin/parse {"text": "..."}` bülten ayrıştırır
- `POST /api/match/analyze` tek maç analizi (skor dağılımı, pazarlar, güç modeli, benzer maçlar, form, karşılıklı geçmiş, EV)
Anahtar yokken sunucu çalışır; refresh 503 ve açıklayıcı mesaj döner.

## Model değerlendirmesi (scripts/evaluate_models.py, scripts/model_report.json)
Eğitim ≤2023-24, doğrulama 2024-25 (birleşim ağırlığı burada seçildi), bağımsız test 2025-26; güç modeli sezon başına tarihe kadar eğitildi.
Test 1X2 log-kayıp: kapanış-piyasa Poisson **0,989** · arşiv güç modeli 1,020 · eşit olasılık 1,071. Ağırlık araması piyasaya 1,0 verdi:
**güç modeli kapanış oranının üstüne bilgi katmıyor**. Bu yüzden birleşik tahmin piyasaya eşittir; güç modeli ayrışma uyarısı için gösterilir.
Değerlendirme maç öncesi *kapanış* oranlarıyla yapıldı; güncel bültendeki oranlar kapanıştan önce olabilir. Sezon başına 3.000 maçlık örnek kullanıldı.
Skor dağılımı: 0-0 ve 1-1 sıklığı modelle uyumlu (%7,4 / %11,3); 2,5 üst ve KG sıklığı 2024-25'te piyasa-Poisson'dan ~4 puan yüksekti (tek sezon).
