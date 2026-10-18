// node mobile/test_parity.mjs <klasör>  — JS motoru, Python motoruyla aynı sonucu veriyor mu?
import fs from "node:fs";
import zlib from "node:zlib";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const E = require("./engine.js");
const dir = process.argv[2];
const raw = zlib.gunzipSync(fs.readFileSync(`${dir}/data.bin.gz`));
const D = E.decode(raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength));
const ref = JSON.parse(fs.readFileSync(`${dir}/ref.json`));
let bad = 0;
for (const r of ref) {
  const res = E.analyze(D, r.q, r.sc, { topN: r.n });
  const ids = res.top.map((t) => D.match_id[t.i]);
  const same = ids.length === r.ids.length && ids.every((x, k) => x === r.ids[k]);
  const setSame = new Set(ids).size === new Set(r.ids).size && ids.every((x) => r.ids.includes(x));
  let maxDiff = 0;
  for (const g of Object.keys(r.markets)) for (const [k, v] of Object.entries(r.markets[g])) {
    const m = res.summary.markets[g][k];
    if (!m || m.n !== v.n) { maxDiff = 9; console.log("n farkı", g, k, m && m.n, v.n); continue; }
    if (v.rate !== null) maxDiff = Math.max(maxDiff, Math.abs(m.rate - v.rate), Math.abs(m.ci_low - v.ci_low), Math.abs(m.ci_high - v.ci_high));
  }
  for (const [k, v] of Object.entries(r.htft)) maxDiff = Math.max(maxDiff, Math.abs((res.summary.htft[k]?.count ?? -1) - v.count));
  const ok = setSame && maxDiff < 1e-9 && res.scope_matches === r.scope_matches && Math.abs(res.sim_mean - r.sim_mean) < 1e-6;
  console.log(ok ? "OK  " : "FAIL", r.name, `kapsam=${res.scope_matches}/${r.scope_matches} kullanılan=${res.used}/${r.used} sıraAynı=${same} maxFark=${maxDiff.toExponential(1)}`);
  if (!ok) bad++;
}
process.exit(bad ? 1 : 0);
