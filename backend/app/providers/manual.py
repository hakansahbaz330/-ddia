"""Elle yapıştırılan bülten ayrıştırıcısı (Nesine/bahisçi bülteni vb. kopyala-yapıştır).

Desteklenen satır: "Ev - Deplasman 1.85 3.40 4.20 [2.5Üst 2.5Alt]" (ayraç: - – — vs; ondalık: nokta veya virgül;
sütun ayracı: boşluk/sekme/;). İlk üç sayı 1-X-2, sonraki iki sayı (varsa) 2,5 üst-alt kabul edilir.
Satır başındaki saat/tarih ve lig başlıkları yok sayılır. Ayrıştırılamayan satırlar hata listesinde döner.
"""
from __future__ import annotations

import re

_SEP = re.compile(r"\s+(?:-|–|—|vs\.?|v)\s+", re.I)
_NUM = re.compile(r"(?<![\w.,])(\d{1,3}(?:[.,]\d{1,3})?)(?![\w])")
_PREFIX = re.compile(r"^\s*(?:\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?\s*)?(?:\d{1,2}:\d{2}\s*)?(?:\d{4,7}\s+)?")


_BLOCK = re.compile(r"</?(?:div|p|br|tr|li|ul|table|section|article|h\d|span|a)\b[^>]*>", re.I)
_CELL = re.compile(r"</t[dh]>", re.I)
_DEC = re.compile(r"(?<![\w.,])\d{1,3}[.,]\d{1,2}(?![\w])")


def html_to_text(src: str) -> str:
    """Kaydedilmiş sayfa (HTML) -> düz metin. Site'ye özgü seçici kullanmaz; yalnızca etiketleri soyar."""
    src = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", src)
    src = _CELL.sub("\t", src)
    src = _BLOCK.sub("\n", src)
    src = re.sub(r"<[^>]+>", " ", src)
    import html as _h
    return _h.unescape(src)


def _team_line(line: str) -> bool:
    m = _SEP.search(line)
    return bool(m) and bool(re.search(r"[^\W\d_]", line[:m.start()])) and bool(re.search(r"[^\W\d_]", line[m.end():]))


def _merge_multiline(lines: list[str]) -> list[str]:
    """Takım satırı ile oranlar farklı satırlardaysa (ör. sayfa kopyası) birleştirir. Çok satırlı modda yalnızca ondalıklı sayılar oran sayılır."""
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        if _team_line(ln) and len(_DEC.findall(ln)) < 3:
            parts, j = [ln], i + 1
            while j < len(lines) and len(_DEC.findall(" ".join(parts))) < 5 and not _team_line(lines[j]):
                nums = _DEC.findall(lines[j])
                if nums:
                    parts.append(" ".join(nums))
                j += 1
                if j - i > 8:
                    break
            out.append(" ".join(parts))
            i = j
        else:
            out.append(ln)
            i += 1
    return out


def parse_bulletin(text: str) -> dict:
    matches, errors = [], []
    if "<" in text and re.search(r"</?(?:html|body|div|table|tr|td|span)\b", text, re.I):
        text = html_to_text(text)
    raw_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln, line in enumerate(_merge_multiline(raw_lines), start=1):
        raw = line.strip()
        if not raw:
            continue
        if not any(ch.isdigit() for ch in raw):
            continue  # lig/başlık satırı
        line = _PREFIX.sub("", raw, count=1)
        m = _SEP.search(line)
        if not m:
            errors.append({"line": ln, "text": raw[:80], "reason": "Takım ayracı (-) bulunamadı"})
            continue
        home = line[:m.start()].strip()
        rest = line[m.end():]
        # deplasman adı: ilk sayıya kadar
        first = _NUM.search(rest)
        if not first:
            errors.append({"line": ln, "text": raw[:80], "reason": "Oran bulunamadı"})
            continue
        away = rest[:first.start()].strip(" \t;:")
        nums = [float(x.replace(",", ".")) for x in _NUM.findall(rest[first.start():])]
        if not home or not away or len(nums) < 3:
            errors.append({"line": ln, "text": raw[:80], "reason": "En az 3 oran (1-X-2) ve iki takım adı gerekli"})
            continue
        o1x2 = nums[:3]
        ou = nums[3:5] if len(nums) >= 5 else None
        if any(o <= 1.0 for o in o1x2) or (ou and any(o <= 1.0 for o in ou)):
            errors.append({"line": ln, "text": raw[:80], "reason": "Oranlar 1,00'dan büyük olmalı"})
            continue
        matches.append({"home": home, "away": away, "odds_1x2": o1x2, "odds_ou25": ou})
    return {"matches": matches, "errors": errors}
