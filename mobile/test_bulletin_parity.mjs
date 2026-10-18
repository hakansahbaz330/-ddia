// node mobile/test_bulletin_parity.mjs <ref.json> — bülten çok pazarlı modeli: JS = Python
import fs from "node:fs";
import { createRequire } from "node:module";
const E = createRequire(import.meta.url)("./engine.js");
const ref = JSON.parse(fs.readFileSync(process.argv[2]));
let bad = 0;
ref.forEach((r, k) => {
  const t0 = Date.now(), R = E.analyzeBulletinMatch(r.odds);
  let md = Math.max(Math.abs(R.lh - r.lh), Math.abs(R.la - r.la), Math.abs(R.htLh - r.ht_lh), Math.abs(R.htLa - r.ht_la));
  let pd = 0, evd = 0;
  r.markets.forEach((x, i) => { const y = R.markets[i]; if (!y || y.label !== x.l) { pd = 9; return; } pd = Math.max(pd, Math.abs(y.model - x.m)); evd = Math.max(evd, Math.abs(y.ev - x.ev)); });
  Object.keys(r.htft).forEach((c) => { pd = Math.max(pd, Math.abs(R.htft[c] - r.htft[c])); });
  const sameTop = R.top.slice(0, 3).every((t, i) => t.score === r.top[i].score);
  const ok = md < 5e-3 && pd < 2e-3 && evd < 5e-3 && sameTop && R.markets.length === r.markets.length;
  console.log(ok ? "OK  " : "FAIL", `maç ${k}: λ farkı ${md.toExponential(1)}, p farkı ${pd.toExponential(1)}, EV farkı ${evd.toExponential(1)}, pazar ${R.markets.length}, ${Date.now() - t0} ms`);
  if (!ok) bad++;
});
process.exit(bad ? 1 : 0);
