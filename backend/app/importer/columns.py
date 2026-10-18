"""Kaynak sütun adlarını otomatik olarak anlamlandırır (Football-Data.co.uk şeması + genel eş anlamlılar).

Her sütun şu kategorilerden birine düşer:
  core   : maç alanı (tarih, takım, skor ...)         -> ColumnSpec(kind="core", target="home_team")
  stat   : takım istatistiği (şut, korner ...)         -> ColumnSpec(kind="stat", target="shots", side="H")
  odds   : bahis oranı                                 -> ColumnSpec(kind="odds", bookmaker=..., market=...)
  line   : handikap çizgisi                            -> ColumnSpec(kind="core", target="ah_line")
  ignore : bilinçli olarak atlanır (hesaplanan/özet)
  unknown: tanınmadı -> kullanıcıya gösterilir, içe aktarılmaz

Kullanıcı `overrides` ile {"sütun": "core:home_team" | "odds:B365:1X2:H:closing" | "ignore"} verebilir.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

BOOKMAKER_NAMES = {
    "B365": "Bet365", "BW": "Bet&Win", "IW": "Interwetten", "LB": "Ladbrokes",
    "PS": "Pinnacle", "WH": "William Hill", "VC": "VC Bet", "BF": "Betfair", "BFD": "Betfair Sportsbook",
    "BFE": "Betfair Exchange", "BMGM": "BetMGM", "BV": "BetVictor", "CL": "Coral", "1XB": "1xBet",
    "SJ": "Stan James", "GB": "Gamebookers", "BS": "Blue Square", "SO": "Sporting Odds",
    "SB": "Sportingbet", "SY": "Stanleybet",
    "Max": "Piyasa en yüksek", "Avg": "Piyasa ortalaması",
    "BbMax": "BetBrain en yüksek", "BbAvg": "BetBrain ortalaması",
    # PP, SKB: kaynak dosyada açıklanmadığı için kod olduğu gibi gösterilir.
}
BOOKMAKER_ALIASES = {"P": "PS"}  # "P>2.5" -> Pinnacle
KNOWN_BOOKMAKERS = set(BOOKMAKER_NAMES) | {"PP", "SKB"}

# Çekirdek alanlar: kaynak adı (küçük harf, boşluksuz) -> hedef alan
CORE_SYNONYMS = {
    "div": "division", "league": "division", "lig": "division",
    "date": "date", "tarih": "date",
    "time": "time", "saat": "time",
    "hometeam": "home_team", "home": "home_team", "evsahibi": "home_team", "ev": "home_team",
    "awayteam": "away_team", "away": "away_team", "deplasman": "away_team",
    "fthg": "ft_home", "hg": "ft_home",
    "ftag": "ft_away", "ag": "ft_away",
    "hthg": "ht_home", "htag": "ht_away",
    "referee": "referee", "hakem": "referee",
    "ahh": "ah_line", "bbahh": "ah_line", "ahch": "ah_line_closing",
}
# Hesaplanan/özet sütunlar: skorlardan kendimiz üretiriz veya anlamı oran değildir.
IGNORED = {
    "ftr": "Sonuç sütunu Excel formülü; skorlardan yeniden hesaplanır.",
    "htr": "İlk yarı sonucu Excel formülü; skorlardan yeniden hesaplanır.",
    "bb1x2": "Oran veren bahis şirketi sayısı (oran değil).",
    "bbou": "Oran veren bahis şirketi sayısı (oran değil).",
    "bbah": "Oran veren bahis şirketi sayısı (oran değil).",
}
# (ev, deplasman) istatistik sütunları
STAT_PAIRS = {
    "shots": ("HS", "AS"), "shots_on_target": ("HST", "AST"), "fouls": ("HF", "AF"),
    "corners": ("HC", "AC"), "yellow_cards": ("HY", "AY"), "red_cards": ("HR", "AR"),
    "free_kicks_conceded": ("HFKC", "AFKC"), "xg": ("HxG", "AxG"),
}
STAT_BY_COLUMN = {c.lower(): (t, "HA"[i]) for t, cols in STAT_PAIRS.items() for i, c in enumerate(cols)}

SEL_1X2 = {"H": "1", "D": "X", "A": "2"}
RE_BB = re.compile(r"^Bb(?P<agg>Mx|Av)(?P<rest>.+)$")


@dataclass(frozen=True)
class ColumnSpec:
    kind: str  # core | stat | odds | ignore | unknown
    target: str | None = None  # core/stat hedef alanı
    side: str | None = None  # stat için H/A
    bookmaker: str | None = None
    market: str | None = None  # 1X2 | OU | AH
    selection: str | None = None
    line: float | None = None
    odds_type: str | None = None  # pre | closing | unspecified
    note: str | None = None

    def describe(self) -> str:
        if self.kind == "odds":
            line = f" {self.line}" if self.line is not None else ""
            return f"odds:{self.bookmaker}:{self.market}{line}:{self.selection}:{self.odds_type}"
        if self.kind in ("core", "stat"):
            return f"{self.kind}:{self.target}" + (f":{self.side}" if self.side else "")
        return self.kind

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


def _odds(bk: str, market: str, sel: str, odds_type: str, line: float | None = None) -> ColumnSpec:
    bk = BOOKMAKER_ALIASES.get(bk, bk)
    return ColumnSpec("odds", bookmaker=bk, market=market, selection=sel, line=line, odds_type=odds_type)


_BK_PREFIXES = sorted(KNOWN_BOOKMAKERS | set(BOOKMAKER_ALIASES), key=len, reverse=True)
_BODY_1X2 = re.compile(r"^[HDA]$")
_BODY_OU = re.compile(r"^(?P<dir>[<>])(?P<line>\d+(?:\.\d+)?)$")
_BODY_AH = re.compile(r"^AH(?P<sel>[HA])$")


def _parse_bookmaker_column(compact: str) -> ColumnSpec | None:
    """<bahisçi>[C]<gövde>: bilinen bahisçi önekini ayırır, 'C' kapanış işaretidir (VCH = VC+H, BWCH = BW+C+H)."""
    for bk in _BK_PREFIXES:
        if not compact.startswith(bk):
            continue
        tail = compact[len(bk):]
        for closing, body in ((False, tail), (True, tail[1:] if tail.startswith("C") else None)):
            if body is None:
                continue
            otype = "closing" if closing else "pre"
            if _BODY_1X2.match(body):
                return _odds(bk, "1X2", SEL_1X2[body], otype)
            m = _BODY_AH.match(body)
            if m:
                return _odds(bk, "AH", "home" if m["sel"] == "H" else "away", otype)
            m = _BODY_OU.match(body)
            if m:
                return _odds(bk, "OU", "over" if m["dir"] == ">" else "under", otype, float(m["line"]))
    return None


def classify_column(name: str) -> ColumnSpec:
    raw = str(name).strip()
    key = re.sub(r"\s+", "", raw).lower()
    if key in IGNORED:
        return ColumnSpec("ignore", note=IGNORED[key])
    if key in CORE_SYNONYMS:
        return ColumnSpec("core", target=CORE_SYNONYMS[key])
    if key in STAT_BY_COLUMN:
        target, side = STAT_BY_COLUMN[key]
        return ColumnSpec("stat", target=target, side=side)

    compact = re.sub(r"\s+", "", raw)
    # BetBrain toplamları: BbMxH, BbAvD, BbMx>2.5, BbMxAHH ...  (zaman damgası belirsiz => unspecified)
    m = RE_BB.match(compact)
    if m:
        bk = "BbMax" if m["agg"] == "Mx" else "BbAvg"
        rest = m["rest"]
        if rest in SEL_1X2:
            return _odds(bk, "1X2", SEL_1X2[rest], "unspecified")
        mo = re.match(r"^([<>])(\d+(?:\.\d+)?)$", rest)
        if mo:
            return _odds(bk, "OU", "over" if mo[1] == ">" else "under", "unspecified", float(mo[2]))
        if rest in ("AHH", "AHA"):
            return _odds(bk, "AH", "home" if rest == "AHH" else "away", "unspecified")
        return ColumnSpec("unknown")

    spec = _parse_bookmaker_column(compact)
    if spec:
        return spec
    return ColumnSpec("unknown")


def parse_override(text: str) -> ColumnSpec:
    """'ignore' | 'core:home_team' | 'stat:shots:H' | 'odds:B365:1X2:H:closing' | 'odds:B365:OU2.5:over:pre'."""
    parts = text.split(":")
    kind = parts[0]
    if kind == "ignore":
        return ColumnSpec("ignore", note="kullanıcı tarafından yok sayıldı")
    if kind == "core" and len(parts) == 2:
        return ColumnSpec("core", target=parts[1])
    if kind == "stat" and len(parts) == 3 and parts[2] in ("H", "A"):
        return ColumnSpec("stat", target=parts[1], side=parts[2])
    if kind == "odds" and len(parts) == 5:
        _, bk, mkt, sel, otype = parts
        line = None
        mm = re.match(r"^(OU)(\d+(?:\.\d+)?)$", mkt)
        if mm:
            mkt, line = "OU", float(mm[2])
        if mkt not in ("1X2", "OU", "AH") or otype not in ("pre", "closing", "unspecified"):
            raise ValueError(f"Geçersiz eşleşme: {text}")
        return ColumnSpec("odds", bookmaker=bk, market=mkt, selection=sel, line=line, odds_type=otype)
    raise ValueError(f"Geçersiz eşleşme: {text!r}")


def build_mapping(columns: list[str], overrides: dict[str, str] | None = None) -> dict[str, ColumnSpec]:
    overrides = overrides or {}
    out: dict[str, ColumnSpec] = {}
    for c in columns:
        out[c] = parse_override(overrides[c]) if c in overrides else classify_column(c)
    return out


def mapping_summary(mapping: dict[str, ColumnSpec]) -> dict:
    by_kind: dict[str, list[str]] = {}
    for col, spec in mapping.items():
        by_kind.setdefault(spec.kind, []).append(col)
    return {k: sorted(v) for k, v in by_kind.items()}
