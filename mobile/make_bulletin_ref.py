"""Bülten modeli parite referansı: Python çıktısı (node test_bulletin_parity.mjs karşılaştırır).
Kullanım: cd backend && PYTHONPATH=. python ../mobile/make_bulletin_ref.py ../mobile/weekly.json <çıktı.json>"""
import json
import sys

from app.models.bulletin_model import analyze_bulletin_match

W = json.load(open(sys.argv[1]))["matches"]
picks = [next(m for m in W if len(m["odds"]) >= 39), next(m for m in W if 20 <= len(m["odds"]) < 39), next(m for m in W if len(m["odds"]) == 15),
         next(m for m in W if len(m["odds"]) <= 10)]
out = []
for m in picks:
    r = analyze_bulletin_match(m["odds"])
    out.append({"odds": m["odds"], "lh": r["lh"], "la": r["la"], "ht_lh": r["ht_lh"], "ht_la": r["ht_la"], "htft": r["htft"],
                "top": r["top_scores"][:5], "markets": [{"g": x["group"], "l": x["label"], "m": x["model"], "ev": x["ev"]} for x in r["markets"]]})
json.dump(out, open(sys.argv[2], "w"))
print("ok", len(out))
