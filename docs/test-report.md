# Test raporu (Faz 1–2)

`cd backend && python -m pytest -q` → **19 geçti** (birim: sütun sınıflandırma, temizleme; entegrasyon: xlsx/csv içe aktarma,
tekrar/çakışma, bozuk dosya, elle eşleşme, API önizleme/aktarma/hata mesajları/API anahtarı).

Gerçek arşiv doğrulaması (elle çalıştırıldı, otomatik teste dahil değil):
- 10 dosya içe aktarıldı (~85 sn): 69.920 satır → 69.920 maç, 0 red; pandas ile bağımsız sayım aynı (69.920; skorsuz 2).
- 5.047.197 oran gözlemi, 62 pazar×bahisçi×tür kaynağı; veritabanı ~375 MB (SQLite).
- Çalışan API üzerinden `/api/data/summary` ve `/api/matches` yanıtları doğrulandı.

**Test edilmeyenler / sınırlar:** PostgreSQL'e karşı çalıştırılmadı (yalnızca SQLite); büyük CSV'ler gerçek dosyayla denenmedi;
alembic migrasyonu SQLite'ta doğrulandı; arayüz yok; yedek geri yükleme fonksiyonu otomatik testte değil; yükleme sırasında
aktarım senkron çalışır (arka plan görevi/ilerleme çubuğu sonraki aşama).
