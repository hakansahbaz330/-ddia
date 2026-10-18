"""Piyasa oranlarından Poisson skor dağılımı.

1X2 (ve varsa 2,5 üst/alt) marjdan arındırılır; beklenen goller (lh, la) bu olasılıklara en iyi uyacak şekilde
bulunur (en küçük kareler). Skor matrisinden tüm pazarlar türetilir. Dixon–Coles düzeltmesi (rho) isteğe bağlıdır.
İlk yarı pazarları yaklaşıktır: ilk yarı gollerinin payı arşivden hesaplanan sabit bir orandır (HT_SHARE).
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson

MAX_GOALS = 10
HT_SHARE = 0.444  # arşivde ilk yarı gollerinin payı (69.852 maç üzerinden ölçüldü)
DEFAULT_RHO = -0.05  # Dixon–Coles; 2024-25 örneğinde olabilirlik farkı çok küçük (0,6 log-birim)


def devig(odds) -> np.ndarray:
    inv = 1.0 / np.asarray(odds, dtype=float)
    return inv / inv.sum()


def score_matrix(lh: float, la: float, rho: float = 0.0, max_goals: int = MAX_GOALS) -> np.ndarray:
    g = np.arange(max_goals + 1)
    m = np.outer(poisson.pmf(g, lh), poisson.pmf(g, la))
    if rho:
        # Dixon–Coles: yalnızca düşük skorlar (0-0, 1-0, 0-1, 1-1) düzeltilir
        m[0, 0] *= max(0.0, 1 - lh * la * rho)
        m[0, 1] *= 1 + lh * rho
        m[1, 0] *= 1 + la * rho
        m[1, 1] *= max(0.0, 1 - rho)
    return m / m.sum()


def market_probs(m: np.ndarray) -> dict:
    n = m.shape[0]
    i, j = np.indices((n, n))
    tot = i + j
    out = {
        "1": float(m[i > j].sum()), "X": float(m[i == j].sum()), "2": float(m[i < j].sum()),
        "btts_yes": float(m[(i > 0) & (j > 0)].sum()),
    }
    out["1X"], out["12"], out["X2"] = out["1"] + out["X"], out["1"] + out["2"], out["X"] + out["2"]
    for x in (0.5, 1.5, 2.5, 3.5, 4.5):
        out[f"over_{x}"] = float(m[tot > x].sum())
    out["home_clean_sheet"] = float(m[:, 0].sum())
    out["away_clean_sheet"] = float(m[0, :].sum())
    return out


def top_scores(m: np.ndarray, k: int = 8) -> list[dict]:
    flat = np.argsort(m, axis=None)[::-1][:k]
    return [{"score": f"{a}-{b}", "p": float(m[a, b])} for a, b in (np.unravel_index(f, m.shape) for f in flat)]


def fit_from_market(odds_1x2, odds_ou25=None, rho: float = 0.0) -> dict:
    """(lh, la) bulur. Dönen: lambdalar, uyum hatası ve hedef olasılıklar."""
    p = devig(odds_1x2)
    target_ou = float(devig(odds_ou25)[0]) if odds_ou25 else None

    def loss(x):
        lh, la = np.exp(x)
        mp = market_probs(score_matrix(lh, la, rho))
        e = (mp["1"] - p[0]) ** 2 + (mp["X"] - p[1]) ** 2 + (mp["2"] - p[2]) ** 2
        if target_ou is not None:
            e += (mp["over_2.5"] - target_ou) ** 2
        return e

    best = min((minimize(loss, np.log(x0), method="Nelder-Mead", options={"xatol": 1e-6, "fatol": 1e-12, "maxiter": 800})
                for x0 in ((1.4, 1.1), (2.0, 0.8), (0.9, 1.6))), key=lambda r: r.fun)
    lh, la = np.exp(best.x)
    return {"lh": float(lh), "la": float(la), "rho": rho, "fit_rmse": float(np.sqrt(best.fun / (4 if target_ou is not None else 3))),
            "target": {"1": float(p[0]), "X": float(p[1]), "2": float(p[2]), "over_2.5": target_ou}}


def half_markets(lh: float, la: float, share: float = HT_SHARE) -> dict:
    """Yaklaşık ilk yarı pazarları (bağımsız Poisson, sabit gol payı)."""
    m = score_matrix(lh * share, la * share)
    mp = market_probs(m)
    return {"ht_1": mp["1"], "ht_x": mp["X"], "ht_2": mp["2"], "ht_btts_yes": mp["btts_yes"],
            "ht_over_0.5": mp["over_0.5"], "ht_over_1.5": mp["over_1.5"], "ht_over_2.5": mp["over_2.5"]}


def analyze_market(odds_1x2, odds_ou25=None, rho: float = DEFAULT_RHO) -> dict:
    fit = fit_from_market(odds_1x2, odds_ou25, rho)
    m = score_matrix(fit["lh"], fit["la"], rho)
    return {"fit": fit, "matrix": m, "markets": market_probs(m), "half": half_markets(fit["lh"], fit["la"]),
            "top_scores": top_scores(m)}
