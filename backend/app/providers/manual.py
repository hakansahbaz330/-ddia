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


def parse_bulletin(text: str) -> dict:
    matches, errors = [], []
    for ln, line in enumerate(text.splitlines(), start=1):
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
