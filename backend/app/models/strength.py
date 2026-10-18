"""Arşivden takım gücü: zamanla azalan ağırlıklı, düzenlenmiş (ridge) Poisson regresyonu.

log λ_ev  = lig_tabanı + ev_avantajı + atak[ev] − savunma[dep]
log λ_dep = lig_tabanı + atak[dep] − savunma[ev]
Yalnızca `before` tarihinden önceki maçlarla eğitilir (geleceği kullanmaz). Oran girdisi kullanmaz:
piyasadan bağımsız bir model olarak karşılaştırma ve birleşim içindir.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.linear_model import PoissonRegressor

HALF_LIFE_DAYS = 365.0
ALPHA = 1.0  # ridge gücü (doğrulamayla ayarlanabilir)


@dataclass
class StrengthModel:
    teams: list[str]  # "Ülke|Takım"
    leagues: list[str]
    att: dict[str, float]
    dfn: dict[str, float]
    league_base: dict[str, float]
    home_adv: float
    before: str

    def lambdas(self, home_key: str, away_key: str, league: str) -> tuple[float, float] | None:
        if home_key not in self.att or away_key not in self.att:
            return None
        base = self.league_base.get(league, float(np.mean(list(self.league_base.values()))))
        lh = np.exp(base + self.home_adv + self.att[home_key] - self.dfn[away_key])
        la = np.exp(base + self.att[away_key] - self.dfn[home_key])
        return float(lh), float(la)


def fit_strength(df: pd.DataFrame, before: str | None = None, half_life: float = HALF_LIFE_DAYS, alpha: float = ALPHA) -> StrengthModel:
    d = df[["date", "division", "country", "home", "away", "fth", "fta"]].dropna()
    if before:
        d = d[d.date < pd.Timestamp(before)]
    ref = d.date.max()
    w = 0.5 ** ((ref - d.date).dt.days.to_numpy() / half_life)
    hk = (d.country + "|" + d.home).to_numpy()
    ak = (d.country + "|" + d.away).to_numpy()
    teams = sorted(set(hk) | set(ak))
    leagues = sorted(d.division.unique())
    ti = {t: i for i, t in enumerate(teams)}
    li = {l: i for i, l in enumerate(leagues)}
    n, T, L = len(d), len(teams), len(leagues)
    rows_h, rows_a = np.arange(n), np.arange(n)
    # Her maç iki gözlem: ev golü ve deplasman golü
    def block(att_idx, def_idx, home_flag):
        a = sp.csr_matrix((np.ones(n), (rows_h, att_idx)), shape=(n, T))
        df_ = sp.csr_matrix((-np.ones(n), (rows_h, def_idx)), shape=(n, T))
        lg = sp.csr_matrix((np.ones(n), (rows_h, d.division.map(li).to_numpy())), shape=(n, L))
        hf = sp.csr_matrix(np.full((n, 1), float(home_flag)))
        return sp.hstack([a, df_, lg, hf]).tocsr()
    X = sp.vstack([block(np.array([ti[k] for k in hk]), np.array([ti[k] for k in ak]), 1),
                   block(np.array([ti[k] for k in ak]), np.array([ti[k] for k in hk]), 0)]).tocsr()
    y = np.concatenate([d.fth.to_numpy(float), d.fta.to_numpy(float)])
    reg = PoissonRegressor(alpha=alpha / (2 * n), fit_intercept=False, max_iter=300)
    reg.fit(X, y, sample_weight=np.concatenate([w, w]))
    c = reg.coef_
    return StrengthModel(teams, leagues, dict(zip(teams, c[:T], strict=True)), dict(zip(teams, c[T:2 * T], strict=True)),
                         dict(zip(leagues, c[2 * T:2 * T + L], strict=True)), float(c[-1]), before or str(ref.date()))
