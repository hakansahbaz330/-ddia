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


  /* ================= Piyasa -> Poisson (backend/app/models/market_poisson.py ile aynı) ================= */
  var MAXG = 10, HT_SHARE = 0.444, RHO = -0.05;
  function pmfRow(l) { var r = [Math.exp(-l)]; for (var k = 1; k <= MAXG; k++) r.push(r[k - 1] * l / k); return r; }
  function scoreMatrix(lh, la, rho) {
    var a = pmfRow(lh), b = pmfRow(la), m = [], t = 0, i, j;
    for (i = 0; i <= MAXG; i++) { m.push([]); for (j = 0; j <= MAXG; j++) m[i].push(a[i] * b[j]); }
    if (rho) {
      m[0][0] *= Math.max(0, 1 - lh * la * rho); m[0][1] *= 1 + lh * rho; m[1][0] *= 1 + la * rho; m[1][1] *= Math.max(0, 1 - rho);
    }
    for (i = 0; i <= MAXG; i++) for (j = 0; j <= MAXG; j++) t += m[i][j];
    for (i = 0; i <= MAXG; i++) for (j = 0; j <= MAXG; j++) m[i][j] /= t;
    return m;
  }
  function marketProbs(m) {
    var o = { "1": 0, X: 0, "2": 0, btts_yes: 0, hcs: 0, acs: 0 }, over = { 0.5: 0, 1.5: 0, 2.5: 0, 3.5: 0, 4.5: 0 };
    for (var i = 0; i <= MAXG; i++) for (var j = 0; j <= MAXG; j++) {
      var p = m[i][j];
      if (i > j) o["1"] += p; else if (i === j) o.X += p; else o["2"] += p;
      if (i > 0 && j > 0) o.btts_yes += p;
      if (j === 0) o.hcs += p; if (i === 0) o.acs += p;
      Object.keys(over).forEach(function (x) { if (i + j > +x) over[x] += p; });
    }
    o["1X"] = o["1"] + o.X; o["12"] = o["1"] + o["2"]; o.X2 = o.X + o["2"];
    Object.keys(over).forEach(function (x) { o["over_" + String(x).replace(".", "_")] = over[x]; });
    return o;
  }
  function topScores(m, k) {
    var all = [];
    for (var i = 0; i <= MAXG; i++) for (var j = 0; j <= MAXG; j++) all.push({ score: i + "-" + j, p: m[i][j] });
    return all.sort(function (a, b) { return b.p - a.p; }).slice(0, k || 8);
  }
  function nelderMead(f, x0, iters) {
    var n = x0.length, S = [x0.slice()], i, j;
    for (i = 0; i < n; i++) { var v = x0.slice(); v[i] += 0.25; S.push(v); }
    var F = S.map(f);
    for (var it = 0; it < (iters || 400); it++) {
      var ord = F.map(function (_, k) { return k; }).sort(function (a, b) { return F[a] - F[b]; });
      S = ord.map(function (k) { return S[k]; }); F = ord.map(function (k) { return F[k]; });
      if (Math.abs(F[n] - F[0]) < 1e-14) break;
      var c = new Array(n).fill(0);
      for (i = 0; i < n; i++) for (j = 0; j < n; j++) c[j] += S[i][j] / n;
      var mix = function (t) { return c.map(function (cj, j2) { return cj + t * (S[n][j2] - cj); }); };
      var xr = mix(-1), fr = f(xr);
      if (fr < F[0]) { var xe = mix(-2), fe = f(xe); if (fe < fr) { S[n] = xe; F[n] = fe; } else { S[n] = xr; F[n] = fr; } }
      else if (fr < F[n - 1]) { S[n] = xr; F[n] = fr; }
      else {
        var xc = mix(fr < F[n] ? -0.5 : 0.5), fc = f(xc);
        if (fc < Math.min(fr, F[n])) { S[n] = xc; F[n] = fc; }
        else for (i = 1; i <= n; i++) { S[i] = S[i].map(function (v2, j2) { return S[0][j2] + 0.5 * (v2 - S[0][j2]); }); F[i] = f(S[i]); }
      }
    }
    var b = 0; for (i = 1; i <= n; i++) if (F[i] < F[b]) b = i;
    return { x: S[b], f: F[b] };
  }
  function fitFromMarket(o1x2, ou, rho) {
    rho = rho === undefined ? RHO : rho;
    var p = devig(o1x2), tou = ou ? devig(ou)[0] : null;
    var loss = function (x) {
      var mp = marketProbs(scoreMatrix(Math.exp(x[0]), Math.exp(x[1]), rho));
      var e = Math.pow(mp["1"] - p[0], 2) + Math.pow(mp.X - p[1], 2) + Math.pow(mp["2"] - p[2], 2);
      if (tou !== null) e += Math.pow(mp.over_2_5 - tou, 2);
      return e;
    };
    var best = null;
    [[1.4, 1.1], [2.0, 0.8], [0.9, 1.6]].forEach(function (s0) {
      var r = nelderMead(loss, s0.map(Math.log), 600); if (!best || r.f < best.f) best = r;
    });
    return { lh: Math.exp(best.x[0]), la: Math.exp(best.x[1]), rho: rho, rmse: Math.sqrt(best.f / (tou !== null ? 4 : 3)), target: p };
  }
  function halfMarkets(lh, la) {
    var mp = marketProbs(scoreMatrix(lh * HT_SHARE, la * HT_SHARE, 0));
    return { ht_1: mp["1"], ht_x: mp.X, ht_2: mp["2"], ht_btts: mp.btts_yes, ht_o05: mp.over_0_5, ht_o15: mp.over_1_5, ht_o25: mp.over_2_5 };
  }

  /* ================= Bülten ayrıştırma (backend/app/providers/manual.py ile aynı kurallar) ================= */
  var SEPRE = /\s+(?:-|–|—|vs\.?|v)\s+/i;
  var DEC = /(?<![\w.,])\d{1,3}[.,]\d{1,2}(?![\w])/g;
  function htmlToText(src) {
    src = src.replace(/<(script|style|noscript)\b[\s\S]*?<\/\1>/gi, " ").replace(/<\/t[dh]>/gi, "\t")
      .replace(/<\/?(?:div|p|br|tr|li|ul|table|section|article|h\d|span|a)\b[^>]*>/gi, "\n").replace(/<[^>]+>/g, " ");
    return src.replace(/&amp;/g, "&").replace(/&nbsp;/g, " ").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'");
  }
  function isTeamLine(line) {
    var m = SEPRE.exec(line); if (!m) return false;
    return /[^\W\d_]/u.test(line.slice(0, m.index)) && /[^\W\d_]/u.test(line.slice(m.index + m[0].length));
  }
  function decs(t) { return t.match(DEC) || []; }
  function mergeMultiline(lines) {
    var out = [], i = 0;
    while (i < lines.length) {
      var ln = lines[i];
      if (isTeamLine(ln) && decs(ln).length < 3) {
        var parts = [ln], j = i + 1;
        while (j < lines.length && decs(parts.join(" ")).length < 5 && !isTeamLine(lines[j])) {
          var nums = decs(lines[j]); if (nums.length) parts.push(nums.join(" "));
          j++; if (j - i > 8) break;
        }
        out.push(parts.join(" ")); i = j;
      } else { out.push(ln); i++; }
    }
    return out;
  }
  function parseBulletin(text) {
    var matches = [], errors = [];
    if (/</.test(text) && /<\/?(?:html|body|div|table|tr|td|span)\b/i.test(text)) text = htmlToText(text);
    var rawLines = text.split(/\r?\n/).map(function (x) { return x.trim(); }).filter(Boolean);
    var PREFIX = /^\s*(?:\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?\s*)?(?:\d{1,2}:\d{2}\s*)?(?:\d{4,7}\s+)?/;
    mergeMultiline(rawLines).forEach(function (raw, k) {
      if (!/\d/.test(raw)) return; /* lig başlığı */
      var line = raw.replace(PREFIX, ""), m = SEPRE.exec(line);
      var bad = function (reason) { errors.push({ line: k + 1, text: raw.slice(0, 80), reason: reason }); };
      if (!m) return bad("Takım ayracı (-) bulunamadı");
      var home = line.slice(0, m.index).trim(), rest = line.slice(m.index + m[0].length);
      var NUM = /(?<![\w.,])(\d{1,3}(?:[.,]\d{1,3})?)(?![\w])/g, first = NUM.exec(rest);
      if (!first) return bad("Oran bulunamadı");
      var away = rest.slice(0, first.index).replace(/^[ \t;:]+|[ \t;:]+$/g, "");
      var nums = (rest.slice(first.index).match(/(?<![\w.,])(\d{1,3}(?:[.,]\d{1,3})?)(?![\w])/g) || []).map(function (x) { return parseFloat(x.replace(",", ".")); });
      if (!home || !away || nums.length < 3) return bad("En az 3 oran (1-X-2) ve iki takım adı gerekli");
      var o = nums.slice(0, 3), ou = nums.length >= 5 ? nums.slice(3, 5) : null;
      if (o.some(function (x) { return x <= 1; }) || (ou && ou.some(function (x) { return x <= 1; }))) return bad("Oranlar 1,00'dan büyük olmalı");
      matches.push({ home: home, away: away, odds: o, ou: ou });
    });
    return { matches: matches, errors: errors };
  }

  /* ================= Takım adı eşleme ================= */
  var STOP = { fc: 1, cf: 1, afc: 1, sc: 1, ac: 1, as: 1, ssc: 1, fk: 1, sk: 1, bk: 1, fsv: 1, vfb: 1, vfl: 1, tsg: 1, rb: 1, "1": 1, "04": 1, "05": 1, de: 1, the: 1 };
  function normName(s) {
    s = s.normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/ı/g, "i").replace(/İ/g, "i").toLowerCase().replace(/[^a-z0-9 ]/g, " ");
    return s.split(/\s+/).filter(function (t) { return t && !STOP[t]; }).join(" ");
  }
  function dice(a, b) {
    if (a === b) return 1; if (a.length < 2 || b.length < 2) return 0;
    var g = {}, i, n = 0; for (i = 0; i < a.length - 1; i++) { var k = a.slice(i, i + 2); g[k] = (g[k] || 0) + 1; }
    for (i = 0; i < b.length - 1; i++) { var k2 = b.slice(i, i + 2); if (g[k2] > 0) { g[k2]--; n++; } }
    return 2 * n / (a.length + b.length - 2);
  }
  function teamIndex(D) {
    if (D._tn) return D._tn;
    var T = D.meta.teams.map(function (t, i) { return { i: i, n: normName(t.name) }; }), last = new Int16Array(T.length).fill(-1);
    for (var i = 0; i < D.n; i++) { last[D.home[i]] = D.div[i]; last[D.away[i]] = D.div[i]; }
    D._tn = { T: T, last: last }; return D._tn;
  }
  /* Türkçe bülten yazımı -> arşiv adı (normalize edilmiş). Yalnızca doğrulanmış eşleşmeler. */
  var ALIAS = { "p thistle": "partick", "wolverhampton": "wolves", "mk dons": "milton keynes dons", "amed sportif faaliyetler": "amedspor", "queens park rangers": "qpr",
    "manchester city": "man city", "manchester united": "man united", "psv": "psv eindhoven", "airdrieonian": "airdrie utd", "marsilya": "marseille", "basaksehir": "buyuksehyr",
    "ayr united": "ayr", "nottingham forest": "nott'm forest" };
  var RESERVE = /\bu(?:17|18|19|20|21|23)\b|\bjong\b|(?<!willem )\bii\b|\biii\b|\([kwf]\)|\bkadin\b/i;
  function matchTeam(D, name) {
    if (RESERVE.test(name)) return -1; /* yedek/genç/kadın takımları birinci takımla karıştırılmaz */
    var tn = teamIndex(D), n = normName(name), best = -1, br = 0; n = ALIAS[n] ? normName(ALIAS[n]) : n;
    for (var k = 0; k < tn.T.length; k++) {
      var t = tn.T[k], r = t.n === n ? 1 : dice(n, t.n);
      if ((n.length >= 4 && t.n.length >= 4) && (t.n.indexOf(n) > -1 || n.indexOf(t.n) > -1)) r = Math.max(r, 0.9);
      if (r > br) { br = r; best = k; }
    }
    return br >= 0.82 ? best : -1;
  }


  /* ================= Lig bilinçli takım eşleme (bülten lig kodu -> arşiv ligi, veriden öğrenilir) ================= */
  function divTeams(D) {
    if (D._dt) return D._dt;
    var sets = D.meta.divs.map(function () { return {}; });
    for (var i = 0; i < D.n; i++) { sets[D.div[i]][D.home[i]] = 1; sets[D.div[i]][D.away[i]] = 1; }
    D._dt = sets.map(function (o) { return Object.keys(o).map(Number); }); return D._dt;
  }
  function scoreName(a, b) {
    var r = a === b ? 1 : dice(a, b);
    if (a.length >= 4 && b.length >= 4 && (a.indexOf(b) > -1 || b.indexOf(a) > -1)) r = Math.max(r, 0.9);
    var ta = a.split(" "), tb = b.split(" ");
    if (ta[0].length >= 4 && ta[0] === tb[0]) r = Math.max(r, 0.75);
    return r;
  }
  function matchTeamIn(D, name, divIdx) {
    if (RESERVE.test(name)) return -1;
    var tn = teamIndex(D), n = normName(name), best = -1, b1 = 0, b2 = 0; n = ALIAS[n] ? normName(ALIAS[n]) : n;
    divTeams(D)[divIdx].forEach(function (k) {
      var r = scoreName(n, tn.T[k].n);
      if (r > b1) { b2 = b1; b1 = r; best = k; } else if (r > b2) b2 = r;
    });
    return b1 >= 0.6 && b1 - b2 >= 0.06 ? best : -1;
  }
  /* items: [{league, home, away}] -> {kod: bölünme indeksi}. Kesin eşleşen takımların çoğunluk ligi, en az 3 oy ve %70 pay. */
  function learnLeagueDivisions(D, items) {
    var votes = {};
    items.forEach(function (m) {
      [m.home, m.away].forEach(function (nm) {
        var t = matchTeam(D, nm); if (t < 0) return; var dv = teamIndex(D).last[t]; if (dv < 0) return;
        var v = votes[m.league] = votes[m.league] || {}; v[dv] = (v[dv] || 0) + 1;
      });
    });
    var map = {};
    Object.keys(votes).forEach(function (code) {
      var tot = 0, best = -1, bv = 0; Object.keys(votes[code]).forEach(function (d) { tot += votes[code][d]; if (votes[code][d] > bv) { bv = votes[code][d]; best = +d; } });
      if (bv >= 3 && bv / tot >= 0.7) map[code] = best;
    });
    return map;
  }

  /* ================= Takım formu ve karşılıklı geçmiş (arşivden) ================= */
  function teamForm(D, team, n, venue) {
    var idx = [];
    for (var i = D.n - 1; i >= 0 && idx.length < n; i--) {
      if (D.fth[i] === MISS) continue;
      var h = D.home[i] === team, a = D.away[i] === team;
      if (!(venue === "home" ? h : venue === "away" ? a : (h || a))) continue;
      idx.push(i);
    }
    if (!idx.length) return { n: 0 };
    var f = { n: idx.length, gf: 0, ga: 0, pts: 0, w: 0, d: 0, l: 0, cs: 0, fts: 0, btts: 0, o25: 0, form: "", cor: 0, corN: 0, crd: 0, crdN: 0 };
    idx.forEach(function (i) {
      var home = D.home[i] === team, gf = home ? D.fth[i] : D.fta[i], ga = home ? D.fta[i] : D.fth[i];
      f.gf += gf; f.ga += ga; f.pts += gf > ga ? 3 : gf === ga ? 1 : 0; f.w += gf > ga; f.d += gf === ga; f.l += gf < ga;
      f.cs += ga === 0; f.fts += gf === 0; f.btts += gf > 0 && ga > 0; f.o25 += gf + ga > 2;
      f.form = (gf > ga ? "G" : gf === ga ? "B" : "M") + f.form;
      if (D.corners[i] !== MISS) { f.cor += D.corners[i]; f.corN++; }
      if (D.cards[i] !== MISS) { f.crd += D.cards[i]; f.crdN++; }
    });
    var n2 = f.n;
    return { n: n2, ppg: f.pts / n2, gf: f.gf / n2, ga: f.ga / n2, win: f.w / n2, draw: f.d / n2, loss: f.l / n2, cs: f.cs / n2, fts: f.fts / n2,
      btts: f.btts / n2, o25: f.o25 / n2, form: f.form, corners: f.corN ? f.cor / f.corN : null, cards: f.crdN ? f.crd / f.crdN : null };
  }
  function h2h(D, a, b, n) {
    var out = [];
    for (var i = D.n - 1; i >= 0 && out.length < n; i--) {
      if (D.fth[i] === MISS) continue;
      if ((D.home[i] === a && D.away[i] === b) || (D.home[i] === b && D.away[i] === a)) out.push(i);
    }
    return out;
  }


  /* ================= Bülten çok pazarlı modeli (backend/app/models/bulletin_model.py ile aynı) ================= */
  var TG = { tg_01: [0, 1], tg_23: [2, 3], tg_45: [4, 5], tg_6p: [6, 99] };
  var TG_KEYS = ["tg_01", "tg_23", "tg_45", "tg_6p"], HTFT = ["11", "10", "12", "01", "00", "02", "21", "20", "22"];
  function pairP(o, a, b) { return (o[a] && o[b]) ? devig([o[a], o[b]]) : null; }
  function fullTargets(o) {
    var p = devig([o.ms1, o.ms0, o.ms2]), t = [["ms1", p[0]], ["ms0", p[1]], ["ms2", p[2]]], q;
    if ((q = pairP(o, "ou25_ust", "ou25_alt"))) t.push(["over25", q[0]]);
    if ((q = pairP(o, "ou35_ust", "ou35_alt"))) t.push(["over35", q[0]]);
    if ((q = pairP(o, "kg_var", "kg_yok"))) t.push(["btts", q[0]]);
    if (TG_KEYS.every(function (k) { return o[k]; })) { var d = devig(TG_KEYS.map(function (k) { return o[k]; })); TG_KEYS.forEach(function (k, i) { t.push([k, d[i]]); }); }
    return t;
  }
  function mvalue(name, m, mp) {
    switch (name) {
      case "ms1": return mp["1"]; case "ms0": return mp.X; case "ms2": return mp["2"];
      case "over25": return mp.over_2_5; case "over35": return mp.over_3_5; case "btts": return mp.btts_yes;
    }
    var r = TG[name], s = 0;
    for (var i = 0; i <= MAXG; i++) for (var j = 0; j <= MAXG; j++) if (i + j >= r[0] && i + j <= r[1]) s += m[i][j];
    return s;
  }
  function htvalue(name, m, mp) { return { ht1: mp["1"], ht0: mp.X, ht2: mp["2"], ht15: mp.over_1_5 }[name]; }
  function fitTargets(targets, rho, vf, starts) {
    var loss = function (x) {
      var m = scoreMatrix(Math.exp(x[0]), Math.exp(x[1]), rho), mp = marketProbs(m), e = 0;
      targets.forEach(function (t) { e += Math.pow(vf(t[0], m, mp) - t[1], 2); });
      return e;
    }, best = null;
    starts.forEach(function (s0) { var r = nelderMead(loss, s0.map(Math.log), 800); if (!best || r.f < best.f) best = r; });
    return { lh: Math.exp(best.x[0]), la: Math.exp(best.x[1]), sse: best.f };
  }
  function symR(a, b) { return a > b ? "1" : a < b ? "2" : "0"; }
  function htftMatrix(l1h, l1a, l2h, l2a) {
    var h1 = scoreMatrix(l1h, l1a, 0), h2 = scoreMatrix(l2h, l2a, 0), out = {}, tot = 0, a, b, c, d;
    HTFT.forEach(function (k) { out[k] = 0; });
    for (a = 0; a <= MAXG; a++) for (b = 0; b <= MAXG; b++) {
      var p1 = h1[a][b]; if (p1 < 1e-9) continue; var s1 = symR(a, b);
      for (c = 0; c <= MAXG; c++) for (d = 0; d <= MAXG; d++) out[s1 + symR(a + c, b + d)] += p1 * h2[c][d];
    }
    HTFT.forEach(function (k) { tot += out[k]; }); HTFT.forEach(function (k) { out[k] /= tot; });
    return out;
  }
  function analyzeBulletinMatch(o) {
    var targets = fullTargets(o), f = fitTargets(targets, RHO, mvalue, [[1.4, 1.1], [2.0, 0.8], [0.9, 1.6]]);
    var lh = f.lh, la = f.la, m = scoreMatrix(lh, la, RHO), mp = marketProbs(m);
    var res = { lh: lh, la: la, rmse: Math.sqrt(f.sse / targets.length), nTargets: targets.length, marketsUsed: targets.map(function (t) { return t[0]; }), matrix: m, top: topScores(m, 10) };
    var ht = [], q;
    if (o.ht1 && o.ht0 && o.ht2) { var hp0 = devig([o.ht1, o.ht0, o.ht2]); ht.push(["ht1", hp0[0]], ["ht0", hp0[1]], ["ht2", hp0[2]]); }
    if ((q = pairP(o, "ht15_ust", "ht15_alt"))) ht.push(["ht15", q[0]]);
    var hl, ha;
    if (ht.length >= 3) { var hf = fitTargets(ht, 0, htvalue, [[0.6, 0.5], [0.9, 0.4], [0.4, 0.8]]); hl = hf.lh; ha = hf.la; res.htSource = "oranlardan (İY 1/0/2" + (ht.length === 4 ? " + 1,5 ü/a)" : ")"); }
    else { hl = lh * HT_SHARE; ha = la * HT_SHARE; res.htSource = "yaklaşık (gol payı %" + nf1(HT_SHARE * 100) + "; İY oranı yok)"; }
    hl = Math.min(hl, lh * 0.95); ha = Math.min(ha, la * 0.95);
    var mh = scoreMatrix(hl, ha, 0), hp = marketProbs(mh);
    res.htLh = hl; res.htLa = ha; res.htTop = topScores(mh, 6);
    res.htft = htftMatrix(hl, ha, Math.max(lh - hl, 0.05), Math.max(la - ha, 0.05));
    var rows = [];
    function impl(keys) { if (!keys.every(function (k) { return o[k]; })) return {}; var d = devig(keys.map(function (k) { return o[k]; })), r = {}; keys.forEach(function (k, i) { r[k] = d[i]; }); return r; }
    function add(group, label, key, pm, im) { if (o[key]) rows.push({ group: group, label: label, odds: o[key], implied: im === undefined ? null : im, model: pm, ev: pm * o[key] - 1 }); }
    var d = impl(["ms1", "ms0", "ms2"]);
    add("Maç sonucu", "MS 1", "ms1", mp["1"], d.ms1); add("Maç sonucu", "MS 0", "ms0", mp.X, d.ms0); add("Maç sonucu", "MS 2", "ms2", mp["2"], d.ms2);
    [["ou25_ust", "ou25_alt", "2,5", mp.over_2_5], ["ou35_ust", "ou35_alt", "3,5", mp.over_3_5]].forEach(function (l) {
      var dd = impl([l[0], l[1]]); add("Alt/Üst", l[2] + " Üst", l[0], l[3], dd[l[0]]); add("Alt/Üst", l[2] + " Alt", l[1], 1 - l[3], dd[l[1]]);
    });
    d = impl(["kg_var", "kg_yok"]); add("Karşılıklı gol", "KG Var", "kg_var", mp.btts_yes, d.kg_var); add("Karşılıklı gol", "KG Yok", "kg_yok", 1 - mp.btts_yes, d.kg_yok);
    d = impl(TG_KEYS); [["tg_01", "0-1 gol"], ["tg_23", "2-3 gol"], ["tg_45", "4-5 gol"], ["tg_6p", "6+ gol"]].forEach(function (x) { add("Toplam gol", x[1], x[0], mvalue(x[0], m, mp), d[x[0]]); });
    d = impl(["ht1", "ht0", "ht2"]); add("İlk yarı", "İY 1", "ht1", hp["1"], d.ht1); add("İlk yarı", "İY 0", "ht0", hp.X, d.ht0); add("İlk yarı", "İY 2", "ht2", hp["2"], d.ht2);
    d = impl(["ht15_ust", "ht15_alt"]); add("İlk yarı", "İY 1,5 Üst", "ht15_ust", hp.over_1_5, d.ht15_ust); add("İlk yarı", "İY 1,5 Alt", "ht15_alt", 1 - hp.over_1_5, d.ht15_alt);
    d = impl(HTFT.map(function (c) { return "htft_" + c; })); HTFT.forEach(function (c) { add("İY / MS", c[0] + "/" + c[1], "htft_" + c, res.htft[c], d["htft_" + c]); });
    var sr = { "1": function (i, j) { return i > j; }, "0": function (i, j) { return i === j; }, "2": function (i, j) { return i < j; } };
    ["1", "0", "2"].forEach(function (r) {
      var pa = 0, pu = 0;
      for (var i = 0; i <= MAXG; i++) for (var j = 0; j <= MAXG; j++) if (sr[r](i, j)) { if (i + j <= 2) pa += m[i][j]; else pu += m[i][j]; }
      add("MS ve 2,5", r + "/Alt", "msou_" + r + "a", pa); add("MS ve 2,5", r + "/Üst", "msou_" + r + "u", pu);
    });
    res.markets = rows; return res;
  }
  function nf1(x) { return x.toFixed(1).replace(".", ","); }


  /* ================= Lig bağlamı: puan durumu ve genel oranlar (arşivden) ================= */
  function standings(D, divIdx, seasonIdx) {
    var t = {}, i;
    for (i = 0; i < D.n; i++) {
      if (D.div[i] !== divIdx || D.season[i] !== seasonIdx || D.fth[i] === MISS) continue;
      var h = D.home[i], a = D.away[i], gh = D.fth[i], ga = D.fta[i];
      [[h, gh, ga], [a, ga, gh]].forEach(function (x) {
        var r = t[x[0]] = t[x[0]] || { team: x[0], p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, pts: 0 };
        r.p++; r.gf += x[1]; r.ga += x[2];
        if (x[1] > x[2]) { r.w++; r.pts += 3; } else if (x[1] === x[2]) { r.d++; r.pts += 1; } else r.l++;
      });
    }
    var rows = Object.keys(t).map(function (k) { return t[k]; });
    rows.sort(function (x, y) { return y.pts - x.pts || (y.gf - y.ga) - (x.gf - x.ga) || y.gf - x.gf; });
    rows.forEach(function (r, k) { r.rank = k + 1; });
    return rows;
  }
  function leagueContext(D, divIdx, seasonMin) {
    var n = 0, h = 0, d = 0, a = 0, g = 0, bt = 0, o = 0;
    for (var i = 0; i < D.n; i++) {
      if (D.div[i] !== divIdx || D.season[i] < seasonMin || D.fth[i] === MISS) continue;
      n++; var x = D.fth[i], y = D.fta[i];
      if (x > y) h++; else if (x === y) d++; else a++;
      g += x + y; if (x > 0 && y > 0) bt++; if (x + y > 2) o++;
    }
    return n ? { n: n, home: h / n, draw: d / n, away: a / n, goals: g / n, btts: bt / n, o25: o / n } : { n: 0 };
  }
  function lastDate(D, team) {
    for (var i = D.n - 1; i >= 0; i--) if (D.home[i] === team || D.away[i] === team) return D.day[i];
    return null;
  }

  /* ================= Otomatik kupon (Faz 7) ================= */
  /* cand: [{mi, match, league, group, label, odds, p, time, date}] */
  function buildCoupons(cands, o) {
    var k = o.legs, lo = o.minOdds, hi = o.maxOdds, minP = o.minP, maxP = o.maxP === undefined ? 1 : o.maxP;
    var perLeague = o.perLeague || 99, nOut = o.count || 3, maxShared = o.maxShared === undefined ? Math.max(0, k - 2) : o.maxShared;
    var pool = cands.filter(function (c) { return c.p >= minP && c.p <= maxP && c.odds >= (o.minLegOdds || 1.01) && (!o.groups || o.groups.indexOf(c.group) > -1); });
    var byMatch = {}; pool.forEach(function (c) { (byMatch[c.mi] = byMatch[c.mi] || []).push(c); });
    var ms = Object.keys(byMatch).map(function (m) {
      var arr = byMatch[m].sort(function (a, b) { return b.p - a.p; }).slice(0, 6); return { mi: +m, c: arr };
    });
    /* her bölmede (adet, log-oran kovası) en iyi birkaç kısmi kupon; hedef: ortak olasılık */
    var step = 0.12, states = [{ legs: [], lp: 0, lo: 0, lg: {} }], levels = {};
    function key(s) { return s.legs.length + ":" + Math.round(s.lo / step); }
    var buckets = {}; buckets[key(states[0])] = [states[0]];
    ms.sort(function (a, b) { return Math.max.apply(null, b.c.map(function (x) { return x.p; })) - Math.max.apply(null, a.c.map(function (x) { return x.p; })); });
    ms.forEach(function (m) {
      var add = [];
      Object.keys(buckets).forEach(function (kk) {
        buckets[kk].forEach(function (s) {
          if (s.legs.length >= k) return;
          m.c.forEach(function (c) {
            if ((s.lg[c.league] || 0) >= perLeague) return;
            var lg = Object.assign({}, s.lg); lg[c.league] = (lg[c.league] || 0) + 1;
            add.push({ legs: s.legs.concat([c]), lp: s.lp + Math.log(c.p), lo: s.lo + Math.log(c.odds), lg: lg });
          });
        });
      });
      add.forEach(function (s) {
        var kk = key(s), b = buckets[kk] = buckets[kk] || [];
        b.push(s); b.sort(function (x, y) { return y.lp - x.lp; }); if (b.length > 4) b.length = 4;
      });
    });
    var finals = [];
    Object.keys(buckets).forEach(function (kk) { buckets[kk].forEach(function (s) { if (s.legs.length === k) { var t = Math.exp(s.lo); if (t >= lo && t <= hi) finals.push(s); } }); });
    finals.sort(function (a, b) { return b.lp - a.lp; });
    var out = [];
    finals.forEach(function (s) {
      if (out.length >= nOut) return;
      var ids = s.legs.map(function (c) { return c.mi + "|" + c.label; });
      var ok = out.every(function (t) { var shared = 0; t.legs.forEach(function (c) { if (ids.indexOf(c.mi + "|" + c.label) > -1) shared++; }); return shared <= maxShared; });
      if (ok) out.push({ legs: s.legs.slice().sort(function (a, b) { return (a.date + a.time) < (b.date + b.time) ? -1 : 1; }), p: Math.exp(s.lp), odds: Math.exp(s.lo) });
    });
    out.forEach(function (c) { c.ev = c.p * c.odds - 1; c.leagues = {}; c.legs.forEach(function (l) { c.leagues[l.league] = (c.leagues[l.league] || 0) + 1; }); });
    return { coupons: out, poolSize: pool.length, matchesInPool: ms.length, feasible: finals.length };
  }

  /* ================= Tek maç otomatik analizi ================= */
  function strengthLambdas(D, h, a) {
    var S = D.meta.strength; if (!S || h < 0 || a < 0) return null;
    var tn = teamIndex(D), dv = tn.last[h]; if (dv < 0) return null;
    var base = S.base[D.meta.divs[dv].code]; if (base === undefined) return null;
    return { lh: Math.exp(base + S.home + S.att[h] - S.def[a]), la: Math.exp(base + S.att[a] - S.def[h]) };
  }
  function analyzeMatch(D, q, hIdx, aIdx, fitOv) {
    var fit = fitOv || fitFromMarket(q.odds, q.ou), mM = scoreMatrix(fit.lh, fit.la, RHO), warn = [];
    var res = { fit: fit, market: marketProbs(mM), mMatrix: mM, half: halfMarkets(fit.lh, fit.la), warnings: warn, hIdx: hIdx, aIdx: aIdx };
    if (fit.rmse > 0.03) warn.push("Piyasa oranları tek bir Poisson dağılımına zor uyuyor (uyum hatası yüksek); oranları kontrol edin.");
    if (!q.ou) warn.push("2,5 üst/alt oranı girilmedi: toplam gol beklentisi yalnızca 1X2'den çıkarıldı, daha belirsiz.");
    var wM = D.meta.strength ? D.meta.strength.w_market : 1, matrix = mM, sl = strengthLambdas(D, hIdx, aIdx);
    res.wMarket = wM;
    if (sl) {
      var mS = scoreMatrix(sl.lh, sl.la, RHO), sp = marketProbs(mS); res.strength = { lh: sl.lh, la: sl.la, market: sp };
      matrix = mM.map(function (row, i) { return row.map(function (v, j) { return wM * v + (1 - wM) * mS[i][j]; }); });
      var keys = ["1", "X", "2", "over_2_5", "btts_yes"], mx = 0;
      keys.forEach(function (k) { mx = Math.max(mx, Math.abs(res.market[k] - sp[k])); });
      res.disagree = { max: mx, flag: mx > 0.08 };
      if (res.disagree.flag) warn.push("Piyasa ve arşiv güç modeli belirgin ayrışıyor (%8 puandan fazla). Sakatlık/rotasyon gibi arşivde olmayan bir bilgi olabilir.");
    } else if (hIdx < 0 || aIdx < 0) warn.push("Takımlardan biri arşivde bulunamadı: güç modeli, form ve karşılıklı geçmiş yok.");
    res.matrix = matrix; res.combined = marketProbs(matrix); res.top = topScores(matrix, 8);
    if (hIdx >= 0 && aIdx >= 0) {
      res.form = { h: teamForm(D, hIdx, 10, "any"), hh: teamForm(D, hIdx, 10, "home"), a: teamForm(D, aIdx, 10, "any"), aa: teamForm(D, aIdx, 10, "away") };
      res.h2h = h2h(D, hIdx, aIdx, 10);
    }
    var sim = analyze(D, q, { kind: "all" }, { topN: 50 }); res.similar = sim;
    return res;
  }

  root.Engine = { decode: decode, devig: devig, wilson: wilson, scopeIdx: scopeIdx, rankSimilar: rankSimilar, summarize: summarize, analyze: analyze, dayToDate: dayToDate, MISS: MISS, fitFromMarket: fitFromMarket, scoreMatrix: scoreMatrix, marketProbs: marketProbs, topScores: topScores,
    matchTeamIn: matchTeamIn, standings: standings, leagueContext: leagueContext, lastDate: lastDate, buildCoupons: buildCoupons, learnLeagueDivisions: learnLeagueDivisions, halfMarkets: halfMarkets, analyzeBulletinMatch: analyzeBulletinMatch, parseBulletin: parseBulletin, matchTeam: matchTeam, teamForm: teamForm, h2h: h2h, analyzeMatch: analyzeMatch, normName: normName };
  if (typeof module !== "undefined") module.exports = root.Engine;
})(typeof window !== "undefined" ? window : globalThis);
