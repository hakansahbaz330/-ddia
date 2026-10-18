// node mobile/check_leagues.mjs <data.bin.gz> mobile/weekly.json
// Her bülten lig kodunun takımlarının, arşivdeki karşılık gelen ligin GÜNCEL SEZON takımlarıyla eşleşme oranını gösterir.
// %70'in altı: kod yanlış eşlenmiş olabilir (kupa, alt lig...). Çıkış kodu 1.
import fs from "node:fs";
import zlib from "node:zlib";
import { createRequire } from "node:module";
const E = createRequire(import.meta.url)("./engine.js");
const raw = zlib.gunzipSync(fs.readFileSync(process.argv[2]));
const D = E.decode(raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength));
const W = JSON.parse(fs.readFileSync(process.argv[3])).matches;
const last = D.meta.seasons.length - 1, cur = {};
for (let i = 0; i < D.n; i++) if (D.season[i] === last) (cur[D.div[i]] = cur[D.div[i]] || new Set()).add(D.home[i]).add(D.away[i]);
const by = {};
W.forEach((m) => {
  const di = D.meta.divs.findIndex((d) => d.code === m.division), r = (by[m.league] = by[m.league] || { div: m.division, ok: 0, tot: 0, miss: [] });
  [m.home, m.away].forEach((nm) => { r.tot++; const t = E.matchTeamIn(D, nm, di); if (t >= 0 && cur[di] && cur[di].has(t)) r.ok++; else r.miss.push(nm); });
});
let bad = 0, ok = 0, tot = 0;
Object.entries(by).forEach(([k, r]) => { const f = r.ok / r.tot; ok += r.ok; tot += r.tot; if (f < 0.7) { bad++; console.log("UYARI", k, r.div, (f * 100).toFixed(0) + "%", r.miss.slice(0, 4).join(", ")); } });
console.log(`takım eşleşmesi: ${ok}/${tot} (%${(ok / tot * 100).toFixed(1)}); şüpheli lig kodu: ${bad}`);
process.exit(bad ? 1 : 0);
