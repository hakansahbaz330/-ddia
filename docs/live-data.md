# Canlı fikstür/oran ve otomatik maç analizi

## Kaynaklar hakkında net bilgi
- **Bet365, Nesine, SofaScore:** Bunların herkese açık resmi API'sini bulamadım ve kullanım koşulları otomatik veri çekmeyi kısıtlayabilir.
  Bu nedenle bu sitelerden kazıma (scraping) bağlayıcısı **yazılmadı**. Bu bahisçilerin oranları, lisanslı sağlayıcının döndürdüğü kadarıyla
  gelir (hangi bahisçinin hangi bölgede/planda olduğu hesabınıza bağlıdır; doğrulanmadı) veya bülten **elle yapıştırılır**.
- **The Odds API (v4):** Bağlayıcı yazıldı (`app/providers/odds_api.py`). Yapı resmi dokümandan (h2h/totals, `apiKey`, kota kredisi) alındı;
  **anahtar olmadığı için canlı çağrı denenmedi**, ayrıştırma ve hata yönetimi sahte yanıtlarla test edildi. Spor anahtarı eşlemesi
  (`app/services/teams.py: SPORT_TO_DIVISION`) bellekten yazıldı, doğrulanmadı; gerçek liste `GET /v4/sports` ile gelir.
- **API-Football (istatistik/oran):** Dokümanına erişilemedi (403), doğrulanmadığı için bağlayıcı yazılmadı. Takım istatistikleri şimdilik kendi
  arşivinizden (şut, korner, kart, form, karşılıklı geçmiş) hesaplanır.

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
