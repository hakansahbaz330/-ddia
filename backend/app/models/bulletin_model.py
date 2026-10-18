"""Bülten oranlarından çok pazarlı Poisson modeli.

Tam maç: 1X2, 2,5/3,5 üst-alt, KG ve toplam gol aralıkları (olanlar) marjdan arındırılıp (orantılı) tek bir (λ_ev, λ_dep)
çiftine en küçük kareler ile uydurulur. İlk yarı: İY 1/0/2 ve İY 1,5 üst-alt varsa ayrı (λ_İY) çiftine uydurulur, yoksa
sabit pay (HT_SHARE) kullanılır. İY/MS ortak dağılımı, ilk yarı ve ikinci yarı (λ − λ_İY) bağımsız Poisson varsayımıyla bulunur.
Her pazar için model olasılığı ile bahisçi oranı yan yana verilir. Model, bahisçinin kendi oranlarından türediği için bu karşılaştırma
bir avantaj kanıtı değildir; tutarsızlıkları ve marjı gösterir.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

from app.models.market_poisson import DEFAULT_RHO, HT_SHARE, MAX_GOALS, devig, market_probs, score_matrix, top_scores

TG_BINS = {"tg_01": (0, 1), "tg_23": (2, 3), "tg_45": (4, 5), "tg_6p": (6, 99)}
HTFT_ORDER = ["11", "10", "12", "01", "00", "02", "21", "20", "22"]  # İY/MS: 1=ev, 0=beraberlik, 2=deplasman


def _pair(odds, a, b):
    return devig([odds[a], odds[b]]) if a in odds and b in odds else None


def full_targets(o: dict) -> list[tuple[str, float]]:
    """Tam maç hedefleri: (ad, marjdan arındırılmış olasılık). Pazarın tüm seçenekleri yoksa atlanır."""
    t: list[tuple[str, float]] = []
    p = devig([o["ms1"], o["ms0"], o["ms2"]])
    t += [("ms1", p[0]), ("ms0", p[1]), ("ms2", p[2])]
    q = _pair(o, "ou25_ust", "ou25_alt")
    if q is not None:
        t.append(("over25", q[0]))
    q = _pair(o, "ou35_ust", "ou35_alt")
    if q is not None:
        t.append(("over35", q[0]))
    q = _pair(o, "kg_var", "kg_yok")
    if q is not None:
        t.append(("btts", q[0]))
    if all(k in o for k in TG_BINS):
        for (k, pk) in zip(TG_BINS, devig([o[k] for k in TG_BINS]), strict=True):
            t.append((k, pk))
    return t


def _model_value(name: str, m: np.ndarray, mp: dict) -> float:
    if name == "ms1":
        return mp["1"]
    if name == "ms0":
        return mp["X"]
    if name == "ms2":
        return mp["2"]
    if name == "over25":
        return mp["over_2.5"]
    if name == "over35":
        return mp["over_3.5"]
    if name == "btts":
        return mp["btts_yes"]
    lo, hi = TG_BINS[name]
    n = m.shape[0]
    i, j = np.indices((n, n))
    return float(m[(i + j >= lo) & (i + j <= hi)].sum())


def _fit(targets, rho, valuef, starts=((1.4, 1.1), (2.0, 0.8), (0.9, 1.6))):
    def loss(x):
        m = score_matrix(float(np.exp(x[0])), float(np.exp(x[1])), rho)
        mp = market_probs(m)
        return sum((valuef(n, m, mp) - p) ** 2 for n, p in targets)

    best = min((minimize(loss, np.log(s), method="Nelder-Mead", options={"xatol": 1e-6, "fatol": 1e-13, "maxiter": 1000}) for s in starts),
               key=lambda r: r.fun)
    return float(np.exp(best.x[0])), float(np.exp(best.x[1])), float(best.fun)


def _ht_value(name, m, mp):
    return {"ht1": mp["1"], "ht0": mp["X"], "ht2": mp["2"], "ht15": mp["over_1.5"]}[name]


def htft_matrix(lh_ht, la_ht, lh_2, la_2) -> dict:
    """Dokuz İY/MS sonucunun olasılığı: İY ve 2. yarı skorları bağımsız Poisson."""
    h1, h2 = score_matrix(lh_ht, la_ht), score_matrix(lh_2, la_2)
    n = MAX_GOALS + 1
    out = {k: 0.0 for k in HTFT_ORDER}
    sym = lambda a, b: "1" if a > b else "2" if a < b else "0"  # noqa: E731
    for a in range(n):
        for b in range(n):
            p1 = h1[a, b]
            if p1 < 1e-9:
                continue
            s1 = sym(a, b)
            # 2. yarı gol farkı dağılımı ile bütün 2. yarı sonuçlarını topla
            for c in range(n):
                for d in range(n):
                    out[s1 + sym(a + c, b + d)] += p1 * h2[c, d]
    tot = sum(out.values())
    return {k: v / tot for k, v in out.items()}


def analyze_bulletin_match(o: dict, rho: float = DEFAULT_RHO) -> dict:
    targets = full_targets(o)
    lh, la, sse = _fit(targets, rho, _model_value)
    m = score_matrix(lh, la, rho)
    mp = market_probs(m)
    n = m.shape[0]
    i, j = np.indices((n, n))
    tot = i + j
    resid = {nme: _model_value(nme, m, mp) - p for nme, p in targets}
    res = {"lh": lh, "la": la, "n_targets": len(targets), "rmse": float(np.sqrt(sse / len(targets))), "residuals": resid,
           "markets_used": [nme for nme, _ in targets], "top_scores": top_scores(m, 10), "matrix": m}
    # --- ilk yarı ---
    ht_t = []
    if all(k in o for k in ("ht1", "ht0", "ht2")):
        p = devig([o["ht1"], o["ht0"], o["ht2"]])
        ht_t += [("ht1", p[0]), ("ht0", p[1]), ("ht2", p[2])]
    q = _pair(o, "ht15_ust", "ht15_alt")
    if q is not None:
        ht_t.append(("ht15", q[0]))
    if len(ht_t) >= 3:
        hl, ha, _ = _fit(ht_t, 0.0, _ht_value, starts=((0.6, 0.5), (0.9, 0.4), (0.4, 0.8)))
        res["ht_source"] = "oranlardan (İY 1/0/2" + (" + 1,5 ü/a)" if len(ht_t) == 4 else ")")
    else:
        hl, ha = lh * HT_SHARE, la * HT_SHARE
        res["ht_source"] = f"yaklaşık (gol payı %{HT_SHARE * 100:.1f}; İY oranı yok)"
    hl, ha = min(hl, lh * 0.95), min(ha, la * 0.95)
    res["ht_lh"], res["ht_la"] = hl, ha
    mh = score_matrix(hl, ha)
    res["ht_top_scores"] = top_scores(mh, 6)
    hp = market_probs(mh)
    res["htft"] = htft_matrix(hl, ha, max(lh - hl, 0.05), max(la - ha, 0.05))
    # --- pazar tablosu: bahisçi oranı, kendi pazarında marjdan arındırılmış p, model p ---
    rows = []

    def add(group, label, key, p_model, implied=None):
        if key in o:
            rows.append({"group": group, "label": label, "odds": o[key], "implied": implied, "model": float(p_model),
                         "ev": float(p_model * o[key] - 1)})

    def impl(keys):
        if all(k in o for k in keys):
            return dict(zip(keys, devig([o[k] for k in keys]), strict=True))
        return {}

    d = impl(("ms1", "ms0", "ms2"))
    for k, lab, pm in (("ms1", "MS 1", mp["1"]), ("ms0", "MS 0", mp["X"]), ("ms2", "MS 2", mp["2"])):
        add("Maç sonucu", lab, k, pm, d.get(k))
    for (u, a, line), pm in ((("ou25_ust", "ou25_alt", "2,5"), mp["over_2.5"]), (("ou35_ust", "ou35_alt", "3,5"), mp["over_3.5"])):
        d = impl((u, a))
        add("Alt/Üst", f"{line} Üst", u, pm, d.get(u))
        add("Alt/Üst", f"{line} Alt", a, 1 - pm, d.get(a))
    d = impl(("kg_var", "kg_yok"))
    add("Karşılıklı gol", "KG Var", "kg_var", mp["btts_yes"], d.get("kg_var"))
    add("Karşılıklı gol", "KG Yok", "kg_yok", 1 - mp["btts_yes"], d.get("kg_yok"))
    d = impl(tuple(TG_BINS))
    for k, lab in (("tg_01", "0-1 gol"), ("tg_23", "2-3 gol"), ("tg_45", "4-5 gol"), ("tg_6p", "6+ gol")):
        add("Toplam gol", lab, k, _model_value(k, m, mp), d.get(k))
    d = impl(("ht1", "ht0", "ht2"))
    for k, lab, pm in (("ht1", "İY 1", hp["1"]), ("ht0", "İY 0", hp["X"]), ("ht2", "İY 2", hp["2"])):
        add("İlk yarı", lab, k, pm, d.get(k))
    d = impl(("ht15_ust", "ht15_alt"))
    add("İlk yarı", "İY 1,5 Üst", "ht15_ust", hp["over_1.5"], d.get("ht15_ust"))
    add("İlk yarı", "İY 1,5 Alt", "ht15_alt", 1 - hp["over_1.5"], d.get("ht15_alt"))
    d = impl(tuple(f"htft_{c}" for c in HTFT_ORDER))
    for c in HTFT_ORDER:
        add("İY / MS", f"{c[0]}/{c[1]}", f"htft_{c}", res["htft"][c], d.get(f"htft_{c}"))
    # MS ve Alt/Üst 2,5
    sym_res = {"1": i > j, "0": i == j, "2": i < j}
    for r_, lab in (("1", "1"), ("0", "0"), ("2", "2")):
        add("MS ve 2,5", f"{lab}/Alt", f"msou_{r_}a", float(m[sym_res[r_] & (tot <= 2)].sum()))
        add("MS ve 2,5", f"{lab}/Üst", f"msou_{r_}u", float(m[sym_res[r_] & (tot > 2)].sum()))
    res["markets"] = rows
    res["margins"] = {g: float(sum(1 / r["odds"] for r in rows if r["group"] == g)) for g in {r["group"] for r in rows}}
    return res
