from app.markets import ALL_COLUMNS, derive_outcomes


def test_two_one_with_ht_one_nil():
    o = derive_outcomes(2, 1, 1, 0, corners_h=6, corners_a=5, yellow_h=2, yellow_a=1, red_h=0, red_a=0)
    assert (o["ft_1"], o["ft_x"], o["ft_2"]) == (1, 0, 0)
    assert (o["dc_1x"], o["dc_12"], o["dc_x2"]) == (1, 1, 0)
    assert o["btts_yes"] == 1 and o["ft_total"] == 3 and o["ft_over_2_5"] == 1 and o["ft_over_3_5"] == 0
    assert o["ft_over_1_5"] == 1 and o["odd_total"] == 1
    # İY 1-0: 0,5 üst, 1,5 alt, ev önde, İY karşılıklı gol yok
    assert (o["ht_over_0_5"], o["ht_over_1_5"], o["ht_1"], o["ht_btts_yes"]) == (1, 0, 1, 0)
    assert o["htft"] == "1/1" and o["exact_score"] == "2-1" and o["ht_score"] == "1-0"
    # 2. yarı 1-1
    assert (o["sh_home"], o["sh_away"], o["sh_x"], o["sh_btts_yes"]) == (1, 1, 1, 1)
    assert o["more_goals_2h"] == 1 and o["more_goals_1h"] == 0
    assert o["corners_total"] == 11 and o["corners_over_10_5"] == 1 and o["corners_over_11_5"] == 0
    assert o["cards_total"] == 3 and o["cards_over_2_5"] == 1 and o["cards_over_3_5"] == 0
    assert o["home_win_to_nil"] == 0 and o["away_clean_sheet"] == 0 and o["home_clean_sheet"] == 0


def test_goalless_draw_and_comeback_htft():
    o = derive_outcomes(0, 0, 0, 0)
    assert o["ft_x"] == 1 and o["ft_over_0_5"] == 0 and o["btts_yes"] == 0 and o["home_clean_sheet"] == 1
    assert o["htft"] == "X/X" and o["equal_goals_halves"] == 1
    o = derive_outcomes(1, 2, 1, 0)
    assert o["htft"] == "1/2" and o["away_win_both_halves"] == 0 and o["sh_2"] == 1


def test_missing_inputs_stay_none():
    o = derive_outcomes(2, 1)  # İY ve istatistik yok
    assert o["ft_1"] == 1 and o["ht_1"] is None and o["htft"] is None and o["sh_total"] is None
    assert o["corners_total"] is None and o["cards_over_3_5"] is None
    o = derive_outcomes(None, None, 1, 0)
    assert o["ft_1"] is None and o["ht_1"] == 1 and o["htft"] is None
    assert set(o) == set(ALL_COLUMNS)


def test_exactly_one_of_each_exclusive_set():
    for fh in range(5):
        for fa in range(5):
            o = derive_outcomes(fh, fa, min(fh, 1), 0 if fa == 0 else min(fa, 1))
            assert o["ft_1"] + o["ft_x"] + o["ft_2"] == 1
            assert o["ht_1"] + o["ht_x"] + o["ht_2"] == 1
            assert o["more_goals_1h"] + o["more_goals_2h"] + o["equal_goals_halves"] == 1
