# Futbol Analiz, Tahmin ve Kupon Yazılımı

Durum: **Faz 1 + Faz 2 tamamlandı** (ortam/arşiv incelemesi, içe aktarma, temizleme, veritabanı).
Faz 3 (benzer oran arama) tamamlandı: `backend/app/analysis/`, `POST /api/similar`, ve telefonda çalışan tek dosyalı uygulama `mobile/`.
Poisson (piyasa) + arşiv güç modeli, bülten ayrıştırma, The Odds API bağlayıcısı ve tek maç otomatik analizi eklendi ([docs/live-data.md](docs/live-data.md)).
Henüz yapılmadı: tam walk-forward backtest raporu, otomatik kupon üretimi, API-Football/istatistik sağlayıcısı, Next.js arayüzü.

## Kurulum
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env            # gerekirse düzenleyin
python -m alembic upgrade head        # veritabanı şemasını oluşturur (varsayılan SQLite: data/football.sqlite)
```
PostgreSQL için `.env` içinde `DATABASE_URL=postgresql+psycopg://...` verin ve `pip install "psycopg[binary]"`.

## Arşivi içe aktarma
```bash
mkdir -p ../data/raw && cp /yol/*.xlsx ../data/raw/
python -m app.importer.cli ../data/raw/*.xlsx        # ~1,5 dk, 10 dosya
python -m app.importer.cli dosya.xlsx --map eslesme.json   # elle sütun eşleşmesi
python -m app.importer.cli dosya.xlsx --force              # aynı dosyayı yeniden aktar
```
Ayrıntı: [docs/import-guide.md](docs/import-guide.md). Veri sözlüğü: [docs/data-dictionary.md](docs/data-dictionary.md).

## API
```bash
cd backend && uvicorn app.api.main:app --reload --port 8000     # belgeler: http://localhost:8000/docs
```
`POST /api/imports/preview` (yazmadan önizleme), `POST /api/imports`, `GET /api/imports/{id}` (rapor),
`GET /api/imports/{id}/issues`, `GET /api/data/summary`, `GET /api/matches`, `GET /api/teams/alias-suggestions`,
`POST /api/teams/aliases`, `POST /api/admin/backup`. `API_KEY` doluysa yazma uçları `X-API-Key` ister.

## Testler
```bash
cd backend && python -m pytest -q      # 43 test
```
Sonuçlar ve sınırlamalar: [docs/test-report.md](docs/test-report.md).

## Yedekleme
`POST /api/admin/backup` veya `from app.services.backup import backup_database` (SQLite için tutarlı kopya, `data/backups/`).
Geri yükleme: API'yi durdurup `restore_database(yol)`. PostgreSQL için `pg_dump`/`pg_restore`.

## Güvenlik notları
Sırlar yalnızca `.env`'de (Git'e girmez, `.env.example` şablondur). Yükleme: uzantı beyaz listesi, boyut sınırı,
dosya adı temizleme, geçici klasör silme. Bahis hesabı/finansal işlem özelliği yoktur ve eklenmeyecektir.

## Mobil uygulama (mobile/)
Tek HTML dosyası, arşiv içine gömülü (1,3 MB), sunucu gerekmez; telefonda tarayıcıda açılır.
```bash
cd backend && PYTHONPATH=. python ../mobile/build.py      # mobile/dist/oran-arsivi.html üretir
# parite testi (JS motoru = Python motoru):
PYTHONPATH=. python ../mobile/make_parity_ref.py /tmp/parity && node ../mobile/test_parity.mjs /tmp/parity
```
Benzerlik yöntemi ve sınırları uygulamanın "Bilgi" sekmesinde ve `backend/app/analysis/similarity.py` başlığında.

## Tek dokunuşla bülten
`uvicorn app.api.main:app` çalışırken `http://localhost:8000/bookmarklet` → yer imini ekleyin → bülten sayfasında tıklayın → `http://localhost:8000/app` Bülten sekmesinde maçlar listelenir. Ayrıntı: docs/live-data.md.

## Haftalık bülten PDF'i
Bülten PDF'ini okuyup uygulamaya gömmek için: docs/live-data.md > "Haftalık bülten PDF'i". Parite testleri: `node mobile/test_bulletin_parity.mjs`.
