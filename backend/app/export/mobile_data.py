"""Arşivi, tek dosyalı mobil uygulamaya gömülecek sıkıştırılmış sütunlu ikili biçime dışa aktarır.

Biçim (gzip içinde): u32 json_uzunluğu | json (UTF-8, 4 bayta hizalı) | sütunlar (little-endian, art arda).
Sütunlar `COLUMNS` sırasıyla; her biri n elemanlı ve 4 bayta hizalı. Eksik değer: u8 için 255, u16 oranlar için 0.
Oranlar x100 tam sayı (2.03 -> 203). Satırlar (tarih, match_id) sıralıdır.
"""
from __future__ import annotations

import gzip
import json
import struct

import numpy as np
import pandas as pd

COLUMNS = [  # (ad, dtype)
    ("match_id", "<u4"), ("day", "<u2"), ("div", "u1"), ("season", "u1"), ("home", "<u2"), ("away", "<u2"),
    ("fth", "u1"), ("fta", "u1"), ("hth", "u1"), ("hta", "u1"), ("corners", "u1"), ("cards", "u1"),
    ("oh", "<u2"), ("od", "<u2"), ("oa", "<u2"), ("oo", "<u2"), ("ou", "<u2"),
]
EPOCH = pd.Timestamp("2017-01-01")


def _u8(s: pd.Series) -> np.ndarray:
    return s.fillna(255).clip(upper=255).astype("u1").to_numpy()


def _odds(s: pd.Series) -> np.ndarray:
    return (s.fillna(0) * 100).round().astype("<u2").to_numpy()


def export_mobile(df: pd.DataFrame, meta_extra: dict | None = None) -> tuple[bytes, dict]:
    df = df.sort_values(["date", "match_id"]).reset_index(drop=True)
    divs = df[["division", "country", "league"]].drop_duplicates().sort_values(["country", "division"])
    div_idx = {d: i for i, d in enumerate(divs.division)}
    seasons = sorted(df.season.unique())
    teams = pd.concat([df[["country", "home"]].rename(columns={"home": "team"}),
                       df[["country", "away"]].rename(columns={"away": "team"})]).drop_duplicates()
    teams = teams.sort_values(["team", "country"]).reset_index(drop=True)
    team_idx = {(c, t): i for i, (c, t) in enumerate(zip(teams.country, teams.team, strict=True))}
    arrays = {
        "match_id": df.match_id.astype("<u4").to_numpy(),
        "day": (df.date - EPOCH).dt.days.astype("<u2").to_numpy(),
        "div": df.division.map(div_idx).astype("u1").to_numpy(),
        "season": df.season.map({s: i for i, s in enumerate(seasons)}).astype("u1").to_numpy(),
        "home": np.array([team_idx[(c, t)] for c, t in zip(df.country, df.home, strict=True)], dtype="<u2"),
        "away": np.array([team_idx[(c, t)] for c, t in zip(df.country, df.away, strict=True)], dtype="<u2"),
        "fth": _u8(df.fth), "fta": _u8(df.fta), "hth": _u8(df.hth), "hta": _u8(df.hta),
        "corners": _u8(df.corners_total), "cards": _u8(df.cards_total),
        "oh": _odds(df.oh), "od": _odds(df.od), "oa": _odds(df.oa), "oo": _odds(df.oo), "ou": _odds(df.ou),
    }
    meta = {
        "n": int(len(df)), "epoch": str(EPOCH.date()),
        "divs": [{"code": r.division, "country": r.country, "league": r.league} for r in divs.itertuples()],
        "seasons": seasons,
        "teams": [{"name": t, "country": c} for c, t in zip(teams.country, teams.team, strict=True)],
        "columns": [c for c, _ in COLUMNS],
        "dtypes": [d for _, d in COLUMNS],
        "date_range": [str(df.date.min().date()), str(df.date.max().date())],
        **(meta_extra or {}),
    }
    js = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    body = b"".join(arrays[c].astype(d).tobytes() + b"\0" * (-(arrays[c].astype(d).nbytes) % 4) for c, d in COLUMNS)
    raw = struct.pack("<I", len(js)) + js + body
    return gzip.compress(raw, 9), meta
