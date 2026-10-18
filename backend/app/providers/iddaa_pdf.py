"""İddaa/Nesine haftalık bülten PDF'sini ayrıştırır (kullanıcının kendi indirdiği resmi PDF; metin katmanı gerekir).

Sütunlar, sayfadaki başlık satırından okunan x-konumlarıyla eşlenir (satırdaki boş hücreler kaymaz).
Maçlar sol sütundaki spor harfine (F=futbol, B=basketbol, V=voleybol, H=hentbol ...) bağlanır; yalnızca futbol alınır.
Her maç 1-2 metin satırına yayılabildiği için kelimeler dikey olarak en yakın maç çapasına atanır.
"""
from __future__ import annotations

import re
from datetime import date

MONTHS = {"OCAK": 1, "ŞUBAT": 2, "MART": 3, "NİSAN": 4, "MAYIS": 5, "HAZİRAN": 6, "TEMMUZ": 7, "AĞUSTOS": 8,
          "EYLÜL": 9, "EKİM": 10, "KASIM": 11, "ARALIK": 12}
DAYS = {"PAZARTESİ", "SALI", "ÇARŞAMBA", "PERŞEMBE", "CUMA", "CUMARTESİ", "PAZAR"}

# Başlık sırası (soldan sağa) -> alan adı. Başlıkta "1 0 2" gibi tekrarlar konum sırasıyla çözülür.
COLUMN_KEYS = (
    ["ms1", "ms0", "ms2", "hc1", "hc0", "hc2", "fg1", "fgn", "fg2",
     "msou_1a", "msou_0a", "msou_2a", "msou_1u", "msou_0u", "msou_2u",
     "ou25_alt", "ou25_ust", "ou35_alt", "ou35_ust", "tline", "kg_var", "kg_yok",
     "tg_01", "tg_23", "tg_45", "tg_6p", "ht1", "ht0", "ht2", "ht15_alt", "ht15_ust"]
    + ["htft_11", "htft_10", "htft_12", "htft_01", "htft_00", "htft_02", "htft_21", "htft_20", "htft_22"]
)
_DEC = re.compile(r"^\d{1,3},\d{2}$")
_TIME = re.compile(r"^\d{2}:\d{2}")


def _header_centers(words) -> list[float]:
    """'1/1' ve '2/2' gibi sıralı başlıklardan 40 sütunun x-merkezlerini çıkarır."""
    top = next((w["top"] for w in words if w["text"] == "OLMAZ"), None)
    if top is None:
        return []
    row = sorted((w for w in words if abs(w["top"] - top) < 4.5 and w["x0"] > 170), key=lambda w: w["x0"])
    return [(w["x0"] + w["x1"]) / 2 for w in row]


def parse_pdf(path, year: int | None = None) -> dict:
    import pdfplumber

    year = year or date.today().year
    matches, skipped, days_seen = [], 0, []
    skipped_rows: list[dict] = []
    with pdfplumber.open(path) as pdf:
        centers: list[float] = []
        for pg in pdf.pages:
            words = pg.extract_words()
            hc = _header_centers(words)
            if len(hc) == len(COLUMN_KEYS):
                centers = hc
            if not centers:
                continue
            # gün başlıkları: satır "16 EKİM CUMA"
            heads = []
            lines: dict[int, list] = {}
            for w in words:
                lines.setdefault(round(w["top"]), []).append(w)
            for top, ws in lines.items():
                ws = sorted((w for w in ws if w["x0"] < 75), key=lambda w: w["x0"])
                if len(ws) >= 3 and ws[0]["x0"] < 25 and ws[0]["text"].isdigit() and ws[1]["text"] in MONTHS and ws[2]["text"] in DAYS:
                    d = date(year, MONTHS[ws[1]["text"]], int(ws[0]["text"]))
                    heads.append((top, d))
                    days_seen.append(str(d))
            heads.sort()
            anchors = sorted(((w["top"] + w["bottom"]) / 2, w["text"]) for w in words if w["x0"] < 12.5 and len(w["text"]) == 1 and w["text"].isalpha() and w["top"] > 335)
            if not anchors:
                continue
            ys = [a[0] for a in anchors]
            buckets: list[list] = [[] for _ in anchors]
            for w in words:
                if w["top"] <= 335 or w["x0"] < 12.5:
                    continue
                cy = (w["top"] + w["bottom"]) / 2
                k = min(range(len(ys)), key=lambda i: abs(ys[i] - cy))
                if abs(ys[k] - cy) <= 5.2:
                    buckets[k].append(w)
            for (ay, sport), ws in zip(anchors, buckets, strict=True):
                if sport != "F":
                    continue
                league = " ".join(w["text"] for w in sorted(ws, key=lambda w: w["x0"]) if 13 <= w["x0"] < 28.5)
                time_ = next((w["text"][:5] for w in ws if _TIME.match(w["text"]) and 28 <= w["x0"] < 40), "")
                names = sorted((w for w in ws if 62 <= w["x0"] < 160 and not _DEC.match(w["text"]) and w["text"] != "-"), key=lambda w: w["x0"])
                if len(names) < 2:
                    skipped += 1
                    skipped_rows.append({"league": league, "reason": "takım adı okunamadı"})
                    continue
                gaps = [(names[i + 1]["x0"] - names[i]["x1"], i) for i in range(len(names) - 1)]
                g, cut = max(gaps)
                home = " ".join(w["text"] for w in names[: cut + 1])
                away = " ".join(w["text"] for w in names[cut + 1:])
                odds: dict[str, float] = {}
                for w in ws:
                    if w["x0"] > 170 and _DEC.match(w["text"]):
                        cx = (w["x0"] + w["x1"]) / 2
                        j = min(range(len(centers)), key=lambda i: abs(centers[i] - cx))
                        if abs(centers[j] - cx) <= 7:
                            odds[COLUMN_KEYS[j]] = float(w["text"].replace(",", "."))
                if not all(k in odds for k in ("ms1", "ms0", "ms2")):
                    skipped += 1  # 1X2 yok: analiz edilemez (ör. sadece özel pazar)
                    skipped_rows.append({"league": league, "home": home, "away": away, "time": time_, "reason": "1X2 oranı yok"})
                    continue
                day = None
                for top, d in heads:
                    if top <= ay + 1:
                        day = d
                if day is None and heads:
                    day = heads[0][1]
                matches.append({"date": str(day) if day else None, "time": time_, "league": league, "home": home, "away": away,
                                "odds": odds})
    return {"matches": matches, "skipped_rows": skipped, "skipped_detail": skipped_rows[:100], "days": sorted(set(days_seen))}


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    import sys
    from pathlib import Path

    ap = argparse.ArgumentParser(description="İddaa/Nesine haftalık bülten PDF'sini JSON'a çevirir (yalnızca futbol).")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--year", type=int, default=date.today().year)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--all-leagues", action="store_true", help="Arşivde olmayan ligleri de tut (varsayılan: yalnızca arşivdeki ligler)")
    a = ap.parse_args(argv)
    r = parse_pdf(a.pdf, a.year)
    r["source"] = a.pdf.name
    r["parsed_total"] = len(r["matches"])
    if not a.all_leagues:
        from app.providers.iddaa_leagues import filter_archive_leagues

        r["matches"], r["excluded_leagues"] = filter_archive_leagues(r["matches"])
        r["excluded_total"] = sum(r["excluded_leagues"].values())
    a.out.write_text(json.dumps(r, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(r['matches'])} maç tutuldu (bültende {r['parsed_total']} futbol maçı), atlanan satır {r['skipped_rows']} -> {a.out}")
    if not a.all_leagues:
        print("Arşivde olmadığı için çıkarılan lig kodları:", ", ".join(f"{k}({v})" for k, v in list(r["excluded_leagues"].items())[:40]))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
