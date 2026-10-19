"""FastAPI uygulaması: arşiv içe aktarma ve veri merkezi uç noktaları."""
from __future__ import annotations

import json
import secrets
import shutil
import tempfile
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field, model_validator
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.importer.columns import build_mapping, mapping_summary
from app.importer.engine import import_file
from app.importer.readers import UnsupportedFile, iter_sheets
from app.analysis.similarity import Query as SimQuery, Scope, analyze
from app.schema import DataQualityLog, ImportRun
from app.services import dataset
from app.services.backup import BackupUnsupported, backup_database

app = FastAPI(title="Futbol Analiz API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"], allow_headers=["*"])

ALLOWED_SUFFIXES = {".xlsx", ".xlsm", ".csv"}


def require_key(x_api_key: str | None = Header(default=None)) -> None:
    """API_KEY tanımlıysa değiştirici uç noktalar için zorunlu."""
    key = get_settings().api_key
    if key and not secrets.compare_digest(x_api_key or "", key):
        raise HTTPException(401, "Geçersiz veya eksik API anahtarı (X-API-Key).")


def _save_upload(file: UploadFile) -> Path:
    name = Path(file.filename or "yukleme").name  # yol kaçışını engelle
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(400, f"Desteklenmeyen dosya türü '{suffix}'. xlsx veya csv yükleyin.")
    cfg = get_settings()
    cfg.upload_dir.mkdir(parents=True, exist_ok=True)
    tmpdir = Path(tempfile.mkdtemp(dir=cfg.upload_dir))
    dest = tmpdir / name
    limit = cfg.max_upload_mb * 1024 * 1024
    size = 0
    with dest.open("wb") as f:
        while block := file.file.read(1 << 20):
            size += len(block)
            if size > limit:
                shutil.rmtree(tmpdir, ignore_errors=True)
                raise HTTPException(413, f"Dosya {cfg.max_upload_mb} MB sınırını aşıyor.")
            f.write(block)
    return dest


def _parse_mapping(raw: str | None) -> dict[str, str] | None:
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in obj.items()):
            raise ValueError
        return obj
    except ValueError:
        raise HTTPException(400, 'mapping geçerli bir JSON nesnesi olmalı: {"Sütun": "odds:B365:1X2:H:pre"}') from None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/imports/preview", dependencies=[Depends(require_key)])
def preview_import(file: UploadFile = File(...), mapping: str | None = Form(None)):
    """Veritabanına yazmadan sayfaları, sütunları ve otomatik eşleşmeyi gösterir."""
    path = _save_upload(file)
    try:
        sheets = []
        for sheet, header, rows in iter_sheets(path):
            sample = [dict(zip(header, vals, strict=False)) for _, vals in (r for _, r in zip(range(3), rows, strict=False))]
            m = build_mapping(header, _parse_mapping(mapping))
            sheets.append({"sheet": sheet, "columns": header, "mapping": {c: s.describe() for c, s in m.items()},
                           "summary": mapping_summary(m), "sample_rows": json.loads(json.dumps(sample, default=str))})
        return {"file": path.name, "sheets": sheets}
    except UnsupportedFile as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)


@app.post("/api/imports", dependencies=[Depends(require_key)])
def run_import(file: UploadFile = File(...), mapping: str | None = Form(None), force: bool = Form(False),
               session: Session = Depends(get_session)):
    path = _save_upload(file)
    try:
        rep = import_file(session, path, overrides=_parse_mapping(mapping), original_name=Path(file.filename or path.name).name, force=force)
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)
    if rep.get("status") == "failed":
        raise HTTPException(422, rep.get("error", "İçe aktarma başarısız."))
    return rep


@app.get("/api/imports")
def list_imports(session: Session = Depends(get_session)):
    rows = session.scalars(select(ImportRun).order_by(ImportRun.id.desc())).all()
    return [{"id": r.id, "file": r.file_name, "status": r.status, "season": r.season_hint,
             "started_at": r.started_at, "finished_at": r.finished_at,
             "matches_imported": (r.report or {}).get("matches_imported")} for r in rows]


@app.get("/api/imports/{run_id}")
def get_import(run_id: int, session: Session = Depends(get_session)):
    r = session.get(ImportRun, run_id)
    if r is None:
        raise HTTPException(404, "İçe aktarma çalışması bulunamadı.")
    return {"id": r.id, "file": r.file_name, "status": r.status, "mapping": r.mapping, "report": r.report}


@app.get("/api/imports/{run_id}/issues")
def get_issues(run_id: int, issue_type: str | None = None, limit: int = Query(100, le=1000), offset: int = 0,
               session: Session = Depends(get_session)):
    q = select(DataQualityLog).where(DataQualityLog.import_run_id == run_id)
    if issue_type:
        q = q.where(DataQualityLog.issue_type == issue_type)
    rows = session.scalars(q.order_by(DataQualityLog.id).limit(limit).offset(offset)).all()
    return [{"severity": x.severity, "type": x.issue_type, "sheet": x.sheet, "row": x.row_number, "column": x.column_name,
             "raw": x.raw_value, "message": x.message} for x in rows]


@app.get("/api/data/summary")
def data_summary(session: Session = Depends(get_session)):
    return dataset.dataset_summary(session)


@app.get("/api/matches")
def matches(division: str | None = None, season: str | None = None, team: str | None = None,
            date_from: date | None = None, date_to: date | None = None,
            limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
            session: Session = Depends(get_session)):
    return dataset.search_matches(session, division=division, season=season, team=team, date_from=date_from,
                                  date_to=date_to, limit=limit, offset=offset)


@app.get("/api/teams/alias-suggestions")
def alias_suggestions(threshold: float = Query(0.88, ge=0.5, le=1.0), session: Session = Depends(get_session)):
    return dataset.suggest_team_aliases(session, threshold)


@app.post("/api/teams/aliases", dependencies=[Depends(require_key)])
def create_alias(country: str, alias: str, team_id: int, session: Session = Depends(get_session)):
    try:
        dataset.add_alias(session, country, alias, team_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"ok": True}


@app.post("/api/admin/backup", dependencies=[Depends(require_key)])
def backup():
    try:
        return {"path": str(backup_database())}
    except BackupUnsupported as exc:
        raise HTTPException(501, str(exc)) from exc


class SimilarRequest(BaseModel):
    odds_1x2: tuple[float, float, float]
    odds_ou25: tuple[float, float] | None = None
    scope: str = Field("all", pattern="^(all|league|team)$")
    divisions: list[str] = []
    team: str | None = None
    venue: str = Field("any", pattern="^(any|home|away)$")
    opponent: str | None = None
    last_seasons: int | None = Field(None, ge=1, le=20)
    top_n: int = Field(50, ge=1, le=500)
    max_dist: float | None = Field(None, gt=0, le=0.2)  # verilirse N sınırı yok: bu uzaklık içindeki tüm maçlar
    min_n: int | None = Field(None, ge=1)
    min_similarity: float = Field(0, ge=0, le=100)
    min_sample: int = Field(30, ge=1)

    @model_validator(mode="after")
    def _odds_valid(self):
        if any(o <= 1.0 for o in self.odds_1x2) or (self.odds_ou25 and any(o <= 1.0 for o in self.odds_ou25)):
            raise ValueError("Oranlar 1.00'dan büyük olmalı.")
        return self


_frame_cache: dict = {}


def _frame(session: Session):
    """Özellik tablosu bellekte tutulur; yeni içe aktarma sonrası /api/similar/reload çağrılır."""
    if "df" not in _frame_cache:
        from app.analysis.features import load_feature_frame
        _frame_cache["df"] = load_feature_frame(session)
    return _frame_cache["df"]


@app.post("/api/similar/reload", dependencies=[Depends(require_key)])
def reload_frame():
    _frame_cache.clear()
    return {"ok": True}


@app.post("/api/similar")
def similar(req: SimilarRequest, session: Session = Depends(get_session)):
    sc = Scope(kind=req.scope, divisions=req.divisions, team=req.team, venue=req.venue, opponent=req.opponent,
               last_seasons=req.last_seasons)
    df = _frame(session)
    if df.empty:
        _frame_cache.clear()
        raise HTTPException(409, "Arşiv boş: önce maç dosyalarını içe aktarın.")
    try:
        return analyze(df, SimQuery(req.odds_1x2, req.odds_ou25), sc, top_n=req.top_n,
                       min_sim=req.min_similarity, min_sample=req.min_sample, max_dist=req.max_dist, min_n=req.min_n)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


# ---------------- canlı veri, bülten, otomatik maç analizi ----------------
_matcher_cache: dict = {}


def _matcher(session: Session):
    if "m" not in _matcher_cache:
        from app.services.teams import TeamMatcher
        _matcher_cache["m"] = TeamMatcher(_frame(session))
    return _matcher_cache["m"]


@app.get("/api/live/status")
def live_status(session: Session = Depends(get_session)):
    from app.services.live import provider_status
    return provider_status(session)


class RefreshRequest(BaseModel):
    sport_keys: list[str] = Field(min_length=1, max_length=10)


@app.post("/api/live/refresh", dependencies=[Depends(require_key)])
def live_refresh(req: RefreshRequest, session: Session = Depends(get_session)):
    from app.providers.base import ProviderError
    from app.services.live import refresh
    try:
        return refresh(session, req.sport_keys, _matcher(session))
    except ProviderError as exc:
        status = {"no_key": 503, "bad_key": 502, "quota": 429, "network": 504}.get(exc.code, 502)
        raise HTTPException(status, str(exc)) from exc


@app.get("/api/live/fixtures")
def live_fixtures(hours: int = Query(72, ge=1, le=720), session: Session = Depends(get_session)):
    from app.services.live import list_fixtures
    return list_fixtures(session, hours)


class BulletinRequest(BaseModel):
    text: str = Field(max_length=200_000)


@app.post("/api/bulletin/parse")
def bulletin_parse(req: BulletinRequest, session: Session = Depends(get_session)):
    """Yapıştırılan bülteni ayrıştırır ve takımları arşivle eşler (veritabanına yazmaz)."""
    from app.providers.manual import parse_bulletin
    res = parse_bulletin(req.text)
    df = _frame(session)
    if not df.empty:
        m = _matcher(session)
        for x in res["matches"]:
            x["home_archive"], x["away_archive"] = m.match(None, x["home"]), m.match(None, x["away"])
    return res


class AnalyzeRequest(BaseModel):
    odds_1x2: tuple[float, float, float]
    odds_ou25: tuple[float, float] | None = None
    home_archive: str | None = None  # "Ülke|Takım" (bulletin/parse veya fixtures'tan)
    away_archive: str | None = None
    division: str | None = None
    offered_1x2: tuple[float, float, float] | None = None
    offered_ou25: tuple[float, float] | None = None

    @model_validator(mode="after")
    def _valid(self):
        for o in (self.odds_1x2, self.odds_ou25, self.offered_1x2, self.offered_ou25):
            if o and any(x <= 1.0 for x in o):
                raise ValueError("Oranlar 1.00'dan büyük olmalı.")
        return self


@app.post("/api/match/analyze")
def match_analyze(req: AnalyzeRequest, session: Session = Depends(get_session)):
    from app.services.analysis import analyze_match, attach_ev
    df = _frame(session)
    if df.empty:
        raise HTTPException(409, "Arşiv boş: önce maç dosyalarını içe aktarın.")
    res = analyze_match(df, odds_1x2=req.odds_1x2, odds_ou25=req.odds_ou25, home_key=req.home_archive,
                        away_key=req.away_archive, division=req.division)
    return attach_ev(res, req.offered_1x2 or req.odds_1x2, req.offered_ou25 or req.odds_ou25)


# ---------------- tek dokunuşla bülten gelen kutusu (yer imi) ----------------
from fastapi import Request, Response  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse  # noqa: E402

_inbox: dict = {"id": 0, "text": "", "source": "", "ts": None}
INBOX_MAX = 400_000


def _check_inbox_key(k: str | None) -> None:
    key = get_settings().api_key
    if key and not secrets.compare_digest(k or "", key):
        raise HTTPException(401, "Geçersiz anahtar (k).")


@app.options("/api/bulletin/inbox")
def inbox_preflight(request: Request):
    h = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
         "Access-Control-Allow-Headers": "*", "Access-Control-Allow-Private-Network": "true"}
    return Response(status_code=204, headers=h)


@app.post("/api/bulletin/inbox")
async def inbox_post(request: Request, s: str = "", k: str | None = None):
    """Yer imi, açık sayfanın görünen metnini buraya gönderir (text/plain). Metin ayrıştırılmadan saklanır."""
    _check_inbox_key(k)
    body = (await request.body())[: INBOX_MAX * 4].decode("utf-8", errors="replace")[:INBOX_MAX]
    if not body.strip():
        raise HTTPException(400, "Boş içerik.")
    from datetime import datetime
    _inbox.update(id=_inbox["id"] + 1, text=body, source=s[:60], ts=datetime.now().isoformat(timespec="seconds"))
    return Response(status_code=204, headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Private-Network": "true"})


@app.get("/api/bulletin/inbox")
def inbox_get(after: int = 0, k: str | None = None):
    _check_inbox_key(k)
    if _inbox["id"] <= after:
        return {"id": _inbox["id"], "new": False}
    return {"id": _inbox["id"], "new": True, "text": _inbox["text"], "source": _inbox["source"], "ts": _inbox["ts"]}


APP_FILE = get_settings().upload_dir.parent.parent / "mobile" / "dist" / "oran-arsivi.html"


@app.get("/app")
def serve_app():
    """Aynı uygulamayı yerel sunucudan sunar; böylece gelen kutusuna bağlanabilir."""
    if not APP_FILE.exists():
        raise HTTPException(404, "Uygulama dosyası yok: cd backend && PYTHONPATH=. python ../mobile/build.py")
    return FileResponse(APP_FILE, media_type="text/html")


@app.get("/bookmarklet", response_class=HTMLResponse)
def bookmarklet(request: Request):
    base = f"{request.url.scheme}://{request.headers.get('host', 'localhost:8000')}"
    key = get_settings().api_key
    q = f"&k={key}" if key else ""
    code = ("javascript:(function(){var t=(document.body.innerText||'').slice(0,%d);"
            "try{navigator.clipboard.writeText(t)}catch(e){}"
            "fetch('%s/api/bulletin/inbox?s='+encodeURIComponent(location.hostname)+'%s',{method:'POST',mode:'no-cors',body:t})"
            ".then(function(){alert('Bülten gönderildi ('+t.length+' karakter)')}).catch(function(){alert('Gönderilemedi: sunucu çalışıyor mu?')})})()") % (INBOX_MAX, base, q)
    import html as _h
    return f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Bülten yer imi</title><body style="font:16px system-ui;max-width:640px;margin:2rem auto;padding:0 1rem;line-height:1.5">
<h1>Bülten yer imi</h1>
<p>Bu bağlantıyı yer imleri çubuğuna <b>sürükleyin</b>: <a href="{_h.escape(code, quote=True)}" style="padding:.4rem .8rem;background:#0b6b50;color:#fff;border-radius:8px;text-decoration:none">Bülteni gönder</a></p>
<ol><li>Kendi tarayıcınızda Nesine veya bahisçi bülten sayfasını açın, maç listesi görünsün (gerekirse aşağı kaydırıp tüm maçları yükleyin).</li>
<li>Yer imine tıklayın. Sayfada <i>görünen</i> metin bu sunucuya gönderilir ve panoya kopyalanır.</li>
<li><a href="{base}/app">Uygulamayı</a> açın: Bülten sekmesinde maçlar kendiliğinden listelenir.</li></ol>
<p style="color:#555;font-size:14px">Yer imi yalnızca sizin tarayıcınızda, sizin açtığınız sayfanın metnini okur; siteye istek göndermez ve koruma aşmaz. Sunucu {_h.escape(base)} adresinde çalışmalıdır.</p>"""
