from datetime import date

from app.importer.clean import clean_row, result_from_score, season_from_filename, to_date
from app.importer.columns import build_mapping, classify_column, parse_override


def test_odds_column_classification():
    assert classify_column("B365H").describe() == "odds:B365:1X2:1:pre"
    assert classify_column("B365CD").describe() == "odds:B365:1X2:X:closing"
    assert classify_column("VCH").describe() == "odds:VC:1X2:1:pre"  # VC + H, V + CH değil
    assert classify_column("BWCA").describe() == "odds:BW:1X2:2:closing"
    assert classify_column("P>2.5").describe() == "odds:PS:OU 2.5:over:pre"
    assert classify_column("MaxC<2.5").describe() == "odds:Max:OU 2.5:under:closing"
    assert classify_column("PCAHH").describe() == "odds:PS:AH:home:closing"
    assert classify_column("BbMxH").bookmaker == "BbMax"
    assert classify_column("HFKC").kind == "stat"
    assert classify_column("FTR").kind == "ignore"
    assert classify_column("Gizemli").kind == "unknown"


def test_user_override():
    m = build_mapping(["Gizemli", "Date"], {"Gizemli": "odds:B365:1X2:H:closing"})
    assert m["Gizemli"].bookmaker == "B365" and m["Gizemli"].odds_type == "closing"
    import pytest
    with pytest.raises(ValueError):
        parse_override("odds:eksik")


def test_dates_and_seasons():
    assert to_date("12/08/2023") == date(2023, 8, 12)
    assert to_date("12/08/23") == date(2023, 8, 12)
    assert to_date("bozuk") is None
    assert season_from_filename("all-euro-data-2025-2026-1.xlsx") == "2025-2026"
    assert season_from_filename("rastgele.xlsx") is None


def test_result_from_score():
    assert [result_from_score(2, 1), result_from_score(1, 1), result_from_score(0, 3), result_from_score(None, 1)] == ["H", "D", "A", None]


def _row(**kw):
    base = {"Div": "E0", "Date": date(2023, 8, 12), "HomeTeam": "A", "AwayTeam": "B", "FTHG": 1, "FTAG": 0}
    return {**base, **kw}


def _map(row):
    return build_mapping(list(row))


def test_invalid_rows_rejected_not_zeroed():
    r = _row(Date="yok")
    assert clean_row(r, _map(r), "2023-2024").reject_reason == "invalid_date"
    r = _row(HomeTeam=None)
    assert clean_row(r, _map(r), "2023-2024").reject_reason == "missing_team"
    r = _row(AwayTeam="a")
    assert clean_row(r, _map(r), "2023-2024").reject_reason == "same_team"


def test_missing_score_stays_null():
    r = _row(FTHG=None, FTAG=None)
    c = clean_row(r, _map(r), "2023-2024")
    assert c.match["ft_home"] is None and c.match["ft_result"] is None
    assert any(i.issue_type == "missing_score" for i in c.issues)


def test_ht_greater_than_ft_dropped():
    r = _row(HTHG=3, HTAG=0)
    c = clean_row(r, _map(r), "2023-2024")
    assert c.match["ht_home"] is None
    assert any(i.issue_type == "ht_exceeds_ft" for i in c.issues)


def test_bad_odds_dropped_and_logged():
    r = _row(B365H=0.0, B365D=3.4, B365A="abc")
    c = clean_row(r, _map(r), "2023-2024")
    assert [x[1] for x in c.odds] == ["B365D"]
    assert {i.issue_type for i in c.issues} == {"invalid_odds"}
