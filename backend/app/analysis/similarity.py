"""Geçmiş maçlarda benzer oran analizi.

Yöntem (başlangıç; ağırlıklar kanıtlanmış değil, doğrulama ile ayarlanacak):
  1. Oranlar marj düzeltilir (orantılı: p_i = (1/o_i)/Σ(1/o_j)).
  2. Özellikler: p(1), p(X), p(2) ve - iki tarafta da varsa - p(2,5 üst).
  3. Uzaklık d = sqrt(Σ w_i (q_i - m_i)^2 / Σ w_i);  benzerlik = 100 * exp(-d / tau).
Bu bir tahmin değil, geçmişte benzer fiyatlanan maçların gerçekleşme sıklığıdır.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.markets import CARD_LINES, CORNER_LINES, FT_LINES, HT_LINES, _k

DEFAULT_WEIGHTS = {"p1": 1.0, "px": 1.0, "p2": 1.0, "pover": 1.0}
DEFAULT_TAU = 0.05
TOP_N_CHOICES = (10, 25, 50, 100)


def devig(odds: list[float]) -> list[float]:
    inv = [1.0 / o for o in odds]
    t = sum(inv)
    return [x / t for x in inv]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


@dataclass
class Query:
    odds_1x2: tuple[float, float, float]
    odds_ou25: tuple[float, float] | None = None  # (üst, alt)


@dataclass
class Scope:
    kind: str = "all"  # all | league | team
    divisions: list[str] = field(default_factory=list)
    team: str | None = None
    venue: str = "any"  # any | home | away  (yalnız team için)
    opponent: str | None = None
    last_seasons: int | None = None  # 3, 5 veya None = hepsi
    exclude_match_ids: list[int] = field(default_factory=list)
    before_date: str | None = None  # geriye dönük testte: yalnız bu tarihten önceki maçlar


def apply_scope(df: pd.DataFrame, sc: Scope) -> pd.DataFrame:
    m = pd.Series(True, index=df.index)
    if sc.divisions:
        m &= df.division.isin(sc.divisions)
    if sc.kind == "league" and not sc.divisions:
        raise ValueError("Lig bazlı arama için en az bir lig seçin.")
    if sc.kind == "team":
        if not sc.team:
            raise ValueError("Takım bazlı arama için takım seçin.")
        h, a = df.home == sc.team, df.away == sc.team
        m &= h if sc.venue == "home" else a if sc.venue == "away" else (h | a)
        if sc.opponent:
            m &= ((df.home == sc.opponent) | (df.away == sc.opponent))
    if sc.last_seasons:
        keep = sorted(df.season.unique())[-sc.last_seasons:]
        m &= df.season.isin(keep)
    if sc.before_date:
        m &= df.date < pd.Timestamp(sc.before_date)
    if sc.exclude_match_ids:
        m &= ~df.match_id.isin(sc.exclude_match_ids)
    return df[m]


def rank_similar(df: pd.DataFrame, q: Query, weights: dict | None = None, tau: float = DEFAULT_TAU) -> pd.DataFrame:
    """Oranı olan maçları benzerlik puanına göre azalan sıralar. 'sim' (0-100) ve 'dist' sütunları eklenir."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    d = df.dropna(subset=["oh", "od", "oa"])
    d = d[(d.oh > 1) & (d.od > 1) & (d.oa > 1)]
    inv = 1 / d[["oh", "od", "oa"]].to_numpy()
    P = inv / inv.sum(axis=1, keepdims=True)
    qp = np.array(devig(list(q.odds_1x2)))
    ws = np.array([w["p1"], w["px"], w["p2"]])
    sq = ((P - qp) ** 2) * ws
    wsum = np.full(len(d), ws.sum())
    if q.odds_ou25:
        has = d[["oo", "ou"]].notna().all(axis=1).to_numpy()
        o, u = d["oo"].to_numpy(dtype=float), d["ou"].to_numpy(dtype=float)
        with np.errstate(invalid="ignore", divide="ignore"):
            po = (1 / o) / (1 / o + 1 / u)
        qo = devig([q.odds_ou25[0], q.odds_ou25[1]])[0]
        sq = np.column_stack([sq.sum(axis=1), np.where(has, w["pover"] * (po - qo) ** 2, 0.0)]).sum(axis=1)
        wsum = wsum + np.where(has, w["pover"], 0.0)
    else:
        sq = sq.sum(axis=1)
    dist = np.sqrt(sq / wsum)
    out = d.assign(dist=dist, sim=100 * np.exp(-dist / tau))
    return out.sort_values(["dist", "match_id"], ascending=[True, False])


def _rate(sub: pd.DataFrame, col: str) -> dict:
    s = sub[col].dropna()
    n = int(len(s))
    k = int(s.sum())
    lo, hi = wilson(k, n)
    return {"rate": (k / n) if n else None, "n": n, "ci_low": lo, "ci_high": hi}


MARKET_GROUPS = {
    "Maç sonucu": [("ft_1", "1"), ("ft_x", "X"), ("ft_2", "2")],
    "Çifte şans": [("dc_1x", "1X"), ("dc_12", "12"), ("dc_x2", "X2")],
    "Gol üst (maç)": [(f"ft_over_{_k(x)}", f"{x} üst") for x in FT_LINES[:5]],
    "Karşılıklı gol": [("btts_yes", "KG var")],
    "İlk yarı sonucu": [("ht_1", "İY 1"), ("ht_x", "İY X"), ("ht_2", "İY 2")],
    "İlk yarı gol üst": [(f"ht_over_{_k(x)}", f"İY {x} üst") for x in HT_LINES],
    "İlk yarı KG": [("ht_btts_yes", "İY KG var")],
    "Korner üst": [(f"corners_over_{_k(x)}", f"Korner {x} üst") for x in CORNER_LINES[1:5]],
    "Kart üst": [(f"cards_over_{_k(x)}", f"Kart {x} üst") for x in CARD_LINES[:4]],
}


def summarize(sub: pd.DataFrame) -> dict:
    """Gerçekleşme sıklıkları (Wilson %95 aralığı), İY/MS ve skor dağılımları."""
    res = {"n": int(len(sub)), "markets": {}}
    for g, items in MARKET_GROUPS.items():
        res["markets"][g] = {label: _rate(sub, col) for col, label in items}
    # "alt" = 1 - üst; aralık da simetrik ters çevrilir
    for g in ("Gol üst (maç)", "İlk yarı gol üst", "Korner üst", "Kart üst"):
        for label, r in list(res["markets"][g].items()):
            alt = label.replace("üst", "alt")
            res["markets"][g][alt] = {"rate": None if r["rate"] is None else 1 - r["rate"], "n": r["n"],
                                      "ci_low": 1 - r["ci_high"], "ci_high": 1 - r["ci_low"]}
    htft = sub["htft"].dropna().value_counts()
    res["htft"] = {k: {"count": int(v), "rate": v / htft.sum()} for k, v in htft.items()}
    sc = sub["exact_score"].value_counts().head(8)
    res["top_scores"] = [{"score": k, "count": int(v), "rate": v / max(len(sub), 1)} for k, v in sc.items()]
    if len(sub):
        res["avg_goals"] = float((sub.fth + sub.fta).mean())
    return res


def select_radius(ranked: pd.DataFrame, eps: float, min_n: int | None = None, max_eps: float = 0.06) -> tuple[pd.DataFrame, float]:
    """Uzaklığı eps içindeki TÜM maçlar. min_n verilmişse, o kadar maç çıkana (veya max_eps'e) kadar aralık 1,25 katlanarak genişler."""
    e = eps
    n = int((ranked.dist <= e).sum())
    while min_n and n < min_n and e < max_eps - 1e-12:
        e = min(max_eps, e * 1.25)
        n = int((ranked.dist <= e).sum())
    return ranked[ranked.dist <= e], e


def analyze(df_all: pd.DataFrame, q: Query, scope: Scope, top_n: int = 50, min_sim: float = 0.0,
            min_sample: int = 30, weights: dict | None = None, tau: float = DEFAULT_TAU, list_limit: int = 100,
            max_dist: float | None = None, min_n: int | None = None, max_eps: float = 0.06) -> dict:
    """top_n: en benzer N maç. max_dist verilirse N sınırı yoktur: uzaklığı max_dist içindeki bütün maçlar analiz edilir
    (min_n ile aralık gerekirse otomatik genişler)."""
    scoped = apply_scope(df_all, scope)
    ranked = rank_similar(scoped, q, weights, tau)
    radius = None
    if max_dist is not None:
        top, eff = select_radius(ranked, max_dist, min_n, max_eps)
        radius = {"requested": max_dist, "effective": eff, "widened": eff > max_dist + 1e-12, "n": int(len(top))}
    else:
        ranked = ranked[ranked.sim >= min_sim]
        top = ranked.head(top_n)
    warnings = []
    if len(top) < min_sample:
        warnings.append(f"Örneklem küçük ({len(top)} < {min_sample}); yüzdeler güvenilir değil, aralıklar geniş.")
    if len(scoped) and len(ranked) < len(scoped) * 0.5:
        warnings.append("Kapsamdaki maçların yarısından fazlasında 1X2 oranı yok; bu maçlar dışarıda kaldı.")
    if len(top) and top.sim.min() < 50:
        warnings.append(f"En düşük benzerlik {top.sim.min():.0f}/100; seçilen N için eşleşmeler yakın değil.")
    cols = ["match_id", "date", "league", "season", "home", "away", "fth", "fta", "hth", "hta", "oh", "od", "oa", "sim", "src_1x2"]
    lst = top.sort_values(["dist", "match_id"], ascending=[True, False]).head(list_limit)[cols].copy()
    lst["date"] = lst["date"].dt.strftime("%Y-%m-%d")
    if radius and radius["widened"]:
        warnings.append(f"Benzerlik aralığı {radius['requested']:.3f} iken yalnızca az maç vardı; aralık otomatik {radius['effective']:.3f}'e genişletildi.")
    return {
        "radius": radius,
        "scope_matches": int(len(scoped)), "with_odds": int(len(ranked)), "used": int(len(top)),
        "similarity": {"min": float(top.sim.min()) if len(top) else None, "mean": float(top.sim.mean()) if len(top) else None},
        "summary": summarize(top), "matches": lst.to_dict("records"), "warnings": warnings,
        "method": {"features": ["p1", "px", "p2"] + (["pover"] if q.odds_ou25 else []), "tau": tau,
                   "weights": {**DEFAULT_WEIGHTS, **(weights or {})},
                   "note": "Başlangıç ağırlıkları doğrulanmadı. Sonuç tahmin değil, geçmiş sıklıktır."},
    }
