"""Arşiv içe aktarma motoru: akışlı okuma, parça parça temizleme, toplu veritabanı yazımı."""
from __future__ import annotations

import hashlib
import traceback
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.importer.clean import CleanRow, Issue, clean_row, season_from_filename
from app.importer.columns import BOOKMAKER_NAMES, ColumnSpec, build_mapping, mapping_summary
from app.importer.readers import UnsupportedFile, iter_sheets
from app.schema import (
    DataQualityLog,
    ImportRun,
    Match,
    OddsHistory,
    OddsSource,
    Team,
    TeamAlias,
    TeamMatchStat,
)

STAT_FIELDS = ("shots", "shots_on_target", "fouls", "corners", "yellow_cards", "red_cards",
               "free_kicks_conceded", "xg")
CHUNK_ROWS = 1500
LOG_SAMPLE_PER_TYPE = 50  # her sorun türü için en fazla bu kadar örnek satır loglanır; toplam sayı raporda


def _ignore_dup_insert(session: Session, table):
    name = session.bind.dialect.name
    ins = pg_insert(table) if name == "postgresql" else sqlite_insert(table)
    return ins.on_conflict_do_nothing()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class _Run:
    """Bir içe aktarma çalışmasının durumu ve sayaçları."""

    def __init__(self, session: Session, run: ImportRun):
        self.s = session
        self.run = run
        self.c: Counter = Counter()
        self.issue_totals: Counter = Counter()
        self.issue_logged: Counter = Counter()
        self.rejects: Counter = Counter()
        self.by_league_season: Counter = Counter()
        self.market_cov: dict[tuple, int] = defaultdict(int)  # (market, bookmaker, odds_type) -> dolu hücre
        self.column_nonnull: Counter = Counter()
        self.date_min = self.date_max = None
        self.seen_keys: dict[str, tuple] = {}  # bu dosyada görülen match_key -> skor
        self.team_cache: dict[tuple[str, str], int] = {}
        self.source_cache: dict[tuple, int] = {}
        self.pending_logs: list[dict] = []
        self.sheets: list[dict] = []

    def log(self, issue, sheet: str, row: int, key: str | None):
        self.issue_totals[issue.issue_type] += 1
        if self.issue_logged[issue.issue_type] >= LOG_SAMPLE_PER_TYPE:
            return
        self.issue_logged[issue.issue_type] += 1
        self.pending_logs.append(dict(
            import_run_id=self.run.id, severity=issue.severity, issue_type=issue.issue_type,
            sheet=sheet, row_number=row, match_key=key, column_name=issue.column,
            raw_value=issue.raw, message=issue.message))

    def flush_logs(self):
        if self.pending_logs:
            self.s.execute(insert(DataQualityLog), self.pending_logs)
            self.pending_logs = []

    def team_id(self, country: str | None, name: str) -> int:
        k = (country or "", name)
        tid = self.team_cache.get(k)
        if tid is None:
            tid = self.s.scalar(select(Team.id).where(Team.country == k[0], Team.name == name))
            if tid is None:
                tid = self.s.execute(insert(Team).values(name=name, country=k[0])).inserted_primary_key[0]
            self.team_cache[k] = tid
        return tid

    def source_id(self, spec: ColumnSpec, column: str) -> int:
        line_key = "" if spec.line is None else f"{spec.line:g}"
        k = (spec.bookmaker, spec.market, spec.selection, line_key, spec.odds_type)
        sid = self.source_cache.get(k)
        if sid is None:
            sid = self.s.scalar(select(OddsSource.id).where(
                OddsSource.bookmaker == k[0], OddsSource.market == k[1], OddsSource.selection == k[2],
                OddsSource.line_key == k[3], OddsSource.odds_type == k[4]))
            if sid is None:
                sid = self.s.execute(insert(OddsSource).values(
                    source_column=column, bookmaker=spec.bookmaker,
                    bookmaker_name=BOOKMAKER_NAMES.get(spec.bookmaker, spec.bookmaker),
                    market=spec.market, selection=spec.selection, line=spec.line,
                    line_key=line_key, odds_type=spec.odds_type)).inserted_primary_key[0]
            self.source_cache[k] = sid
        return sid


def _flush_chunk(r: _Run, sheet: str, chunk: list[tuple[int, CleanRow]]):
    """Bir satır grubunu veritabanına yazar: maçlar -> oranlar -> istatistikler."""
    s = r.s
    keys = [cr.match["match_key"] for _, cr in chunk]
    existing = {
        k: (mid, fh, fa) for k, mid, fh, fa in s.execute(
            select(Match.match_key, Match.id, Match.ft_home, Match.ft_away).where(Match.match_key.in_(keys)))
    }
    new_rows, to_attach = [], []  # to_attach: veritabanında zaten olan maçlar için sadece oran gözlemi eklenecek
    for rownum, cr in chunk:
        m = cr.match
        k = m["match_key"]
        score = (m["ft_home"], m["ft_away"])
        if k in r.seen_keys:
            same = r.seen_keys[k] == score
            r.c["duplicates_in_file"] += 1
            r.log(Issue("warning", "duplicate_in_file" if same else "conflict_in_file", None, k,
                        "Aynı maç dosyada tekrar ediyor" + ("" if same else " ve skorlar farklı") + "; ilk kayıt korundu."),
                  sheet, rownum, k)
            if not same:
                r.c["conflicts"] += 1
            continue
        r.seen_keys[k] = score
        if k in existing:
            mid, fh, fa = existing[k]
            r.c["already_in_db"] += 1
            if (fh, fa) != score and fh is not None and score[0] is not None:
                r.c["conflicts"] += 1
                r.log(Issue("warning", "conflict_with_db", None, k, f"Veritabanındaki skor {fh}-{fa}, dosyadaki {score[0]}-{score[1]}; veritabanı korundu."), sheet, rownum, k)
            else:
                to_attach.append((mid, cr))
            continue
        row = dict(m)
        row["home_team_id"] = r.team_id(m["country"], m["home_team"])
        row["away_team_id"] = r.team_id(m["country"], m["away_team"])
        row["import_run_id"] = r.run.id
        new_rows.append((row, cr))

    ids: dict[str, int] = {}
    if new_rows:
        s.execute(insert(Match), [row for row, _ in new_rows])
        ids = dict(s.execute(select(Match.match_key, Match.id).where(
            Match.match_key.in_([row["match_key"] for row, _ in new_rows]))).all())
        r.c["matches_imported"] += len(new_rows)
        for row, _ in new_rows:
            r.by_league_season[(row["division"], row["season"])] += 1
            d = row["match_date"]
            r.date_min = d if r.date_min is None or d < r.date_min else r.date_min
            r.date_max = d if r.date_max is None or d > r.date_max else r.date_max
            if row["ft_home"] is None:
                r.c["matches_without_score"] += 1
            else:
                r.c["matches_with_ft"] += 1
            if row["ht_home"] is not None:
                r.c["matches_with_ht"] += 1

    odds_rows, stat_rows = [], []
    for row, cr in new_rows:
        mid = ids[row["match_key"]]
        for side in ("H", "A"):
            st = cr.stats.get(side)
            if st:
                full = {f: None for f in STAT_FIELDS} | st  # executemany için tüm satırlarda aynı anahtarlar
                stat_rows.append(dict(match_id=mid, side=side,
                                      team_id=row["home_team_id"] if side == "H" else row["away_team_id"], **full))
        _collect_odds(r, mid, cr, odds_rows)
    for mid, cr in to_attach:
        _collect_odds(r, mid, cr, odds_rows)

    if odds_rows:
        res = s.execute(_ignore_dup_insert(s, OddsHistory.__table__), odds_rows)
        r.c["odds_inserted"] += res.rowcount if res.rowcount and res.rowcount > 0 else len(odds_rows)
    if stat_rows:
        s.execute(_ignore_dup_insert(s, TeamMatchStat.__table__), stat_rows)
        r.c["stat_rows"] += len(stat_rows)


def _collect_odds(r: _Run, mid: int, cr: CleanRow, out: list[dict]):
    for spec, col, x in cr.odds:
        out.append(dict(match_id=mid, source_id=r.source_id(spec, col), odds=x, import_run_id=r.run.id))
        r.market_cov[(spec.market, spec.bookmaker, spec.odds_type)] += 1


def import_file(
    session: Session,
    path: Path,
    *,
    overrides: dict[str, str] | None = None,
    original_name: str | None = None,
    force: bool = False,
) -> dict:
    """Tek dosyayı içe aktarır ve raporu döndürür. Aynı dosya (SHA-256) tekrar yüklenirse atlanır."""
    path = Path(path)
    name = original_name or path.name
    sha = file_sha256(path)
    if not force:
        prev = session.scalar(select(ImportRun).where(ImportRun.file_sha256 == sha, ImportRun.status == "ok"))
        if prev is not None:
            return {"status": "skipped", "run_id": prev.id, "file": name,
                    "message": f"Bu dosya daha önce aktarılmış (çalışma #{prev.id}). Yeniden aktarmak için force kullanın."}

    season = season_from_filename(name)
    run = ImportRun(file_name=name, file_sha256=sha, file_size=path.stat().st_size, season_hint=season, status="running")
    session.add(run)
    session.commit()
    r = _Run(session, run)
    aliases = {a: t for a, t in session.execute(
        select(TeamAlias.alias, Team.name).join(Team, Team.id == TeamAlias.team_id))}
    all_mappings: dict[str, ColumnSpec] = {}
    try:
        for sheet, header, rows in iter_sheets(path):
            mapping = build_mapping(header, overrides)
            for col, spec in mapping.items():
                all_mappings.setdefault(col, spec)
            summ = mapping_summary(mapping)
            sheet_stat = {"sheet": sheet, "columns": len(header), "unknown_columns": summ.get("unknown", []),
                          "rows": 0}
            missing = [t for t in ("date", "home_team", "away_team") if t not in {s.target for s in mapping.values() if s.kind == "core"}]
            if missing:
                r.log(Issue("error", "missing_required_columns", None, ",".join(missing),
                            f"Zorunlu alanlar eşleşmedi: {missing}. Sayfa atlandı; sütun eşleşmesini elle düzeltin."), sheet, 1, None)
                sheet_stat["skipped"] = f"zorunlu sütunlar eksik: {missing}"
                r.sheets.append(sheet_stat)
                continue
            for col in mapping:
                if mapping[col].kind == "unknown":
                        r.log(Issue("info", "unknown_column", col, None, "Sütun tanınmadı ve içe aktarılmadı."), sheet, 1, None)
            idx = {c: i for i, c in enumerate(header)}
            chunk: list[tuple[int, CleanRow]] = []
            for rownum, vals in rows:
                r.c["rows_found"] += 1
                sheet_stat["rows"] += 1
                cr = clean_row({c: vals[i] for c, i in idx.items()}, mapping, season, aliases)
                key = cr.match["match_key"] if cr.match else None
                for iss in cr.issues:
                    r.log(iss, sheet, rownum, key)
                if cr.match is None:
                    r.c["rows_rejected"] += 1
                    r.rejects[cr.reject_reason or "unknown"] += 1
                    continue
                for col, i in idx.items():
                    if mapping[col].kind in ("odds", "stat") and vals[i] not in (None, ""):
                        r.column_nonnull[col] += 1
                chunk.append((rownum, cr))
                if len(chunk) >= CHUNK_ROWS:
                    _flush_chunk(r, sheet, chunk)
                    r.flush_logs()
                    session.commit()
                    chunk = []
            if chunk:
                _flush_chunk(r, sheet, chunk)
            r.flush_logs()
            session.commit()
            r.sheets.append(sheet_stat)
        from app.services.outcomes import rebuild_outcomes

        report = _build_report(r, name, all_mappings)
        report["outcomes_built"] = rebuild_outcomes(session, list(session.scalars(select(Match.id).where(Match.import_run_id == run.id))))
        run.status = "ok"
    except UnsupportedFile as exc:
        session.rollback()
        run = session.get(ImportRun, run.id)
        run.status = "failed"
        report = {"status": "failed", "file": name, "error": str(exc)}
    except Exception as exc:  # beklenmeyen hata: kısmi veri kalmasın
        session.rollback()
        _purge_run(session, run.id)
        run = session.get(ImportRun, run.id)
        run.status = "failed"
        report = {"status": "failed", "file": name,
                  "error": f"Beklenmeyen hata: {exc.__class__.__name__}: {str(exc)[:300]}",
                  "trace": traceback.format_exc(limit=5)}
    run.report = report
    run.mapping = {c: sp.describe() for c, sp in all_mappings.items()}
    run.finished_at = datetime.now(UTC).replace(tzinfo=None)
    session.commit()
    report["run_id"] = run.id
    return report


def _purge_run(session: Session, run_id: int) -> None:
    """Başarısız çalışmanın yazdığı kısmi verileri temizler (maç silinince oran/istatistik CASCADE ile gider)."""
    from sqlalchemy import delete
    session.execute(delete(OddsHistory).where(OddsHistory.import_run_id == run_id))
    session.execute(delete(Match).where(Match.import_run_id == run_id))
    session.commit()


def _build_report(r: _Run, name: str, mapping: dict[str, ColumnSpec]) -> dict:
    c = r.c
    markets: dict[str, dict] = {}
    for (market, bk, otype), n in sorted(r.market_cov.items()):
        markets.setdefault(market, {}).setdefault(f"{bk}:{otype}", n)
    leagues: dict[str, dict[str, int]] = {}
    for (div, season), n in sorted(r.by_league_season.items()):
        leagues.setdefault(div, {})[season] = n
    return {
        "status": "ok",
        "file": name,
        "rows_found": c["rows_found"],
        "matches_imported": c["matches_imported"],
        "already_in_db": c["already_in_db"],
        "duplicates_in_file": c["duplicates_in_file"],
        "conflicts": c["conflicts"],
        "rows_rejected": c["rows_rejected"],
        "reject_reasons": dict(r.rejects),
        "matches_with_ft_score": c["matches_with_ft"],
        "matches_without_score": c["matches_without_score"],
        "matches_with_ht_score": c["matches_with_ht"],
        "odds_rows_inserted": c["odds_inserted"],
        "stat_rows_inserted": c["stat_rows"],
        "date_range": [str(r.date_min) if r.date_min else None, str(r.date_max) if r.date_max else None],
        "league_season_counts": leagues,
        "markets": markets,
        "issue_totals": dict(r.issue_totals),
        "unknown_columns": sorted({col for col, sp in mapping.items() if sp.kind == "unknown"}),
        "column_mapping": mapping_summary(mapping),
        "sheets": r.sheets,
        "odds_timing_note": (
            "Kaynak dosyalarda oran gözlem zamanı yoktur. 'closing' (kapanış) yalnızca sütun adındaki "
            "C işaretinden, 'pre' ise C içermeyen sütunlardan çıkarılmıştır; kesin zaman damgası değildir."),
    }
