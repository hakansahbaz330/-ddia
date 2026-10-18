import numpy as np
import pandas as pd
import pytest

from app.analysis.similarity import Query, Scope, analyze, apply_scope, devig, rank_similar, wilson
from app.markets import derive_outcomes


def make_df(rows):
    recs = []
    for i, (div, season, date, h, a, fh, fa, hh, ha, oh, od, oa, oo, ou) in enumerate(rows, start=1):
        recs.append({"match_id": i, "date": pd.Timestamp(date), "division": div, "league": div, "season": season,
                     "home": h, "away": a, "fth": fh, "fta": fa, "hth": hh, "hta": ha, "oh": oh, "od": od, "oa": oa,
                     "oo": oo, "ou": ou, "src_1x2": "PS:closing", **derive_outcomes(fh, fa, hh, ha)})
    return pd.DataFrame(recs)


ROWS = [
    ("E0", "2021-2022", "2021-09-01", "A", "B", 2, 1, 1, 0, 2.0, 3.4, 3.8, 1.8, 2.0),
    ("E0", "2022-2023", "2022-09-01", "A", "C", 0, 0, 0, 0, 2.05, 3.4, 3.7, 1.9, 1.95),
    ("D1", "2022-2023", "2022-10-01", "D", "E", 3, 2, 1, 1, 1.4, 5.0, 9.0, 1.4, 3.0),
    ("D1", "2023-2024", "2023-10-01", "E", "A", 1, 2, 0, 1, 2.0, 3.5, 3.7, 1.85, 1.95),
    ("E0", "2023-2024", "2023-11-01", "B", "A", 1, 1, 0, 0, None, None, None, None, None),
]


def test_devig_sums_to_one_and_formula():
    p = devig([2.0, 3.5, 4.0])
    assert sum(p) == pytest.approx(1)
    assert p[0] == pytest.approx((1 / 2.0) / (1 / 2 + 1 / 3.5 + 1 / 4))


def test_wilson_bounds():
    lo, hi = wilson(5, 10)
    assert 0.2 < lo < 0.5 < hi < 0.8
    assert wilson(0, 0) == (0.0, 1.0)


def test_ranking_orders_by_distance_and_skips_missing_odds():
    df = make_df(ROWS)
    r = rank_similar(df, Query((2.0, 3.4, 3.8)))
    assert len(r) == 4  # oranı olmayan maç elenir
    assert r.iloc[0].match_id == 1 and r.iloc[0].sim == pytest.approx(100)
    assert r.iloc[-1].match_id == 3  # 1.4/5/9 en uzak
    assert list(r.sim) == sorted(r.sim, reverse=True)


def test_ou_feature_changes_ranking():
    df = make_df(ROWS)
    a = rank_similar(df, Query((2.0, 3.4, 3.8)))
    b = rank_similar(df, Query((2.0, 3.4, 3.8), (1.4, 3.0)))  # çok gollü beklenti
    assert list(a.match_id) != list(b.match_id) or not np.allclose(a.sim, b.sim)


def test_scopes_filter_correctly():
    df = make_df(ROWS)
    assert set(apply_scope(df, Scope(kind="league", divisions=["D1"])).division) == {"D1"}
    t = apply_scope(df, Scope(kind="team", team="A"))
    assert set(t.match_id) == {1, 2, 4, 5}
    assert set(apply_scope(df, Scope(kind="team", team="A", venue="home")).match_id) == {1, 2}
    assert set(apply_scope(df, Scope(kind="team", team="A", venue="away")).match_id) == {4, 5}
    assert set(apply_scope(df, Scope(kind="team", team="A", opponent="B")).match_id) == {1, 5}
    assert set(apply_scope(df, Scope(last_seasons=1)).season) == {"2023-2024"}
    assert set(apply_scope(df, Scope(before_date="2022-09-15")).match_id) == {1, 2}
    with pytest.raises(ValueError):
        apply_scope(df, Scope(kind="league"))
    with pytest.raises(ValueError):
        apply_scope(df, Scope(kind="team"))


def test_analyze_frequencies_and_warnings():
    df = make_df(ROWS)
    r = analyze(df, Query((2.0, 3.4, 3.8)), Scope(), top_n=3, min_sample=30)
    assert r["used"] == 3 and r["warnings"]  # küçük örneklem uyarısı
    m = r["summary"]["markets"]
    assert m["Maç sonucu"]["1"]["n"] == 3
    # en benzer 3: maç 1 (2-1), 2 (0-0), 4 (1-2) => ev galibiyeti 1/3
    assert m["Maç sonucu"]["1"]["rate"] == pytest.approx(1 / 3)
    assert m["Gol üst (maç)"]["2.5 üst"]["rate"] + m["Gol üst (maç)"]["2.5 alt"]["rate"] == pytest.approx(1)
    assert r["summary"]["htft"]["1/1"]["count"] == 1
    assert r["matches"][0]["home"] == "A"


def test_no_future_leak_with_before_date():
    df = make_df(ROWS)
    r = analyze(df, Query((2.0, 3.4, 3.8)), Scope(before_date="2022-09-01"), top_n=10)
    assert r["used"] == 1 and r["matches"][0]["date"] == "2021-09-01"
