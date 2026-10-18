"""Satır temizleme ve doğrulama. Bilinmeyen değerler asla sessizce 0'a çevrilmez; None kalır ve loglanır."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

from app.importer.columns import ColumnSpec

MAX_GOALS = 30
MIN_ODDS, MAX_ODDS = 1.01, 1000.0  # ondalık oran 1.00 veya altı geçersizdir

DIVISIONS: dict[str, tuple[str, str, int]] = {
    "E0": ("England", "Premier League", 1), "E1": ("England", "Championship", 2),
    "E2": ("England", "League One", 3), "E3": ("England", "League Two", 4),
    "EC": ("England", "National League", 5),
    "SC0": ("Scotland", "Premiership", 1), "SC1": ("Scotland", "Championship", 2),
    "SC2": ("Scotland", "League One", 3), "SC3": ("Scotland", "League Two", 4),
    "D1": ("Germany", "Bundesliga", 1), "D2": ("Germany", "2. Bundesliga", 2),
    "SP1": ("Spain", "La Liga", 1), "SP2": ("Spain", "Segunda División", 2),
    "I1": ("Italy", "Serie A", 1), "I2": ("Italy", "Serie B", 2),
    "F1": ("France", "Ligue 1", 1), "F2": ("France", "Ligue 2", 2),
    "N1": ("Netherlands", "Eredivisie", 1), "B1": ("Belgium", "Pro League", 1),
    "P1": ("Portugal", "Primeira Liga", 1), "T1": ("Turkey", "Süper Lig", 1),
    "G1": ("Greece", "Super League", 1),
}

_DATE_FORMATS = ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y")


@dataclass
class Issue:
    severity: str  # info | warning | error
    issue_type: str
    column: str | None = None
    raw: str | None = None
    message: str = ""


@dataclass
class CleanRow:
    match: dict[str, Any] | None = None
    odds: list[tuple[ColumnSpec, str, float]] = field(default_factory=list)  # (spec, kaynak sütun, oran)
    stats: dict[str, dict[str, float | int]] = field(default_factory=dict)  # {"H": {...}, "A": {...}}
    issues: list[Issue] = field(default_factory=list)
    reject_reason: str | None = None


def season_from_filename(name: str) -> str | None:
    m = re.search(r"(20\d{2})\D{1,3}(20\d{2})", name)
    if m and int(m[2]) == int(m[1]) + 1:
        return f"{m[1]}-{m[2]}"
    return None


def season_from_date(d: date) -> str:
    """Temmuz ve sonrası yeni sezon sayılır (yalnızca dosya adı yoksa yedek yöntem)."""
    y = d.year if d.month >= 7 else d.year - 1
    return f"{y}-{y + 1}"


def season_window(season: str) -> tuple[date, date]:
    y = int(season[:4])
    return date(y, 6, 1), date(y + 1, 9, 30)  # COVID gibi uzayan sezonlar için pay bırakılır


def make_match_key(division: str, d: date, home: str, away: str) -> str:
    s = f"{division}|{d.isoformat()}|{home.casefold()}|{away.casefold()}"
    return hashlib.sha1(s.encode()).hexdigest()


def norm_name(v: Any) -> str | None:
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    return s or None


def to_date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        s = v.strip()
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
    return None


def to_time(v: Any) -> time | None:
    if isinstance(v, datetime):
        return v.time()
    if isinstance(v, time):
        return v
    if isinstance(v, str):
        m = re.match(r"^(\d{1,2}):(\d{2})", v.strip())
        if m and int(m[1]) < 24 and int(m[2]) < 60:
            return time(int(m[1]), int(m[2]))
    return None


def to_number(v: Any) -> tuple[float | None, bool]:
    """(değer, geçerli_mi). Boş hücre -> (None, True); metin/NaN -> (None, False)."""
    if v is None:
        return None, True
    if isinstance(v, bool):
        return None, False
    if isinstance(v, (int, float)):
        if v != v:  # NaN
            return None, True
        return float(v), True
    s = str(v).strip().replace(",", ".")
    if s in ("", "-", "NA", "N/A", "nan"):
        return None, True
    try:
        return float(s), True
    except ValueError:
        return None, False


def result_from_score(h: int | None, a: int | None) -> str | None:
    if h is None or a is None:
        return None
    return "H" if h > a else "A" if h < a else "D"


def _score(v: Any, col: str, issues: list[Issue]) -> int | None:
    x, ok = to_number(v)
    if not ok:
        issues.append(Issue("warning", "invalid_score", col, str(v)[:120], "Skor sayısal değil; boş bırakıldı."))
        return None
    if x is None:
        return None
    if x < 0 or x > MAX_GOALS or x != int(x):
        issues.append(Issue("warning", "invalid_score", col, str(v)[:120], "Skor geçerli aralık dışında; boş bırakıldı."))
        return None
    return int(x)


def clean_row(
    values: dict[str, Any],
    mapping: dict[str, ColumnSpec],
    season: str | None,
    aliases: dict[str, str] | None = None,
) -> CleanRow:
    out = CleanRow()
    core: dict[str, Any] = {}
    stats: dict[str, dict[str, float | int]] = {"H": {}, "A": {}}
    odds_raw: list[tuple[ColumnSpec, str, Any]] = []
    for col, spec in mapping.items():
        v = values.get(col)
        if spec.kind == "core":
            core[spec.target] = v
        elif spec.kind == "stat":
            x, ok = to_number(v)
            if not ok:
                out.issues.append(Issue("warning", "invalid_stat", col, str(v)[:120], "İstatistik sayısal değil; boş bırakıldı."))
            elif x is not None and x >= 0:
                stats[spec.side][spec.target] = x if spec.target == "xg" else int(x)
            elif x is not None:
                out.issues.append(Issue("warning", "invalid_stat", col, str(x), "Negatif istatistik; boş bırakıldı."))
        elif spec.kind == "odds":
            odds_raw.append((spec, col, v))

    d = to_date(core.get("date"))
    if d is None:
        out.reject_reason = "invalid_date"
        out.issues.append(Issue("error", "invalid_date", "Date", str(core.get("date"))[:120], "Tarih okunamadı; satır reddedildi."))
        return out
    home, away = norm_name(core.get("home_team")), norm_name(core.get("away_team"))
    if not home or not away:
        out.reject_reason = "missing_team"
        out.issues.append(Issue("error", "missing_team", None, None, "Ev sahibi veya deplasman adı boş; satır reddedildi."))
        return out
    if aliases:
        home, away = aliases.get(home, home), aliases.get(away, away)
    if home.casefold() == away.casefold():
        out.reject_reason = "same_team"
        out.issues.append(Issue("error", "same_team", None, home, "Ev sahibi ve deplasman aynı; satır reddedildi."))
        return out
    division = norm_name(core.get("division")) or "??"
    if division == "??":
        out.issues.append(Issue("warning", "missing_division", "Div", None, "Lig kodu yok; '??' olarak kaydedildi."))

    ft_h = _score(core.get("ft_home"), "FTHG", out.issues)
    ft_a = _score(core.get("ft_away"), "FTAG", out.issues)
    ht_h = _score(core.get("ht_home"), "HTHG", out.issues)
    ht_a = _score(core.get("ht_away"), "HTAG", out.issues)
    if (ft_h is None) != (ft_a is None):
        out.issues.append(Issue("warning", "partial_score", "FTHG/FTAG", None, "Maç sonu skorunun yalnızca bir tarafı var; ikisi de boş bırakıldı."))
        ft_h = ft_a = None
    if (ht_h is None) != (ht_a is None):
        out.issues.append(Issue("warning", "partial_score", "HTHG/HTAG", None, "İlk yarı skorunun yalnızca bir tarafı var; ikisi de boş bırakıldı."))
        ht_h = ht_a = None
    if ft_h is None:
        out.issues.append(Issue("warning", "missing_score", "FTHG/FTAG", None, "Maç sonu skoru yok (oynanmadı/ertelendi olabilir); maç sonucu bekleyen olarak kaydedildi."))
    if ht_h is not None and ft_h is not None and (ht_h > ft_h or ht_a > ft_a):
        out.issues.append(Issue("warning", "ht_exceeds_ft", "HTHG/HTAG", f"{ht_h}-{ht_a} > {ft_h}-{ft_a}", "İlk yarı skoru maç sonundan büyük; ilk yarı skoru boş bırakıldı."))
        ht_h = ht_a = None

    if season is None:
        season = season_from_date(d)
    else:
        lo, hi = season_window(season)
        if not (lo <= d <= hi):
            out.issues.append(Issue("warning", "date_outside_season", "Date", d.isoformat(), f"Tarih {season} sezon penceresi dışında."))

    info = DIVISIONS.get(division)
    ah, _ = to_number(core.get("ah_line"))
    ahc, _ = to_number(core.get("ah_line_closing"))
    out.match = {
        "match_key": make_match_key(division, d, home, away),
        "division": division, "country": info[0] if info else None,
        "league_name": info[1] if info else None, "tier": info[2] if info else None,
        "season": season, "match_date": d, "kickoff_time": to_time(core.get("time")),
        "home_team": home, "away_team": away,
        "ft_home": ft_h, "ft_away": ft_a, "ht_home": ht_h, "ht_away": ht_a,
        "ft_result": result_from_score(ft_h, ft_a), "ht_result": result_from_score(ht_h, ht_a),
        "referee": norm_name(core.get("referee")),
        "ah_line": ah, "ah_line_closing": ahc,
    }
    for spec, col, v in odds_raw:
        x, ok = to_number(v)
        if x is None:
            if not ok:
                out.issues.append(Issue("warning", "invalid_odds", col, str(v)[:120], "Oran sayısal değil; atlandı."))
            continue
        if not (MIN_ODDS <= x <= MAX_ODDS):
            out.issues.append(Issue("warning", "invalid_odds", col, str(x), "Oran geçerli aralık (1.01–1000) dışında; atlandı."))
            continue
        out.odds.append((spec, col, x))
    out.stats = {k: v for k, v in stats.items() if v}
    return out
