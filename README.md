# Futbol Analiz, Tahmin ve Kupon Yazılımı

Durum: **Faz 1 + Faz 2 tamamlandı** (ortam/arşiv incelemesi, içe aktarma, temizleme, veritabanı).
Faz 3–9 (benzer oran arama, modeller, geriye dönük test, API entegrasyonu, kupon, arayüz) **henüz yapılmadı**.
Arayüz (Next.js) bu sürümde yok; yalnızca FastAPI uç noktaları ve komut satırı var.

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
cd backend && python -m pytest -q      # 23 test
```
Sonuçlar ve sınırlamalar: [docs/test-report.md](docs/test-report.md).

## Yedekleme
`POST /api/admin/backup` veya `from app.services.backup import backup_database` (SQLite için tutarlı kopya, `data/backups/`).
Geri yükleme: API'yi durdurup `restore_database(yol)`. PostgreSQL için `pg_dump`/`pg_restore`.

## Güvenlik notları
Sırlar yalnızca `.env`'de (Git'e girmez, `.env.example` şablondur). Yükleme: uzantı beyaz listesi, boyut sınırı,
dosya adı temizleme, geçici klasör silme. Bahis hesabı/finansal işlem özelliği yoktur ve eklenmeyecektir.
