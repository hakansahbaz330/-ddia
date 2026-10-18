"""Canlı fikstür/oran çekme ve saklama. Sağlayıcı anahtarı yoksa uygulama çalışmaya devam eder (manuel bülten)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.providers.base import FetchResult, ProviderError
from app.providers.odds_api import OddsApiProvider
from app.schema import DataSource, LiveFixture, LiveOddsRow
from app.services.teams import SPORT_TO_DIVISION, TeamMatcher


def provider_status(s: Session) -> dict:
    cfg = get_settings()
    src = s.get(DataSource, "the_odds_api")
    return {
        "the_odds_api": {
            "configured": bool(cfg.odds_api_key),
            "message": None if cfg.odds_api_key else "ODDS_API_KEY tanımlı değil; canlı oran çekilemez. Manuel bülten yapıştırma kullanılabilir.",
            "last_fetch_at": src.last_fetch_at if src else None,
            "requests_remaining": src.requests_remaining if src else None,
            "last_error": src.last_error if src else None,
        },
        "bet365_nesine_sofascore": "Doğrudan bağlayıcı yok: resmi/herkese açık API'leri yok ve kullanım koşulları otomatik veri çekmeyi kısıtlayabilir. "
                                   "Bu bahisçilerin oranları lisanslı sağlayıcının döndürdüğü kadarıyla gelir veya bülten elle yapıştırılır.",
    }


def refresh(s: Session, sport_keys: list[str], matcher: TeamMatcher | None, provider: OddsApiProvider | None = None) -> dict:
    cfg = get_settings()
    src = s.get(DataSource, "the_odds_api") or DataSource(provider="the_odds_api")
    s.add(src)
    try:
        provider = provider or OddsApiProvider(cfg.odds_api_key, cfg.odds_api_regions)
        src.terms_url, src.license_note = provider.terms_url, provider.license_note
        res: FetchResult = provider.fetch(sport_keys)
    except ProviderError as exc:
        src.last_error = str(exc)
        s.commit()
        raise
    n_fx = n_odds = unmatched = 0
    for fx in res.fixtures:
        div = SPORT_TO_DIVISION.get(fx.sport_key)
        row = s.scalar(select(LiveFixture).where(LiveFixture.provider == fx.provider, LiveFixture.ext_id == fx.ext_id))
        if row is None:
            row = LiveFixture(provider=fx.provider, ext_id=fx.ext_id, sport_key=fx.sport_key, home=fx.home, away=fx.away,
                              commence_time=fx.commence_time)
            s.add(row)
        row.league_title, row.division = fx.league_title, div
        if matcher:
            row.home_archive, row.away_archive = matcher.match(div, fx.home), matcher.match(div, fx.away)
            unmatched += (row.home_archive is None) + (row.away_archive is None)
        s.flush()
        n_fx += 1
        for o in fx.odds:
            ins = sqlite_insert(LiveOddsRow).values(fixture_id=row.id, bookmaker=o.bookmaker, market=o.market, selection=o.selection,
                                                    odds=o.odds, source_updated_at=o.source_updated_at).on_conflict_do_nothing()
            n_odds += s.execute(ins).rowcount or 0
    src.last_fetch_at, src.requests_remaining, src.last_error = datetime.utcnow(), res.requests_remaining, None
    s.commit()
    return {"fixtures": n_fx, "new_odds_rows": n_odds, "unmatched_team_names": unmatched, "requests_remaining": res.requests_remaining}


def list_fixtures(s: Session, hours: int = 72) -> list[dict]:
    """Yaklaşan maçlar ve bahisçi başına en güncel 1X2 / 2,5 oranları (eksik oranlar işaretlenir)."""
    now = datetime.utcnow()
    fxs = s.scalars(select(LiveFixture).where(LiveFixture.commence_time >= now).order_by(LiveFixture.commence_time)).all()
    out = []
    for fx in fxs:
        if (fx.commence_time - now).total_seconds() > hours * 3600:
            continue
        rows = s.scalars(select(LiveOddsRow).where(LiveOddsRow.fixture_id == fx.id).order_by(LiveOddsRow.id)).all()
        latest: dict[tuple, LiveOddsRow] = {}
        for r in rows:
            latest[(r.bookmaker, r.market, r.selection)] = r
        books: dict[str, dict] = {}
        for (bk, mk, sel), r in latest.items():
            books.setdefault(bk, {})[f"{mk}:{sel}"] = r.odds
        complete = {bk: v for bk, v in books.items() if all(f"1X2:{k}" in v for k in "1X2")}
        out.append({"id": fx.id, "home": fx.home, "away": fx.away, "league": fx.league_title, "division": fx.division,
                    "kickoff_utc": fx.commence_time.isoformat(), "archive_match": bool(fx.home_archive and fx.away_archive),
                    "bookmakers": complete, "missing_odds": not complete})
    return out
