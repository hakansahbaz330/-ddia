// node mobile/test_coupon.mjs — kupon üretici: kısıtlar, toplam oran, olasılık çarpımı, alternatif farklılığı
import { createRequire } from "node:module";
const E = createRequire(import.meta.url)("./engine.js");
let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const cands = [];
for (let mi = 0; mi < 30; mi++) for (const [label, grp] of [["MS 1", "Maç sonucu"], ["MS 2", "Maç sonucu"], ["2,5 Üst", "Alt/Üst"], ["KG Var", "Karşılıklı gol"]]) {
  const p = 0.2 + rnd() * 0.65; cands.push({ mi, match: "M" + mi, league: "L" + (mi % 4), group: grp, label, p, odds: Math.round((1 / (p * 1.175)) * 100) / 100, time: "20:00", date: "2026-10-17" });
}
let bad = 0; const ck = (c, m) => { if (!c) { console.log("FAIL", m); bad++; } else console.log("OK  ", m); };
const r = E.buildCoupons(cands, { legs: 5, minOdds: 8, maxOdds: 30, minP: 0.45, perLeague: 2, count: 3, groups: ["Maç sonucu", "Alt/Üst"] });
ck(r.coupons.length === 3, "3 alternatif üretildi (" + r.coupons.length + ")");
r.coupons.forEach((c, i) => {
  const prod = c.legs.reduce((a, l) => a * l.odds, 1), pp = c.legs.reduce((a, l) => a * l.p, 1);
  ck(c.legs.length === 5 && new Set(c.legs.map((l) => l.mi)).size === 5, `kupon ${i}: 5 farklı maç`);
  ck(Math.abs(prod - c.odds) < 1e-9 && Math.abs(pp - c.p) < 1e-12 && Math.abs(c.ev - (pp * prod - 1)) < 1e-9, `kupon ${i}: oran/olasılık/EV doğru`);
  ck(c.odds >= 8 && c.odds <= 30, `kupon ${i}: oran aralığında (${c.odds.toFixed(2)})`);
  ck(c.legs.every((l) => l.p >= 0.45 && l.group !== "Karşılıklı gol"), `kupon ${i}: min olasılık ve izinli pazarlar`);
  ck(Math.max(...Object.values(c.leagues)) <= 2, `kupon ${i}: lig başına en çok 2`);
});
ck(r.coupons[0].p >= r.coupons[1].p && r.coupons[1].p >= r.coupons[2].p, "olasılığa göre sıralı");
const ids = (c) => c.legs.map((l) => l.mi + l.label);
ck(r.coupons.every((c, i) => r.coupons.every((d, j) => i >= j || ids(c).filter((x) => ids(d).includes(x)).length <= 3)), "alternatifler en çok 3 ortak seçim");
const none = E.buildCoupons(cands, { legs: 5, minOdds: 5000, maxOdds: 9000, minP: 0.45 });
ck(none.coupons.length === 0, "ulaşılamayan oran hedefinde boş sonuç (zayıf seçimle doldurulmaz)");
// brute-force doğrulama: 6 maç, 3 seçim: en yüksek olasılıklı uygun kupon
const small = cands.filter((c) => c.mi < 6 && c.group === "Maç sonucu"), o = { legs: 3, minOdds: 3, maxOdds: 12, minP: 0.3, count: 1 };
let best = 0; const ms = [...new Set(small.map((c) => c.mi))];
for (let a = 0; a < ms.length; a++) for (let b = a + 1; b < ms.length; b++) for (let c = b + 1; c < ms.length; c++)
  for (const x of small.filter((q) => q.mi === ms[a] && q.p >= .3)) for (const y of small.filter((q) => q.mi === ms[b] && q.p >= .3)) for (const z of small.filter((q) => q.mi === ms[c] && q.p >= .3)) {
    const od = x.odds * y.odds * z.odds; if (od >= 3 && od <= 12) best = Math.max(best, x.p * y.p * z.p);
  }
const got = E.buildCoupons(small, o).coupons[0];
ck(got && got.p >= best * 0.98, `beam en iyiye yakın (brute-force ${best.toFixed(4)}, bulunan ${got ? got.p.toFixed(4) : "-"})`);
process.exit(bad ? 1 : 0);
