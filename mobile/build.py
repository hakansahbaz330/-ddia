"""Tek dosyalı mobil uygulamayı üretir: mobile/dist/oran-arsivi.html
Kullanım: cd backend && PYTHONPATH=. python ../mobile/build.py   (veritabanı dolu olmalı)"""
import base64
from pathlib import Path

from app.analysis.features import load_feature_frame
from app.db import session_scope
from app.export.mobile_data import export_mobile
from app.models.strength import fit_strength
from app.services.analysis import market_weight

here = Path(__file__).resolve().parent
with session_scope() as s:
    df = load_feature_frame(s)
w, _ = market_weight()
blob, meta = export_mobile(df, strength=fit_strength(df), w_market=w)
html = (here / "template.html").read_text(encoding="utf-8")
html = html.replace("/*ENGINE*/", (here / "engine.js").read_text(encoding="utf-8"))
html = html.replace("__BLOB__", base64.b64encode(blob).decode())
out = here / "dist" / "oran-arsivi.html"
out.parent.mkdir(exist_ok=True)
out.write_text(html, encoding="utf-8")
print(f"{out} {out.stat().st_size / 1e6:.2f} MB, {meta['n']} maç")
