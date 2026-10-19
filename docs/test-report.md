# Test raporu (Faz 1–2)

`cd backend && python -m pytest -q` → **37 geçti (piyasa-Poisson, bülten ayrıştırıcı, The Odds API ayrıştırma/hata yönetimi dahil)** (birim: sütun sınıflandırma, temizleme; entegrasyon: xlsx/csv içe aktarma,
tekrar/çakışma, bozuk dosya, elle eşleşme, API önizleme/aktarma/hata mesajları/API anahtarı).

Gerçek arşiv doğrulaması (elle çalıştırıldı, otomatik teste dahil değil):
- 10 dosya içe aktarıldı (~85 sn): 69.920 satır → 69.920 maç, 0 red; pandas ile bağımsız sayım aynı (69.920; skorsuz 2).
- 5.047.197 oran gözlemi, 62 pazar×bahisçi×tür kaynağı; veritabanı ~375 MB (SQLite).
- Türetilen pazarlar (2,5 üst, KG var, İY 1,5 üst, korner 9,5 üst; 2023-24) ham xlsx'ten pandas ile bağımsız hesaplananla birebir aynı çıktı.
- Çalışan API üzerinden `/api/data/summary` ve `/api/matches` yanıtları doğrulandı.

**Test edilmeyenler / sınırlar:** PostgreSQL'e karşı çalıştırılmadı (yalnızca SQLite); büyük CSV'ler gerçek dosyayla denenmedi;
alembic migrasyonu SQLite'ta doğrulandı; arayüz yok; yedek geri yükleme fonksiyonu otomatik testte değil; yükleme sırasında
aktarım senkron çalışır (arka plan görevi/ilerleme çubuğu sonraki aşama).


Mobil: `node mobile/test_parity.mjs` JS motoru ile Python motorunun benzer-maç sıralaması, yüzdeleri ve piyasa-Poisson sonucunu karşılaştırır (hepsi OK). Canlı The Odds API çağrısı ve gerçek telefon denenmedi.

Bülten listesi: her maçın model % (bülten oranlarından, kuponda kullanılan) ve arşiv % (oranları en benzer 50 maç) değerleri, maç detayındaki sayılarla aynı fonksiyonlardan gelir (tarayıcıda karşılaştırıldı: ör. MS1 %59/%72 liste = detay %58,6/özet %72). Arşiv yöntemi 400 rastgele geçmiş maçla (yalnız öncesi maçlar) sınandı: ortalama sapma ev +0,48, beraberlik −0,01, deplasman −0,47 puan.

Düzen denetimi: `python mobile/check_layout.py mobile/dist/oran-arsivi.html` iPhone çentik payını (safe-area) emüle eder. Bir sınıf adı çakışması (`.top`) yüzünden telefonda "model favorisi" kutuları aşağı kayıp kartın `overflow: hidden` kuralıyla kesiliyordu (350 kutudan 150'si); masaüstü/headless tarayıcıda çentik payı 0 olduğu için görünmüyordu. Düzeltmeden sonra 0/350.
