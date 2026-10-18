/* Oran Arşivi motoru: backend/app/analysis/similarity.py ile aynı algoritma (parite testi: mobile/test_parity.mjs). */
(function (root) {
  "use strict";
  var TAU = 0.05;
  var W = { p1: 1, px: 1, p2: 1, pover: 1 };
  var MISS = 255;

  function decode(buf) {
    var dv = new DataView(buf);
    var jl = dv.getUint32(0, true);
    var meta = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, jl)));
    var off = 4 + jl, n = meta.n, D = { meta: meta, n: n };
    var T = { "<u4": Uint32Array, "<u2": Uint16Array, u1: Uint8Array };
    var bytes = { "<u4": 4, "<u2": 2, u1: 1 };
    meta.columns.forEach(function (c, i) {
      var dt = meta.dtypes[i], len = n * bytes[dt];
      D[c] = new T[dt](buf.slice(off, off + len));
      off += len + ((4 - (len % 4)) % 4);
    });
    D.hasOdds = function (i) { return D.oh[i] > 100 && D.od[i] > 100 && D.oa[i] > 100; };
    return D;
  }

  function devig(o) {
    var inv = o.map(function (x) { return 1 / x; }), t = inv.reduce(function (a, b) { return a + b; }, 0);
    return inv.map(function (x) { return x / t; });
  }

  function wilson(k, n) {
    if (!n) return [0, 1];
    var z = 1.96, p = k / n, den = 1 + z * z / n, c = (p + z * z / (2 * n)) / den;
    var h = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den;
    return [Math.max(0, c - h), Math.min(1, c + h)];
  }

  /* kapsam: {kind:'all'|'league'|'team', div:[kod], team:idx, venue:'any'|'home'|'away', opp:idx|null, lastSeasons:n|null} */
  function scopeIdx(D, sc) {
    var out = [], divSet = null, i;
    if (sc.div && sc.div.length) {
      divSet = {};
      sc.div.forEach(function (c) { divSet[D.meta.divs.findIndex(function (d) { return d.code === c; })] = 1; });
    }
    if (sc.kind === "league" && !divSet) throw new Error("Lig bazlı arama için bir lig seçin.");
    if (sc.kind === "team" && (sc.team == null || sc.team < 0)) throw new Error("Takım bazlı arama için listeden bir takım seçin.");
    var minSeason = sc.lastSeasons ? D.meta.seasons.length - sc.lastSeasons : 0;
    for (i = 0; i < D.n; i++) {
      if (D.fth[i] === MISS) continue;
      if (divSet && !divSet[D.div[i]]) continue;
      if (D.season[i] < minSeason) continue;
      if (sc.beforeDay != null && D.day[i] >= sc.beforeDay) continue;
      if (sc.kind === "team") {
        var h = D.home[i] === sc.team, a = D.away[i] === sc.team;
        if (!(sc.venue === "home" ? h : sc.venue === "away" ? a : (h || a))) continue;
        if (sc.opp != null && sc.opp >= 0 && !(D.home[i] === sc.opp || D.away[i] === sc.opp)) continue;
      }
      out.push(i);
    }
    return out;
  }

  /* q: {odds:[o1,ox,o2], ou:[ust,alt]|null}. Dönen: [{i, dist, sim}] benzerliğe göre azalan. */
  function rankSimilar(D, idx, q, tau) {
    tau = tau || TAU;
    var qp = devig(q.odds), qo = q.ou ? devig(q.ou)[0] : null, res = [];
    for (var k = 0; k < idx.length; k++) {
      var i = idx[k];
      if (!D.hasOdds(i)) continue;
      var inv = [100 / D.oh[i], 100 / D.od[i], 100 / D.oa[i]], t = inv[0] + inv[1] + inv[2];
      var s = W.p1 * Math.pow(inv[0] / t - qp[0], 2) + W.px * Math.pow(inv[1] / t - qp[1], 2) + W.p2 * Math.pow(inv[2] / t - qp[2], 2);
      var ws = W.p1 + W.px + W.p2;
      if (qo !== null && D.oo[i] > 100 && D.ou[i] > 100) {
        var po = (100 / D.oo[i]) / (100 / D.oo[i] + 100 / D.ou[i]);
        s += W.pover * Math.pow(po - qo, 2); ws += W.pover;
      }
      var d = Math.sqrt(s / ws);
      res.push({ i: i, dist: d, sim: 100 * Math.exp(-d / tau) });
    }
    res.sort(function (a, b) { return a.dist - b.dist || D.match_id[b.i] - D.match_id[a.i]; });
    return res;
  }

  function b(x) { return x ? 1 : 0; }
  /* Pazar tanımları (Python MARKET_GROUPS ile aynı etiketler). fn(D,i) -> 1|0|null */
  function tot(D, i) { return D.fth[i] + D.fta[i]; }
  function hasHT(D, i) { return D.hth[i] !== MISS; }
  var GROUPS = [
    ["Maç sonucu", [["1", function (D, i) { return b(D.fth[i] > D.fta[i]); }], ["X", function (D, i) { return b(D.fth[i] === D.fta[i]); }], ["2", function (D, i) { return b(D.fth[i] < D.fta[i]); }]]],
    ["Çifte şans", [["1X", function (D, i) { return b(D.fth[i] >= D.fta[i]); }], ["12", function (D, i) { return b(D.fth[i] !== D.fta[i]); }], ["X2", function (D, i) { return b(D.fth[i] <= D.fta[i]); }]]],
    ["Gol üst (maç)", [0.5, 1.5, 2.5, 3.5, 4.5].map(function (x) { return [x + " üst", function (D, i) { return b(tot(D, i) > x); }]; })],
    ["Karşılıklı gol", [["KG var", function (D, i) { return b(D.fth[i] > 0 && D.fta[i] > 0); }]]],
    ["İlk yarı sonucu", [["İY 1", function (D, i) { return hasHT(D, i) ? b(D.hth[i] > D.hta[i]) : null; }], ["İY X", function (D, i) { return hasHT(D, i) ? b(D.hth[i] === D.hta[i]) : null; }], ["İY 2", function (D, i) { return hasHT(D, i) ? b(D.hth[i] < D.hta[i]) : null; }]]],
    ["İlk yarı gol üst", [0.5, 1.5, 2.5].map(function (x) { return ["İY " + x + " üst", function (D, i) { return hasHT(D, i) ? b(D.hth[i] + D.hta[i] > x) : null; }]; })],
    ["İlk yarı KG", [["İY KG var", function (D, i) { return hasHT(D, i) ? b(D.hth[i] > 0 && D.hta[i] > 0) : null; }]]],
    ["Korner üst", [8.5, 9.5, 10.5, 11.5].map(function (x) { return ["Korner " + x + " üst", function (D, i) { return D.corners[i] === MISS ? null : b(D.corners[i] > x); }]; })],
    ["Kart üst", [2.5, 3.5, 4.5, 5.5].map(function (x) { return ["Kart " + x + " üst", function (D, i) { return D.cards[i] === MISS ? null : b(D.cards[i] > x); }]; })]
  ];
  function sym(a, c) { return a > c ? "1" : a < c ? "2" : "X"; }

  function summarize(D, list) {
    var res = { n: list.length, markets: {}, htft: {}, top_scores: [] };
    GROUPS.forEach(function (g) {
      var out = {};
      g[1].forEach(function (m) {
        var k = 0, n = 0;
        for (var j = 0; j < list.length; j++) { var v = m[1](D, list[j]); if (v !== null) { n++; k += v; } }
        var ci = wilson(k, n);
        out[m[0]] = { rate: n ? k / n : null, n: n, ci_low: ci[0], ci_high: ci[1] };
      });
      if (g[1][0][0].indexOf("üst") > -1) {
        Object.keys(out).forEach(function (l) {
          var r = out[l];
          out[l.replace("üst", "alt")] = { rate: r.rate === null ? null : 1 - r.rate, n: r.n, ci_low: 1 - r.ci_high, ci_high: 1 - r.ci_low };
        });
      }
      res.markets[g[0]] = out;
    });
    var ht = {}, sc = {}, htn = 0, goals = 0;
    list.forEach(function (i) {
      if (hasHT(D, i)) { var k = sym(D.hth[i], D.hta[i]) + "/" + sym(D.fth[i], D.fta[i]); ht[k] = (ht[k] || 0) + 1; htn++; }
      var s = D.fth[i] + "-" + D.fta[i]; sc[s] = (sc[s] || 0) + 1; goals += tot(D, i);
    });
    Object.keys(ht).forEach(function (k) { res.htft[k] = { count: ht[k], rate: ht[k] / htn }; });
    res.top_scores = Object.keys(sc).map(function (k) { return { score: k, count: sc[k], rate: sc[k] / list.length }; })
      .sort(function (a, c) { return c.count - a.count || (a.score < c.score ? -1 : 1); }).slice(0, 8);
    if (list.length) res.avg_goals = goals / list.length;
    return res;
  }

  function analyze(D, q, sc, opt) {
    opt = opt || {};
    var scoped = scopeIdx(D, sc), ranked = rankSimilar(D, scoped, q, opt.tau);
    var minSim = opt.minSim || 0, topN = opt.topN || 50, minSample = opt.minSample || 30;
    ranked = ranked.filter(function (r) { return r.sim >= minSim; });
    var top = ranked.slice(0, topN), warnings = [];
    if (top.length < minSample) warnings.push("Örneklem küçük (" + top.length + " < " + minSample + "): yüzdeler güvenilir değil, aralıklar geniş.");
    if (scoped.length && ranked.length < scoped.length * 0.5) warnings.push("Kapsamdaki maçların yarısından fazlasında 1X2 oranı yok; bu maçlar dışarıda kaldı.");
    var minS = top.length ? top[top.length - 1].sim : null;
    if (minS !== null && minS < 50) warnings.push("En düşük benzerlik " + Math.round(minS) + "/100: seçilen N için eşleşmeler yakın değil.");
    return {
      scope_matches: scoped.length, with_odds: ranked.length, used: top.length,
      sim_mean: top.length ? top.reduce(function (a, r) { return a + r.sim; }, 0) / top.length : null, sim_min: minS,
      summary: summarize(D, top.map(function (r) { return r.i; })), top: top, warnings: warnings
    };
  }

  function dayToDate(D, day) {
    var d = new Date(Date.parse(D.meta.epoch + "T00:00:00Z") + day * 86400000);
    return d.toISOString().slice(0, 10);
  }

  root.Engine = { decode: decode, devig: devig, wilson: wilson, scopeIdx: scopeIdx, rankSimilar: rankSimilar, summarize: summarize, analyze: analyze, dayToDate: dayToDate, MISS: MISS };
  if (typeof module !== "undefined") module.exports = root.Engine;
})(typeof window !== "undefined" ? window : globalThis);
