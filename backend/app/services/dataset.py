"""Veritabanı genelinde arşiv özeti ve sorgular (Veri Merkezi için)."""
from __future__ import annotations

import difflib
import itertools
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.schema import Match, match_outcomes, OddsHistory, OddsSource, Team, TeamAlias, TeamMatchStat


def dataset_summary(s: Session) -> dict:
    total = s.scalar(select(func.count(Match.id))) or 0
    scored = s.scalar(select(func.count(Match.id)).where(Match.ft_home.is_not(None))) or 0
    ht = s.scalar(select(func.count(Match.id)).where(Match.ht_home.is_not(None))) or 0
    dmin, dmax = s.execute(select(func.min(Match.match_date), func.max(Match.match_date))).one()
    by_season = {k: n for k, n in s.execute(select(Match.season, func.count()).group_by(Match.season).order_by(Match.season))}
    leagues = [
        {"division": d, "country": c, "league": ln, "tier": t, "matches": n}
        for d, c, ln, t, n in s.execute(
            select(Match.division, Match.country, Match.league_name, Match.tier, func.count())
            .group_by(Match.division, Match.country, Match.league_name, Match.tier).order_by(Match.country, Match.tier))
    ]
    markets = [
        {"market": m, "bookmaker": b, "odds_type": ot, "observations": n}
        for m, b, ot, n in s.execute(
            select(OddsSource.market, OddsSource.bookmaker, OddsSource.odds_type, func.count(OddsHistory.id))
            .join(OddsHistory, OddsHistory.source_id == OddsSource.id)
            .group_by(OddsSource.market, OddsSource.bookmaker, OddsSource.odds_type)
            .order_by(OddsSource.market, OddsSource.bookmaker))
    ]
    stat_cols = ("shots", "shots_on_target", "fouls", "corners", "yellow_cards", "red_cards", "free_kicks_conceded", "xg")
    stats = {c: s.scalar(select(func.count(getattr(TeamMatchStat, c)))) or 0 for c in stat_cols}
    return {
        "matches": total, "matches_with_ft_score": scored, "matches_with_ht_score": ht,
        "matches_pending_or_unscored": total - scored,
        "teams": s.scalar(select(func.count(Team.id))) or 0,
        "odds_observations": s.scalar(select(func.count(OddsHistory.id))) or 0,
        "date_range": [str(dmin) if dmin else None, str(dmax) if dmax else None],
        "outcome_base_rates": outcome_base_rates(s),
        "seasons": by_season, "leagues": leagues, "odds_markets": markets, "team_stat_availability": stats,
        "notes": [
            "Sezon 2026-2027 kısmidir (dosya yalnızca oynanmış maçları içerir).",
            "Kapsanan sezon sayısı: %d (10 yıl değil)." % len(by_season),
        ],
    }


def outcome_base_rates(s: Session) -> dict:
    """Türetilmiş sonuçların arşiv genelindeki gerçekleşme oranı (girdisi olan maçlar üzerinden)."""
    from app.markets import INT_COLUMNS
    flags = [c for c in INT_COLUMNS if c.startswith(("ft_over", "ht_over", "sh_over", "corners_over", "cards_over"))
             or c in ("ft_1", "ft_x", "ft_2", "dc_1x", "dc_12", "dc_x2", "ht_1", "ht_x", "ht_2", "btts_yes", "ht_btts_yes")]
    cols = []
    for c in flags:
        cols += [func.avg(match_outcomes.c[c]), func.count(match_outcomes.c[c])]
    row = s.execute(select(*cols)).one()
    return {c: {"rate": round(row[2 * i], 4) if row[2 * i] is not None else None, "n": row[2 * i + 1]}
            for i, c in enumerate(flags)}


def search_matches(s: Session, *, division: str | None = None, season: str | None = None, team: str | None = None,
                   date_from: date | None = None, date_to: date | None = None, limit: int = 50, offset: int = 0) -> dict:
    q = select(Match)
    if division:
        q = q.where(Match.division == division)
    if season:
        q = q.where(Match.season == season)
    if team:
        like = f"%{team}%"
        q = q.where(Match.home_team.ilike(like) | Match.away_team.ilike(like))
    if date_from:
        q = q.where(Match.match_date >= date_from)
    if date_to:
        q = q.where(Match.match_date <= date_to)
    total = s.scalar(select(func.count()).select_from(q.subquery()))
    rows = s.scalars(q.order_by(Match.match_date.desc(), Match.id.desc()).limit(limit).offset(offset)).all()
    return {"total": total, "limit": limit, "offset": offset, "items": [
        {"id": m.id, "date": str(m.match_date), "division": m.division, "league": m.league_name, "season": m.season,
         "home": m.home_team, "away": m.away_team, "ft": [m.ft_home, m.ft_away], "ht": [m.ht_home, m.ht_away],
         "result": m.ft_result} for m in rows]}


def suggest_team_aliases(s: Session, threshold: float = 0.88) -> list[dict]:
    """Aynı ülkede çok benzer yazılan takım adı çiftleri. Otomatik birleştirilmez; kullanıcı onayı gerekir."""
    out = []
    by_country: dict[str, list[tuple[int, str]]] = {}
    for tid, country, name in s.execute(select(Team.id, Team.country, Team.name)):
        by_country.setdefault(country, []).append((tid, name))
    for country, teams in by_country.items():
        for (ida, a), (idb, b) in itertools.combinations(teams, 2):
            ratio = difflib.SequenceMatcher(None, a.casefold(), b.casefold()).ratio()
            if ratio >= threshold:
                out.append({"country": country, "a": {"id": ida, "name": a}, "b": {"id": idb, "name": b},
                            "similarity": round(ratio, 3)})
    return sorted(out, key=lambda x: -x["similarity"])


def add_alias(s: Session, country: str, alias: str, team_id: int) -> None:
    """Onaylanan takma adı kaydeder; sonraki içe aktarmalarda alias -> kanonik ad dönüşümü uygulanır."""
    if s.get(Team, team_id) is None:
        raise ValueError(f"Takım bulunamadı: {team_id}")
    s.merge(TeamAlias(alias=alias, country=country, team_id=team_id))
    s.commit()
