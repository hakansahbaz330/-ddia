"""Tek maç için otomatik analiz: piyasa-Poisson, arşiv güç modeli, benzer maçlar, takım istatistikleri, EV."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from app.analysis.similarity import Query, Scope, analyze as similar_analyze
from app.models.market_poisson import DEFAULT_RHO, analyze_market, half_markets, market_probs, score_matrix, top_scores
from app.models.strength import StrengthModel, fit_strength

REPORT = Path(__file__).resolve().parent.parent.parent / "scripts" / "model_report.json"


def market_weight() -> tuple[float, str]:
    """Birleşimde piyasa modelinin ağırlığı: yalnızca doğrulama döneminde seçilmiş değer (scripts/evaluate_models.py)."""
    try:
        w = json.loads(REPORT.read_text())["blend"]["market_weight_chosen_on_validation"]
        return float(w), "doğrulama döneminde (2024-25) seçildi; test 2025-26"
    except (OSError, KeyError, ValueError):
        return 0.8, "doğrulanmadı (model_report.json yok): varsayılan"


_strength_cache: dict[str, StrengthModel] = {}


def get_strength(df: pd.DataFrame) -> StrengthModel:
    if "m" not in _strength_cache:
        _strength_cache["m"] = fit_strength(df)
    return _strength_cache["m"]


def team_form(df: pd.DataFrame, key: str, n: int = 10, venue: str = "any") -> dict:
    country, team = key.split("|", 1)
    d = df[(df.country == country) & ((df.home == team) | (df.away == team))]
    if venue == "home":
        d = d[d.home == team]
    elif venue == "away":
        d = d[d.away == team]
    d = d.sort_values(["date", "match_id"]).tail(n)
    if d.empty:
        return {"n": 0}
    ishome = d.home == team
    gf = np.where(ishome, d.fth, d.fta); ga = np.where(ishome, d.fta, d.fth)
    pts = np.where(gf > ga, 3, np.where(gf == ga, 1, 0))
    return {"n": int(len(d)), "ppg": float(pts.mean()), "gf": float(gf.mean()), "ga": float(ga.mean()),
            "win": float((gf > ga).mean()), "draw": float((gf == ga).mean()), "loss": float((gf < ga).mean()),
            "clean_sheet": float((ga == 0).mean()), "failed_to_score": float((gf == 0).mean()),
            "btts": float(d.btts_yes.mean()), "over_2_5": float(d.ft_over_2_5.mean()),
            "ht_goals_for": float(np.where(ishome, d.hth, d.hta)[~d.hth.isna().to_numpy()].mean()) if d.hth.notna().any() else None,
            "match_corners": float(d.corners_total.mean()) if d.corners_total.notna().any() else None,
            "match_cards": float(d.cards_total.mean()) if d.cards_total.notna().any() else None,
            "form": "".join("G" if g > a else "B" if g == a else "M" for g, a in zip(gf, ga, strict=True)),
            "last_date": str(d.date.max().date())}


def h2h(df: pd.DataFrame, a: str, b: str, n: int = 10) -> list[dict]:
    ca, ta = a.split("|", 1); cb, tb = b.split("|", 1)
    d = df[(df.country == ca) & (((df.home == ta) & (df.away == tb)) | ((df.home == tb) & (df.away == ta)))].tail(n)
    return [{"date": str(r.date.date()), "home": r.home, "away": r.away, "score": f"{int(r.fth)}-{int(r.fta)}"} for r in d.itertuples()][::-1]


def _ev(p: float, o: float | None) -> dict | None:
    return None if not o else {"offered": o, "p": p, "ev": p * o - 1}


def analyze_match(df: pd.DataFrame, *, odds_1x2, odds_ou25=None, home_key: str | None = None, away_key: str | None = None,
                  division: str | None = None, similar_top_n: int = 50) -> dict:
    warnings: list[str] = []
    mk = analyze_market(odds_1x2, odds_ou25, rho=DEFAULT_RHO)
    out: dict = {
        "market_model": {"lh": mk["fit"]["lh"], "la": mk["fit"]["la"], "fit_rmse": mk["fit"]["fit_rmse"], "rho": DEFAULT_RHO,
                         "target": mk["fit"]["target"], "markets": mk["markets"], "half_markets_approx": mk["half"],
                         "top_scores": mk["top_scores"]},
        "warnings": warnings, "teams": {"home": home_key, "away": away_key},
    }
    if mk["fit"]["fit_rmse"] > 0.03:
        warnings.append("Piyasa oranları tek bir Poisson dağılımına zor uyuyor (uyum hatası yüksek); oranları kontrol edin.")
    if not odds_ou25:
        warnings.append("2,5 üst/alt oranı girilmedi: toplam gol beklentisi yalnızca 1X2'den çıkarıldı, daha belirsiz.")
    matrix = mk["matrix"]
    w, wnote = market_weight()
    out["blend"] = {"market_weight": w, "note": wnote}
    if home_key and away_key:
        sm = get_strength(df)
        lam = sm.lambdas(home_key, away_key, division or "")
        if lam:
            ms = score_matrix(*lam, rho=DEFAULT_RHO)
            sp = market_probs(ms)
            out["strength_model"] = {"lh": lam[0], "la": lam[1], "markets": sp, "top_scores": top_scores(ms),
                                     "trained_until": sm.before, "note": "Yalnızca arşivdeki geçmiş skorlardan (oran kullanmaz)."}
            matrix = w * mk["matrix"] + (1 - w) * ms
            diff = {k: abs(mk["markets"][k] - sp[k]) for k in ("1", "X", "2", "over_2.5", "btts_yes")}
            out["disagreement"] = {"max_abs_diff": max(diff.values()), "by_market": diff,
                                   "flag": max(diff.values()) > 0.08}
            if out["disagreement"]["flag"]:
                warnings.append("Piyasa ve arşiv güç modeli belirgin ayrışıyor (%8 puandan fazla); bilinmeyen bir bilgi (sakatlık, rotasyon) olabilir.")
        else:
            warnings.append("Takımlardan biri arşivde bulunamadı: güç modeli ve takım istatistikleri hesaplanamadı.")
        def known(key: str) -> bool:
            c, t = key.split("|", 1)
            return bool(((df.country == c) & ((df.home == t) | (df.away == t))).any())

        if known(home_key) and known(away_key):
            out["form"] = {"home_overall": team_form(df, home_key), "home_at_home": team_form(df, home_key, venue="home"),
                           "away_overall": team_form(df, away_key), "away_away": team_form(df, away_key, venue="away")}
            out["h2h"] = h2h(df, home_key, away_key)
    mp = market_probs(matrix)
    out["combined"] = {"markets": mp, "half_markets_approx": half_markets(mk["fit"]["lh"], mk["fit"]["la"]),
                       "top_scores": top_scores(matrix, 10),
                       "matrix": [[round(float(x), 5) for x in row[:7]] for row in matrix[:7]],
                       "note": "Birleşik olasılık, doğrulamada seçilen ağırlıkla piyasa ve güç modelinin karışımıdır."
                               if home_key and away_key and "strength_model" in out else "Yalnızca piyasa modeli (takım eşleşmesi yok)."}
    sc = Scope(kind="all")
    sim = similar_analyze(df, Query(tuple(odds_1x2), tuple(odds_ou25) if odds_ou25 else None), sc, top_n=similar_top_n, list_limit=10)
    out["similar"] = {"used": sim["used"], "similarity_mean": sim["similarity"]["mean"], "warnings": sim["warnings"],
                      "markets": {g: sim["summary"]["markets"][g] for g in ("Maç sonucu", "Gol üst (maç)", "Karşılıklı gol")},
                      "top_scores": sim["summary"]["top_scores"][:5]}
    return out


def attach_ev(result: dict, offered_1x2=None, offered_ou25=None) -> dict:
    """Sunulan oranlara göre teorik EV (model olasılığı × oran − 1). Gerçekleşmiş kâr değildir."""
    mp = result["combined"]["markets"]
    ev = {}
    if offered_1x2:
        for sel, o in zip(("1", "X", "2"), offered_1x2, strict=True):
            ev[sel] = _ev(mp[sel], o)
    if offered_ou25:
        ev["over_2.5"] = _ev(mp["over_2.5"], offered_ou25[0])
        ev["under_2.5"] = _ev(1 - mp["over_2.5"], offered_ou25[1])
    result["ev"] = {"items": ev, "caveat": "Olasılık aynı bahisçinin oranlarından türetildiyse EV yaklaşık −marj çıkar. Pozitif EV, başka bahisçi/eski oran "
                                           "veya model sapması anlamına gelir ve doğrulanmadan avantaj sayılmamalıdır. Gerçekleşmiş kâr değildir."}
    return result
