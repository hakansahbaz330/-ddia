"""Piyasa-Poisson, güç modeli ve birleşimin gerçekçi karşılaştırması.

Eğitim: ≤2023-24 | Doğrulama (birleşim ağırlığı seçimi): 2024-25 | Bağımsız test: 2025-26 (ağırlık orada ayarlanmaz).
Güç modeli her sezon başında, o tarihe kadarki maçlarla eğitilir (geleceği görmez).
Çıktı: scripts/model_report.json
Çalıştırma: cd backend && PYTHONPATH=. python scripts/evaluate_models.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from app.analysis.features import load_feature_frame
from app.db import session_scope
from app.models.market_poisson import devig, fit_from_market, market_probs, score_matrix
from app.models.strength import fit_strength

OUT = Path(__file__).parent / "model_report.json"


def probs_market(r):
    return fit_from_market((r.oh, r.od, r.oa), (r.oo, r.ou) if pd.notna(r.oo) and pd.notna(r.ou) else None)


def one(lh, la):
    mp = market_probs(score_matrix(lh, la))
    return np.array([mp["1"], mp["X"], mp["2"]]), mp["over_2.5"], mp["btts_yes"]


def metrics(rows):
    P = np.array([r["p"] for r in rows]); y = np.array([r["y"] for r in rows])
    ll = -np.mean(np.log(np.clip(P[np.arange(len(y)), y], 1e-9, 1)))
    brier = np.mean(np.sum((P - np.eye(3)[y]) ** 2, axis=1))
    cum = np.cumsum(P, axis=1)[:, :2]; ycum = np.cumsum(np.eye(3)[y], axis=1)[:, :2]
    rps = np.mean(np.sum((cum - ycum) ** 2, axis=1) / 2)
    return {"n": len(y), "log_loss": float(ll), "brier": float(brier), "rps": float(rps)}


def main():
    with session_scope() as s:
        df = load_feature_frame(s)
    df = df.dropna(subset=["oh", "od", "oa"])
    seasons = {"val": "2024-2025", "test": "2025-2026"}
    res = {}
    for name, season in seasons.items():
        sub = df[df.season == season].sample(frac=1, random_state=1).head(3000).sort_values("date")  # hız için örnek
        start = sub.date.min()
        sm = fit_strength(df, before=str(start.date()))
        rows = {"market": [], "strength": [], "uniform": []}
        keep = []
        for r in sub.itertuples():
            lam = sm.lambdas(f"{r.country}|{r.home}", f"{r.country}|{r.away}", r.division)
            if lam is None:
                continue
            y = 0 if r.fth > r.fta else 1 if r.fth == r.fta else 2
            fm = probs_market(r)
            pm, _, _ = one(fm["lh"], fm["la"]); ps, _, _ = one(*lam)
            rows["market"].append({"p": pm, "y": y}); rows["strength"].append({"p": ps, "y": y})
            rows["uniform"].append({"p": np.array([0.4325, 0.2621, 0.3053]), "y": y})
            keep.append((pm, ps, y))
        res[name] = {"season": season, **{k: metrics(v) for k, v in rows.items()}}
        res[name]["_keep"] = keep
    # birleşim ağırlığı yalnızca doğrulamada seçilir
    def blend_ll(keep, w):
        P = np.array([w * a + (1 - w) * b for a, b, _ in keep]); y = np.array([k[2] for k in keep])
        return -np.mean(np.log(np.clip(P[np.arange(len(y)), y], 1e-9, 1)))
    grid = np.linspace(0, 1, 21)
    best_w = float(grid[int(np.argmin([blend_ll(res["val"]["_keep"], w) for w in grid]))])
    test_blend = metrics([{"p": best_w * a + (1 - best_w) * b, "y": y} for a, b, y in res["test"]["_keep"]])
    for v in res.values():
        v.pop("_keep")
    res["blend"] = {"market_weight_chosen_on_validation": best_w, "test": test_blend}
    OUT.write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    sys.exit(main())
