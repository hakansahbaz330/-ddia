"""Sağlayıcı takım/lig adlarını arşivdeki takımlara eşler (otomatik ve açıklanabilir; belirsizse eşleşmez)."""
from __future__ import annotations

import difflib
import re
import unicodedata

import pandas as pd

# The Odds API spor anahtarı -> arşiv lig kodu. Anahtarlar bellekten yazıldı ve DOĞRULANMADI:
# gerçek liste GET /v4/sports ile gelir; farklıysa burayı düzenleyin.
SPORT_TO_DIVISION = {
    "soccer_epl": "E0", "soccer_efl_champ": "E1", "soccer_england_league1": "E2", "soccer_england_league2": "E3",
    "soccer_spl": "SC0", "soccer_germany_bundesliga": "D1", "soccer_germany_bundesliga2": "D2",
    "soccer_spain_la_liga": "SP1", "soccer_spain_segunda_division": "SP2", "soccer_italy_serie_a": "I1",
    "soccer_italy_serie_b": "I2", "soccer_france_ligue_one": "F1", "soccer_france_ligue_two": "F2",
    "soccer_netherlands_eredivisie": "N1", "soccer_belgium_first_div": "B1", "soccer_portugal_primeira_liga": "P1",
    "soccer_turkey_super_league": "T1", "soccer_greece_super_league": "G1",
}
_STOP = {"fc", "cf", "afc", "sc", "ac", "as", "ssc", "fk", "sk", "bk", "fsv", "vfb", "vfl", "tsg", "rb", "1", "04", "05", "de", "the"}


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(t for t in s.split() if t not in _STOP)


class TeamMatcher:
    def __init__(self, df: pd.DataFrame):
        self.by_div: dict[str, dict[str, str]] = {}  # division -> {norm: "Ülke|Takım"}
        for d, g in df.groupby("division"):
            names = {}
            for country, team in pd.concat([g[["country", "home"]].set_axis(["country", "t"], axis=1),
                                            g[["country", "away"]].set_axis(["country", "t"], axis=1)]).drop_duplicates().itertuples(index=False):
                names[norm(team)] = f"{country}|{team}"
            self.by_div[d] = names

    def match(self, division: str | None, name: str, cutoff: float = 0.82) -> str | None:
        pools = [self.by_div[division]] if division in self.by_div else list(self.by_div.values())
        n = norm(name)
        for pool in pools:
            if n in pool:
                return pool[n]
        best, best_r = None, 0.0
        for pool in pools:
            for k, v in pool.items():
                r = difflib.SequenceMatcher(None, n, k).ratio()
                if (n in k or k in n) and min(len(n), len(k)) >= 4:
                    r = max(r, 0.9)
                if r > best_r:
                    best, best_r = v, r
        return best if best_r >= cutoff else None
