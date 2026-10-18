"""Parite referansı: Python motorunun çıktısını ve ikili veriyi üretir (node test_parity.mjs karşılaştırır).
Kullanım: cd backend && python ../mobile/make_parity_ref.py <çıktı_klasörü>"""
import json
import sys
from pathlib import Path

from app.analysis.features import load_feature_frame
from app.analysis.similarity import Query, Scope, analyze
from app.db import session_scope
from app.export.mobile_data import export_mobile

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
with session_scope() as s:
    df = load_feature_frame(s)
blob, meta = export_mobile(df)
(out / "data.bin.gz").write_bytes(blob)
teams = {(t["name"]): i for i, t in enumerate(meta["teams"])}
cases = [
    dict(name="tum_arsiv_1x2", q=dict(odds=[2.0, 3.4, 3.8], ou=None), sc=dict(kind="all"), n=50),
    dict(name="tum_arsiv_ou", q=dict(odds=[1.5, 4.2, 6.5], ou=[1.7, 2.1]), sc=dict(kind="all"), n=100),
    dict(name="lig_E0", q=dict(odds=[2.6, 3.3, 2.7], ou=[1.9, 1.95]), sc=dict(kind="league", div=["E0"]), n=25),
    dict(name="takim_son5", q=dict(odds=[1.8, 3.6, 4.5], ou=None), sc=dict(kind="team", team="Galatasaray", venue="home", lastSeasons=5), n=10),
]
ref = []
for c in cases:
    sc = c["sc"]
    py = Scope(kind=sc["kind"], divisions=sc.get("div", []), team=sc.get("team"), venue=sc.get("venue", "any"),
               last_seasons=sc.get("lastSeasons"))
    r = analyze(df, Query(tuple(c["q"]["odds"]), tuple(c["q"]["ou"]) if c["q"]["ou"] else None), py, top_n=c["n"], list_limit=c["n"])
    js_sc = dict(sc)
    if sc.get("team"):
        js_sc["team"] = teams[sc["team"]]
    ref.append(dict(name=c["name"], q=c["q"], sc=js_sc, n=c["n"], used=r["used"], scope_matches=r["scope_matches"],
                    ids=[m["match_id"] for m in r["matches"]], markets=r["summary"]["markets"],
                    htft=r["summary"]["htft"], sim_mean=r["similarity"]["mean"]))
(out / "ref.json").write_text(json.dumps(ref))
print("ok", len(blob) // 1024, "KB")
