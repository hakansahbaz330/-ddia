"""Komut satırı: python -m app.importer.cli dosya1.xlsx dosya2.xlsx [--map eslesme.json] [--force]"""
import argparse
import json
import sys
from pathlib import Path

from app.db import get_engine, session_scope
from app.schema import Base


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Maç arşivlerini veritabanına aktarır.")
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--map", type=Path, help='Elle sütun eşleşmesi JSON: {"Sütun": "odds:B365:1X2:H:pre"}')
    ap.add_argument("--force", action="store_true", help="Daha önce aktarılmış dosyayı yeniden aktar")
    ap.add_argument("--json", action="store_true", help="Ham JSON raporu yazdır")
    args = ap.parse_args(argv)

    from app.importer.engine import import_file
    from app.importer.report_text import render_report

    overrides = json.loads(args.map.read_text()) if args.map else None
    Base.metadata.create_all(get_engine())  # migrasyon uygulanmamışsa tablo yoksa oluştur
    code = 0
    for f in args.files:
        with session_scope() as s:
            rep = import_file(s, f, overrides=overrides, force=args.force)
        print(json.dumps(rep, ensure_ascii=False, indent=2) if args.json else render_report(rep))
        if rep.get("status") == "failed":
            code = 1
    return code


if __name__ == "__main__":
    sys.exit(main())
