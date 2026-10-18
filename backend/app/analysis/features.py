"""Benzerlik/analiz için tek tablo: maç başına en iyi 1X2 ve 2,5 üst/alt oranı + türetilmiş sonuçlar."""
from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

# Öncelik sırası: kapanış (C) oranlar önce; sonra maç öncesi. Kaynak kodu 'odds_src' sütununda kalır.
PRIORITY_1X2 = [("PS", "closing"), ("Avg", "closing"), ("B365", "closing"), ("PS", "pre"), ("B365", "pre"), ("BW", "pre")]
PRIORITY_OU = [("PS", "closing"), ("Avg", "closing"), ("B365", "closing"), ("PS", "pre"), ("B365", "pre"), ("BbAvg", "unspecified")]


def _best(s: Session, market: str, selections: dict[str, str], priority) -> pd.DataFrame:
    """Her maç için öncelik sırasındaki ilk eksiksiz oran kümesini seçer."""
    bks = sorted({b for b, _ in priority})
    sql = text("""SELECT h.match_id, s.bookmaker AS bk, s.odds_type AS ot, s.selection AS sel, h.odds
                  FROM odds_history h JOIN odds_sources s ON s.id = h.source_id
                  WHERE s.market = :m AND s.bookmaker IN (%s) AND (s.line_key = '' OR s.line_key = '2.5')"""
               % ",".join(f"'{b}'" for b in bks))
    df = pd.read_sql(sql, s.connection(), params={"m": market})
    if df.empty:
        return pd.DataFrame(columns=["match_id", *selections.values(), "src"])
    df = df.drop_duplicates(["match_id", "bk", "ot", "sel"], keep="last")
    wide = df.pivot_table(index=["match_id", "bk", "ot"], columns="sel", values="odds", aggfunc="last").reset_index()
    need = list(selections)
    wide = wide.dropna(subset=need)
    rank = {p: i for i, p in enumerate(priority)}
    wide["rank"] = [rank.get((b, o), 99) for b, o in zip(wide.bk, wide.ot, strict=True)]
    wide = wide[wide["rank"] < 99].sort_values("rank").drop_duplicates("match_id")
    out = wide[["match_id", "bk", "ot", *need]].rename(columns=selections)
    out["src"] = out.bk + ":" + out.ot
    return out.drop(columns=["bk", "ot"])


def load_feature_frame(s: Session) -> pd.DataFrame:
    base = pd.read_sql(text("""
        SELECT m.id AS match_id, m.match_date AS date, m.division, m.country, m.league_name AS league, m.season,
               m.home_team AS home, m.away_team AS away, m.ft_home AS fth, m.ft_away AS fta, m.ht_home AS hth, m.ht_away AS hta,
               o.*
        FROM matches m JOIN match_outcomes o ON o.match_id = m.id
        WHERE m.ft_home IS NOT NULL"""), s.connection())
    base = base.loc[:, ~base.columns.duplicated()]
    base["date"] = pd.to_datetime(base["date"])
    o1 = _best(s, "1X2", {"1": "oh", "X": "od", "2": "oa"}, PRIORITY_1X2).rename(columns={"src": "src_1x2"})
    ou = _best(s, "OU", {"over": "oo", "under": "ou"}, PRIORITY_OU).rename(columns={"src": "src_ou"})
    df = base.merge(o1, on="match_id", how="left").merge(ou, on="match_id", how="left")
    return df.sort_values(["date", "match_id"]).reset_index(drop=True)
