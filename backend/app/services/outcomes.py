"""match_outcomes tablosunu maç skorlarından/istatistiklerinden doldurur (idempotent: eskisini yeniden yazar)."""
from __future__ import annotations

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.markets import derive_outcomes
from app.schema import Match, TeamMatchStat, match_outcomes

BATCH = 5000


def rebuild_outcomes(s: Session, match_ids: list[int] | None = None) -> int:
    q = select(Match.id, Match.ft_home, Match.ft_away, Match.ht_home, Match.ht_away)
    if match_ids is not None:
        q = q.where(Match.id.in_(match_ids))
    matches = s.execute(q).all()
    stats: dict[tuple[int, str], tuple] = {}
    sq = select(TeamMatchStat.match_id, TeamMatchStat.side, TeamMatchStat.corners, TeamMatchStat.yellow_cards,
                TeamMatchStat.red_cards)
    if match_ids is not None:
        sq = sq.where(TeamMatchStat.match_id.in_(match_ids))
    for mid, side, c, y, r in s.execute(sq):
        stats[(mid, side)] = (c, y, r)
    n = 0
    for i in range(0, len(matches), BATCH):
        part = matches[i:i + BATCH]
        rows = []
        for mid, fh, fa, hh, ha in part:
            h, a = stats.get((mid, "H"), (None,) * 3), stats.get((mid, "A"), (None,) * 3)
            rows.append({"match_id": mid, **derive_outcomes(fh, fa, hh, ha, h[0], a[0], h[1], a[1], h[2], a[2])})
        s.execute(delete(match_outcomes).where(match_outcomes.c.match_id.in_([r["match_id"] for r in rows])))
        s.execute(insert(match_outcomes), rows)
        n += len(rows)
    s.commit()
    return n
