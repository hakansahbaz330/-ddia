import numpy as np
import pytest

from app.models.market_poisson import analyze_market, devig, fit_from_market, market_probs, score_matrix, top_scores
from app.providers.manual import parse_bulletin
from app.providers.odds_api import OddsApiProvider, parse_events
from app.providers.base import ProviderError


def test_poisson_matrix_is_consistent():
    m = score_matrix(1.6, 1.1)
    assert m.sum() == pytest.approx(1)
    mp = market_probs(m)
    assert mp["1"] + mp["X"] + mp["2"] == pytest.approx(1)
    assert mp["1X"] == pytest.approx(mp["1"] + mp["X"])
    assert mp["over_2.5"] == pytest.approx(1 - sum(m[i, j] for i in range(11) for j in range(11) if i + j <= 2))
    assert top_scores(m)[0]["score"] in ("1-1", "2-1", "1-0")
    md = score_matrix(1.6, 1.1, rho=-0.1)
    assert md.sum() == pytest.approx(1) and md[0, 0] != m[0, 0]


def test_fit_recovers_market_probabilities():
    odds = (2.0, 3.5, 4.0)
    fit = fit_from_market(odds, (1.9, 1.95))
    p = devig(odds)
    mp = market_probs(score_matrix(fit["lh"], fit["la"]))
    assert abs(mp["1"] - p[0]) < 0.02 and abs(mp["2"] - p[2]) < 0.02
    assert abs(mp["over_2.5"] - devig((1.9, 1.95))[0]) < 0.03
    assert fit["lh"] > fit["la"]
    # daha düşük ev oranı => daha yüksek ev beklentisi
    assert fit_from_market((1.5, 4.2, 7.0))["lh"] > fit["lh"]


def test_analyze_market_outputs():
    r = analyze_market((2.4, 3.3, 3.0), (2.0, 1.85))
    assert set(r["markets"]) >= {"1", "X", "2", "btts_yes", "over_2.5", "1X"}
    assert r["half"]["ht_1"] + r["half"]["ht_x"] + r["half"]["ht_2"] == pytest.approx(1)
    assert len(r["top_scores"]) == 8


def test_bulletin_parser():
    t = "Süper Lig\n20:00 Galatasaray - Fenerbahçe 1,85 3,40 4,20 1,80 1,95\nArsenal vs Chelsea\t2.10\t3.50\t3.40\nBozuk - satır 1,5\nA - B 0.9 3 4"
    r = parse_bulletin(t)
    assert [(m["home"], m["away"]) for m in r["matches"]] == [("Galatasaray", "Fenerbahçe"), ("Arsenal", "Chelsea")]
    assert r["matches"][0]["odds_ou25"] == [1.8, 1.95] and r["matches"][1]["odds_ou25"] is None
    assert len(r["errors"]) == 2  # eksik oran, 1.00 altı oran; başlık satırı hata sayılmaz


SAMPLE = [{"id": "e1", "sport_key": "soccer_x", "sport_title": "X", "commence_time": "2026-10-20T18:00:00Z", "home_team": "Foo", "away_team": "Bar",
           "bookmakers": [{"key": "bk1", "title": "BK1", "last_update": "2026-10-19T10:00:00Z", "markets": [
               {"key": "h2h", "outcomes": [{"name": "Foo", "price": 2.1}, {"name": "Bar", "price": 3.3}, {"name": "Draw", "price": 3.4}]},
               {"key": "totals", "outcomes": [{"name": "Over", "price": 1.9, "point": 2.5}, {"name": "Under", "price": 1.95, "point": 2.5},
                                              {"name": "Over", "price": 1.4, "point": 1.5}]}]}]}]


def test_odds_api_parsing():
    fx = parse_events(SAMPLE)[0]
    got = {(o.market, o.selection): o.odds for o in fx.odds}
    assert got == {("1X2", "1"): 2.1, ("1X2", "2"): 3.3, ("1X2", "X"): 3.4, ("OU2.5", "over"): 1.9, ("OU2.5", "under"): 1.95}


def test_provider_errors_are_readable():
    with pytest.raises(ProviderError) as e:
        OddsApiProvider("")
    assert e.value.code == "no_key" and "ODDS_API_KEY" in str(e.value)
    import httpx
    for status, code in ((401, "bad_key"), (429, "quota"), (500, "http_error")):
        c = httpx.Client(transport=httpx.MockTransport(lambda req, s=status: httpx.Response(s)))
        with pytest.raises(ProviderError) as e:
            OddsApiProvider("k", client=c).fetch(["soccer_x"])
        assert e.value.code == code
    ok = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=SAMPLE, headers={"x-requests-remaining": "480"})))
    res = OddsApiProvider("k", client=ok).fetch(["soccer_x"])
    assert res.requests_remaining == 480 and len(res.fixtures) == 1
    boom = httpx.Client(transport=httpx.MockTransport(lambda req: (_ for _ in ()).throw(httpx.ConnectError("x"))))
    with pytest.raises(ProviderError) as e:
        OddsApiProvider("k", client=boom).fetch(["soccer_x"])
    assert e.value.code == "network"
