import json
from pathlib import Path

import numpy as np
import pytest

from app.models.bulletin_model import HTFT_ORDER, analyze_bulletin_match
from app.models.market_poisson import market_probs, score_matrix

MARGIN = 1.175


def synth_odds(lh=1.5, la=1.1, hl=0.65, ha=0.47, full=True):
    """Bilinen Poisson'dan, sabit marjlı bülten oranları üretir."""
    m = score_matrix(lh, la, -0.05)
    mp = market_probs(m)
    n = m.shape[0]
    i, j = np.indices((n, n))
    tot = i + j
    od = lambda p: round(1 / (p * MARGIN), 2)  # noqa: E731
    o = {"ms1": od(mp["1"]), "ms0": od(mp["X"]), "ms2": od(mp["2"])}
    if not full:
        return o
    o.update(ou25_ust=od(mp["over_2.5"]), ou25_alt=od(1 - mp["over_2.5"]), ou35_ust=od(mp["over_3.5"]), ou35_alt=od(1 - mp["over_3.5"]),
             kg_var=od(mp["btts_yes"]), kg_yok=od(1 - mp["btts_yes"]))
    for k, (lo, hi) in {"tg_01": (0, 1), "tg_23": (2, 3), "tg_45": (4, 5), "tg_6p": (6, 99)}.items():
        o[k] = od(float(m[(tot >= lo) & (tot <= hi)].sum()))
    mh = score_matrix(hl, ha)
    hp = market_probs(mh)
    o.update(ht1=od(hp["1"]), ht0=od(hp["X"]), ht2=od(hp["2"]), ht15_ust=od(hp["over_1.5"]), ht15_alt=od(1 - hp["over_1.5"]))
    return o


def test_recovers_known_parameters():
    r = analyze_bulletin_match(synth_odds())
    assert r["lh"] == pytest.approx(1.5, abs=0.05) and r["la"] == pytest.approx(1.1, abs=0.05)
    assert r["rmse"] < 0.01 and r["n_targets"] == 10
    assert r["ht_lh"] == pytest.approx(0.65, abs=0.06) and "oranlardan" in r["ht_source"]
    assert sum(r["htft"].values()) == pytest.approx(1) and set(r["htft"]) == set(HTFT_ORDER)
    groups = {x["group"] for x in r["markets"]}
    assert {"Maç sonucu", "Alt/Üst", "Karşılıklı gol", "Toplam gol", "İlk yarı"} <= groups
    # bahisçi kendi modeline göre fiyatlıyorsa EV ≈ −marj
    ms1 = next(x for x in r["markets"] if x["label"] == "MS 1")
    assert ms1["ev"] == pytest.approx(1 / MARGIN - 1, abs=0.03)


def test_only_1x2_still_works_and_flags_approx_half():
    r = analyze_bulletin_match(synth_odds(full=False))
    assert r["n_targets"] == 3 and "yaklaşık" in r["ht_source"]
    assert [x["group"] for x in r["markets"]] == ["Maç sonucu"] * 3
    assert r["lh"] > r["la"]


def test_partial_markets():
    o = synth_odds()
    for k in ("tg_01", "tg_23", "tg_45", "tg_6p", "ht15_ust", "ht15_alt"):
        o.pop(k)
    r = analyze_bulletin_match(o)
    assert r["n_targets"] == 6 and "1,5" not in r["ht_source"]


PDF = Path(__file__).resolve().parents[2] / "data" / "raw" / "bulten-2026-10-16.pdf"


@pytest.mark.skipif(not PDF.exists(), reason="Örnek bülten PDF'i yok (data/raw, Git'e girmez)")
def test_real_pdf_parses_with_consistent_margins():
    from app.providers.iddaa_pdf import parse_pdf

    r = parse_pdf(PDF, 2026)
    assert len(r["matches"]) > 800 and r["days"] == ["2026-10-16", "2026-10-17", "2026-10-18", "2026-10-19"]
    assert all(m["time"] for m in r["matches"]) and all(m["date"] for m in r["matches"])
    margins = [sum(1 / m["odds"][k] for k in ("ms1", "ms0", "ms2")) for m in r["matches"] if not m.get("est")]  # kestirilen oranlar hariç
    assert 1.10 < min(margins) and max(margins) < 1.25  # sütun kayması olsaydı marj bozulurdu
    kg = [sum(1 / m["odds"][k] for k in ("kg_var", "kg_yok")) for m in r["matches"] if "kg_var" in m["odds"] and "kg_yok" in m["odds"]]
    assert kg and 1.10 < min(kg) and max(kg) < 1.25
    first = r["matches"][0]
    assert (first["home"], first["away"], first["time"]) == ("PSİM YOGYAKARTA", "PSM MAKASSAR", "11:30")
    assert first["odds"]["ms1"] == 1.98 and first["odds"]["kg_var"] == 1.57


def test_league_filter_keeps_only_archive_leagues():
    from app.providers.iddaa_leagues import ARCHIVE_DIVISIONS, IDDAA_TO_ARCHIVE, filter_archive_leagues

    assert set(IDDAA_TO_ARCHIVE.values()) <= set(ARCHIVE_DIVISIONS)
    ms = [{"league": "İTSA"}, {"league": "ENDO"}, {"league": "İSPP"}, {"league": "SÜPL"}, {"league": "ENDO"}]
    kept, excl = filter_archive_leagues(ms)
    assert [m["division"] for m in kept] == ["I1", "T1"]
    assert excl == {"ENDO": 2, "İSPP": 1}
