"""Excel/CSV okuyucuları. Dosyayı bütünüyle belleğe almadan satır satır akıtır."""
from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import openpyxl

Row = tuple[int, list[Any]]  # (kaynak satır numarası [1 tabanlı], hücre değerleri)


class UnsupportedFile(Exception):
    pass


def iter_sheets(path: Path) -> Iterator[tuple[str, list[str], Iterator[Row]]]:
    """(sayfa adı, başlıklar, satır akışı) üretir. Boş sayfalar atlanır."""
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        yield from _iter_excel(path)
    elif suffix in (".csv", ".txt"):
        yield from _iter_csv(path)
    else:
        raise UnsupportedFile(f"Desteklenmeyen dosya türü: {suffix or '(uzantısız)'}. xlsx veya csv kullanın.")


def _iter_excel(path: Path):
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # bozuk zip, parola vb.
        raise UnsupportedFile(f"Excel dosyası açılamadı ({exc.__class__.__name__}): {exc}") from exc
    try:
        for ws in wb.worksheets:
            rows = ws.iter_rows(values_only=True)
            header_row = next(rows, None)
            if not header_row:
                continue
            header = [str(h).strip() if h is not None else "" for h in header_row]
            while header and header[-1] == "":
                header.pop()
            if not any(header):
                continue
            n = len(header)

            def gen(rows=rows, n=n):
                for i, r in enumerate(rows, start=2):
                    vals = list(r[:n])
                    if all(v is None or (isinstance(v, str) and not v.strip()) for v in vals):
                        continue  # tamamen boş satır
                    yield i, vals + [None] * (n - len(vals))

            yield ws.title, header, gen()
    finally:
        # read_only modunda dosya tutacağı kapatılmalı; üretici tüketildikten sonra çağrılır.
        pass


def _iter_csv(path: Path):
    raw = path.read_bytes()[:200_000]
    for enc in ("utf-8-sig", "cp1254", "latin-1"):
        try:
            raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialect = csv.Sniffer().sniff(raw.decode(enc, errors="replace")[:5000], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    f = path.open(newline="", encoding=enc, errors="replace")
    reader = csv.reader(f, dialect)
    header_row = next(reader, None)
    if not header_row:
        f.close()
        return
    header = [h.strip() for h in header_row]
    while header and header[-1] == "":
        header.pop()
    n = len(header)

    def gen():
        try:
            for i, r in enumerate(reader, start=2):
                vals = [(v.strip() or None) for v in r[:n]]
                if all(v is None for v in vals):
                    continue
                yield i, vals + [None] * (n - len(vals))
        finally:
            f.close()

    yield path.stem, header, gen()
