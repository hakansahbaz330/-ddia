"""Skor ve istatistiklerden gerçekleşen pazar sonuçlarını türetir (tek doğruluk kaynağı).

Girdi eksikse ilgili sonuç None olur (0'a çevrilmez). Üst/alt çizgileri yarım olduğundan "alt" = 1 - "üst".
Değerler 0/1 tam sayıdır; sayısal özetler (toplam gol vb.) tam sayıdır.
"""
from __future__ import annotations

FT_LINES = (0.5, 1.5, 2.5, 3.5, 4.5, 5.5)
HT_LINES = (0.5, 1.5, 2.5)
SH_LINES = (0.5, 1.5, 2.5)
TEAM_LINES = (0.5, 1.5, 2.5)
CORNER_LINES = (7.5, 8.5, 9.5, 10.5, 11.5, 12.5)
CARD_LINES = (2.5, 3.5, 4.5, 5.5, 6.5)  # sarı + kırmızı kart sayısı (kart puanı değil)


def _k(x: float) -> str:
    return str(x).replace(".", "_")


def _ints() -> list[str]:
    cols = ["ft_total", "ft_diff", "ht_total", "sh_home", "sh_away", "sh_total", "corners_total", "cards_total"]
    cols += [f"ft_over_{_k(x)}" for x in FT_LINES]
    cols += [f"ht_over_{_k(x)}" for x in HT_LINES]
    cols += [f"sh_over_{_k(x)}" for x in SH_LINES]
    cols += [f"home_over_{_k(x)}" for x in TEAM_LINES] + [f"away_over_{_k(x)}" for x in TEAM_LINES]
    cols += [f"corners_over_{_k(x)}" for x in CORNER_LINES] + [f"cards_over_{_k(x)}" for x in CARD_LINES]
    cols += ["ft_1", "ft_x", "ft_2", "dc_1x", "dc_12", "dc_x2", "ht_1", "ht_x", "ht_2", "sh_1", "sh_x", "sh_2",
             "btts_yes", "ht_btts_yes", "sh_btts_yes", "odd_total",
             "home_clean_sheet", "away_clean_sheet", "home_win_to_nil", "away_win_to_nil",
             "home_win_both_halves", "away_win_both_halves", "more_goals_1h", "more_goals_2h", "equal_goals_halves",
             "home_scores_both_halves", "away_scores_both_halves"]
    return cols


INT_COLUMNS: list[str] = _ints()
TEXT_COLUMNS = ["htft", "exact_score", "ht_score"]  # htft: "1/1", "X/2" ...; exact_score: "2-1"
ALL_COLUMNS = INT_COLUMNS + TEXT_COLUMNS


def _b(v: bool) -> int:
    return 1 if v else 0


def derive_outcomes(ft_h, ft_a, ht_h=None, ht_a=None, corners_h=None, corners_a=None,
                    yellow_h=None, yellow_a=None, red_h=None, red_a=None) -> dict:
    o: dict = {c: None for c in ALL_COLUMNS}
    if ft_h is not None and ft_a is not None:
        t = ft_h + ft_a
        o.update(ft_total=t, ft_diff=ft_h - ft_a, exact_score=f"{ft_h}-{ft_a}",
                 ft_1=_b(ft_h > ft_a), ft_x=_b(ft_h == ft_a), ft_2=_b(ft_h < ft_a),
                 dc_1x=_b(ft_h >= ft_a), dc_12=_b(ft_h != ft_a), dc_x2=_b(ft_h <= ft_a),
                 btts_yes=_b(ft_h > 0 and ft_a > 0), odd_total=_b(t % 2 == 1),
                 home_clean_sheet=_b(ft_a == 0), away_clean_sheet=_b(ft_h == 0),
                 home_win_to_nil=_b(ft_h > ft_a and ft_a == 0), away_win_to_nil=_b(ft_a > ft_h and ft_h == 0))
        for x in FT_LINES:
            o[f"ft_over_{_k(x)}"] = _b(t > x)
        for x in TEAM_LINES:
            o[f"home_over_{_k(x)}"] = _b(ft_h > x)
            o[f"away_over_{_k(x)}"] = _b(ft_a > x)
    if ht_h is not None and ht_a is not None:
        o.update(ht_total=ht_h + ht_a, ht_score=f"{ht_h}-{ht_a}",
                 ht_1=_b(ht_h > ht_a), ht_x=_b(ht_h == ht_a), ht_2=_b(ht_h < ht_a),
                 ht_btts_yes=_b(ht_h > 0 and ht_a > 0))
        for x in HT_LINES:
            o[f"ht_over_{_k(x)}"] = _b(ht_h + ht_a > x)
    if None not in (ft_h, ft_a, ht_h, ht_a):
        sh, sa = ft_h - ht_h, ft_a - ht_a
        sym = lambda a, b: "1" if a > b else "2" if a < b else "X"  # noqa: E731
        o.update(sh_home=sh, sh_away=sa, sh_total=sh + sa, htft=f"{sym(ht_h, ht_a)}/{sym(ft_h, ft_a)}",
                 sh_1=_b(sh > sa), sh_x=_b(sh == sa), sh_2=_b(sh < sa), sh_btts_yes=_b(sh > 0 and sa > 0),
                 more_goals_1h=_b(ht_h + ht_a > sh + sa), more_goals_2h=_b(sh + sa > ht_h + ht_a),
                 equal_goals_halves=_b(sh + sa == ht_h + ht_a),
                 home_win_both_halves=_b(ht_h > ht_a and sh > sa), away_win_both_halves=_b(ht_a > ht_h and sa > sh),
                 home_scores_both_halves=_b(ht_h > 0 and sh > 0), away_scores_both_halves=_b(ht_a > 0 and sa > 0))
        for x in SH_LINES:
            o[f"sh_over_{_k(x)}"] = _b(sh + sa > x)
    if corners_h is not None and corners_a is not None:
        o["corners_total"] = corners_h + corners_a
        for x in CORNER_LINES:
            o[f"corners_over_{_k(x)}"] = _b(corners_h + corners_a > x)
    if None not in (yellow_h, yellow_a, red_h, red_a):
        c = yellow_h + yellow_a + red_h + red_a
        o["cards_total"] = c
        for x in CARD_LINES:
            o[f"cards_over_{_k(x)}"] = _b(c > x)
    return o
