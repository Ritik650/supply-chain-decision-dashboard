// Supply Chain Decision Dashboard: loads valid order items as typed arrays, applies the global
// filters in the browser and computes every KPI with the definitions in docs/kpi_definitions.md.
'use strict';

const { lineChart, barChart, ramp, tip } = window.charts;

const fmt = {
  money(v) {
    const a = Math.abs(v), s = v < 0 ? '−$' : '$';
    if (a >= 1e6) return `${s}${(a / 1e6).toFixed(2)}M`;
    if (a >= 1e4) return `${s}${(a / 1e3).toFixed(0)}k`;
    if (a >= 1e3) return `${s}${(a / 1e3).toFixed(1)}k`;
    return `${s}${a.toFixed(0)}`;
  },
  axisMoney(v) {
    const a = Math.abs(v);
    if (a >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
    if (a >= 1e3) return `$${(v / 1e3).toFixed(0)}k`;
    return `$${v.toFixed(0)}`;
  },
  usd: v => `$${v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
  pct: (v, d = 1) => Number.isFinite(v) ? `${(v * 100).toFixed(d)}%` : 'n/a',
  int: v => Math.round(v).toLocaleString('en-US'),
  pts: (v, d = 1) => `${v >= 0 ? '+' : '−'}${Math.abs(v * 100).toFixed(d)} pts`,
  chg: v => Number.isFinite(v) ? `${v >= 0 ? '+' : '−'}${Math.abs(v * 100).toFixed(1)}%` : 'n/a',
  month(ym) { const [y, m] = ym.split('-'); return `${'JanFebMarAprMayJunJulAugSepOctNovDec'.substr((m - 1) * 3, 3)} ${y.slice(2)}`; },
};
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const $ = id => document.getElementById(id);
const css = name => `var(--${name})`;
const BAD_RAMP = ['#f6f5f2', '#f2b8b5', '#e5716e', '#d03b3b', '#7f1d1d'];
const GREY_RAMP = ['#f6f5f2', '#d6d4ce', '#a8a69f', '#6b6a65', '#3f3e3b'];
const BANDS = [['0-5%', 0, 0.05], ['5-10%', 0.05, 0.10], ['10-15%', 0.10, 0.15], ['15-20%', 0.15, 0.20], ['20-25%', 0.20, 0.26]];

let M, C, N, IDX;
const S = { page: 'summary', f: null, cap: 10 };
const defaults = () => ({ from: 0, to: M.dicts.months.indexOf(M.window.end), market: -1, segment: -1, category: -1 });

// ---------- data ----------
async function load() {
  const [meta, buf] = await Promise.all([
    fetch('data/meta.json').then(r => r.json()),
    fetch('data/items.bin').then(r => r.arrayBuffer()),
  ]);
  M = meta; N = meta.rows; C = {};
  const T = { float32: Float32Array, uint32: Uint32Array, uint16: Uint16Array, uint8: Uint8Array };
  for (const col of meta.layout) C[col.name] = new T[col.dtype](buf, col.offset, N);
  M.promisedArr = Uint8Array.from(meta.promised_days);
}

function applyFilters() {
  const { from, to, market, segment, category } = S.f;
  const out = new Uint32Array(N);
  const mo = C.month, mk = C.market, sg = C.segment, ct = C.category;
  let k = 0;
  for (let i = 0; i < N; i++) {
    const m = mo[i];
    if (m < from || m > to) continue;
    if (market >= 0 && mk[i] !== market) continue;
    if (segment >= 0 && sg[i] !== segment) continue;
    if (category >= 0 && ct[i] !== category) continue;
    out[k++] = i;
  }
  IDX = out.subarray(0, k);
  $('rowcount').textContent = `${fmt.int(k)} order items`;
}

const isLate = (i, promise = M.promisedArr) => C.actual_days[i] > promise[C.mode[i]];

function totals(idx = IDX) {
  let rev = 0, prof = 0, late = 0, disc = 0, sales = 0, orders = 0, prev = -1, delaySum = 0;
  for (const i of idx) {
    rev += C.item_total[i]; prof += C.profit[i]; sales += C.sales[i];
    if (isLate(i)) { late++; delaySum += C.actual_days[i] - M.promisedArr[C.mode[i]]; }
    if (C.order[i] !== prev) { orders++; prev = C.order[i]; }
  }
  disc = sales - rev;
  const n = idx.length;
  return { n, rev, prof, margin: prof / rev, late, lateRate: late / n, orders, aov: rev / orders, disc,
           avgDelay: delaySum / late };
}

function monthly() {
  const nM = M.dicts.months.length;
  const a = { rev: new Float64Array(nM), prof: new Float64Array(nM), n: new Uint32Array(nM), late: new Uint32Array(nM),
              orders: new Uint32Array(nM) };
  let prev = -1;
  for (const i of IDX) {
    const m = C.month[i];
    a.rev[m] += C.item_total[i]; a.prof[m] += C.profit[i]; a.n[m]++;
    if (isLate(i)) a.late[m]++;
    if (C.order[i] !== prev) { a.orders[m]++; prev = C.order[i]; }
  }
  return a;
}

const monthsSelected = () => S.f.to - S.f.from + 1;
const rate = i => C.rate_milli[i] / 1000;

// ---------- shared UI ----------
function kpiTiles(host, tiles) {
  host.innerHTML = tiles.map(t => `
    <div class="card kpi">
      <div class="label">${t.label}</div>
      <div class="value${t.bad ? ' bad' : ''}">${t.value}</div>
      <div class="delta${t.deltaBad ? ' bad' : ''}">${t.delta || '&nbsp;'}</div>
    </div>`).join('');
}

function takeaway(kicker, head, body, bad) {
  $('tkKicker').textContent = kicker;
  $('tkHead').textContent = head;
  $('tkBody').textContent = body;
  $('takeaway').classList.toggle('bad', !!bad);
}

function table(host, cols, rows, onClick) {
  const head = cols.map(c => `<th class="${c.num ? 'num' : ''}">${c.label}</th>`).join('');
  const body = rows.map((r, ri) => `<tr${onClick ? ` class="click" data-i="${ri}"` : ''}>${cols.map(c => {
    const v = c.html ? c.html(r) : esc(c.fmt ? c.fmt(r[c.key], r) : r[c.key]);
    const cls = [c.num ? 'num' : '', c.bad && c.bad(r) ? 'bad' : ''].join(' ').trim();
    return `<td class="${cls}">${v}</td>`;
  }).join('')}</tr>`).join('');
  host.innerHTML = `<table class="data"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  if (onClick) host.querySelectorAll('tr.click').forEach(tr => tr.addEventListener('click', () => onClick(rows[+tr.dataset.i])));
}

const inbar = (v, max, bad, label) =>
  `<span class="inbar">${label}<i class="${bad ? 'bad' : ''}" style="width:${Math.max(1, 70 * v / (max || 1))}px"></i></span>`;

// ---------- page 1: executive summary ----------
function capRecovery(cap, idx = IDX) {
  const beta = M.whatif.beta_central, el = M.whatif.price_elasticity_low;
  let hi = 0, cen = 0, lo = 0, items = 0, affProfit = 0, overCap = 0;
  for (const i of idx) {
    const r = rate(i);
    if (r <= cap + 1e-9) continue;
    items++;
    const p = C.profit[i], up = (r - cap) * C.sales[i], np = p + up;
    hi += up; overCap += up;
    cen += np * Math.exp(beta * (cap - r)) - p;
    lo += np * Math.max(0, 1 + el * (r - cap) / (1 - r)) - p;
    affProfit += p;
  }
  const k = 12 / monthsSelected();
  return { items, hi: hi * k, cen: cen * k, lo: lo * k, overCapWindow: overCap, breakeven: hi / (affProfit + hi) };
}

function byMode(promise = M.promisedArr) {
  const nm = M.dicts.modes.length;
  const n = new Uint32Array(nm), late = new Uint32Array(nm), days = new Float64Array(nm), delay = new Float64Array(nm);
  for (const i of IDX) {
    const m = C.mode[i]; n[m]++; days[m] += C.actual_days[i];
    if (C.actual_days[i] > promise[m]) { late[m]++; delay[m] += C.actual_days[i] - promise[m]; }
  }
  return M.dicts.modes.map((name, m) => ({ name, m, n: n[m], late: late[m], lateRate: late[m] / n[m],
    avgDays: days[m] / n[m], avgDelay: delay[m] / late[m], promised: promise[m] }));
}

function renderSummary() {
  const t = totals(), mo = monthly();
  const last = S.f.to, prev = S.f.to - 1;
  const has = prev >= S.f.from && mo.n[prev] > 0 && mo.n[last] > 0;
  const lbl = has ? ` vs ${fmt.month(M.dicts.months[prev])}` : '';
  const ch = (a, b) => has ? fmt.chg(a / b - 1) + lbl : 'single month selected';
  const lateNow = mo.late[last] / mo.n[last], latePrev = mo.late[prev] / mo.n[prev];
  kpiTiles($('sumKpis'), [
    { label: 'Revenue', value: fmt.money(t.rev), delta: `${fmt.money(mo.rev[last])} in ${fmt.month(M.dicts.months[last])}, ${ch(mo.rev[last], mo.rev[prev])}` },
    { label: 'Profit', value: fmt.money(t.prof), delta: ch(mo.prof[last], mo.prof[prev]) },
    { label: 'Profit margin', value: fmt.pct(t.margin), delta: has ? fmt.pts(mo.prof[last] / mo.rev[last] - mo.prof[prev] / mo.rev[prev]) + lbl : '' },
    { label: 'Late-delivery rate', value: fmt.pct(t.lateRate), bad: true,
      delta: has ? fmt.pts(lateNow - latePrev) + lbl : '', deltaBad: has && lateNow > latePrev },
    { label: 'Orders', value: fmt.int(t.orders), delta: ch(mo.orders[last], mo.orders[prev]) },
    { label: 'Avg order value', value: fmt.usd(t.aov), delta: ch(mo.rev[last] / mo.orders[last], mo.rev[prev] / mo.orders[prev]) },
  ]);
  const months = M.dicts.months.slice(S.f.from, S.f.to + 1);
  lineChart($('sumTrend'), {
    labels: months.map(fmt.month),
    series: [
      { name: 'Revenue', values: Array.from(mo.rev.slice(S.f.from, S.f.to + 1)), color: css('mark-2') },
      { name: 'Profit', values: Array.from(mo.prof.slice(S.f.from, S.f.to + 1)), color: css('mark') },
    ],
    yFmt: fmt.axisMoney, yLabel: 'USD per month', yMin: 0, height: 280,
  });
  const modes = byMode().filter(d => d.n > 0).sort((a, b) => b.lateRate - a.lateRate);
  const worst = modes[0];
  const cap = capRecovery(0.10);
  let lossN = 0, lossAmt = 0, qLo = 0, nLo = 0, qHi = 0, nHi = 0;
  for (const i of IDX) {
    if (C.profit[i] < 0) { lossN++; lossAmt += C.profit[i]; }
    if (rate(i) > 0.10 + 1e-9) { qHi += C.quantity[i]; nHi++; } else { qLo += C.quantity[i]; nLo++; }
  }
  const alerts = [];
  if (worst) alerts.push([`${worst.name} late on ${fmt.pct(worst.lateRate, 0)} of items`,
    `Promises ${worst.promised} day${worst.promised === 1 ? '' : 's'}; takes ${worst.avgDays.toFixed(2)} on average across ${fmt.int(worst.n)} items. Page 2.`]);
  alerts.push([`${fmt.money(cap.overCapWindow * 12 / monthsSelected())} a year discounted above 10%`,
    `${fmt.pct(cap.items / t.n, 0)} of items; they sell ${(qHi / nHi).toFixed(2)} units per line vs ${(qLo / nLo).toFixed(2)} at or below 10%. Page 3.`]);
  alerts.push([`${fmt.pct(lossN / t.n)} of order lines lose money`,
    `${fmt.money(-lossAmt)} lost on those lines, spread evenly across products and discount bands. Page 5.`]);
  $('sumAlerts').innerHTML = alerts.map((a, k) => `<li><span class="n">${k + 1}</span><div><b>${esc(a[0])}</b><span>${esc(a[1])}</span></div></li>`).join('');
  takeaway('Executive summary',
    `${fmt.pct(t.lateRate, 0)} of items arrive late, and discounts above 10% cost ${fmt.money(cap.cen)} a year without selling more.`,
    `Lateness comes from what each shipping mode promises, not from where it ships; the discount cap is the largest profit lever (central estimate, ${fmt.money(cap.lo)} to ${fmt.money(cap.hi)} a year). Margin is ${fmt.pct(t.margin)} on ${fmt.money(t.rev)} of revenue over ${monthsSelected()} months.`,
    true);
  return { totals: t };
}

// ---------- page 2: delivery ----------
function renderDelivery() {
  const t = totals();
  const modes = byMode();
  const present = modes.filter(d => d.n > 0);
  kpiTiles($('delKpis'), [
    { label: 'Late-delivery rate', value: fmt.pct(t.lateRate), bad: true, delta: `${fmt.int(t.late)} of ${fmt.int(t.n)} items` },
    { label: 'On-time or early', value: fmt.pct(1 - t.lateRate), delta: 'actual days ≤ promised days' },
    { label: 'Avg delay (late items)', value: `${t.avgDelay.toFixed(2)} days`, delta: 'actual − promised, late items only' },
    { label: 'Worst mode', value: present.length ? present.reduce((a, b) => a.lateRate > b.lateRate ? a : b).name : 'n/a', bad: true,
      delta: present.length ? `${fmt.pct(present.reduce((a, b) => a.lateRate > b.lateRate ? a : b).lateRate, 0)} late` : '' },
  ]);

  // small multiples: actual days distribution per mode
  const dist = M.dicts.modes.map(() => new Uint32Array(7));
  for (const i of IDX) dist[C.mode[i]][C.actual_days[i]]++;
  const host = $('delDist'); host.innerHTML = '';
  for (const d of modes) {
    const box = document.createElement('div');
    box.innerHTML = `<h4>${esc(d.name)}</h4><div class="sm-sub">promise ${d.promised}d · ${d.n ? fmt.pct(d.lateRate, 0) + ' late' : 'no items'}</div><div></div>`;
    host.appendChild(box);
    const shares = Array.from(dist[d.m], v => d.n ? v / d.n : 0);
    barChart(box.lastChild, {
      labels: ['0', '1', '2', '3', '4', '5', '6'], values: shares,
      colors: shares.map((_, k) => k > d.promised ? css('bad') : css('mark')),
      yFmt: v => fmt.pct(v, 0), yMax: 1, height: 170, refX: d.promised + 1, xLabel: 'actual days',
      tips: shares.map((s, k) => `<b>${esc(d.name)}, ${k} days</b><div>${fmt.pct(s)} of items${k > d.promised ? ' (late)' : ''}</div>`),
    });
  }

  // heatmap mode x region
  const nr = M.dicts.regions.length, nm = M.dicts.modes.length;
  const cn = new Uint32Array(nr * nm), cl = new Uint32Array(nr * nm);
  for (const i of IDX) { const k = C.region[i] * nm + C.mode[i]; cn[k]++; if (isLate(i)) cl[k]++; }
  const rows = M.dicts.regions.map((name, r) => {
    const cells = M.dicts.modes.map((_, m) => cn[r * nm + m] >= 200 ? cl[r * nm + m] / cn[r * nm + m] : null);
    const tot = M.dicts.modes.reduce((s, _, m) => s + cn[r * nm + m], 0);
    const lt = M.dicts.modes.reduce((s, _, m) => s + cl[r * nm + m], 0);
    return { name, cells, tot, avg: lt / tot };
  }).filter(r => r.cells.some(c => c !== null)).sort((a, b) => b.avg - a.avg);
  $('delHeat').innerHTML = `<table class="heat"><thead><tr><th>Region</th>${M.dicts.modes.map(m => `<th class="col">${esc(m)}</th>`).join('')}</tr></thead><tbody>${
    rows.map(r => `<tr><th>${esc(r.name)}</th>${r.cells.map((v, m) => v === null ? '<td class="empty">·</td>' :
      `<td style="background:${ramp(BAD_RAMP, v)};color:${v > 0.6 ? '#fff' : '#111110'}" title="${esc(r.name)} · ${esc(M.dicts.modes[m])}: ${fmt.pct(v)} late of ${fmt.int(cn[M.dicts.regions.indexOf(r.name) * nm + m])} items">${fmt.pct(v, 0)}</td>`).join('')}</tr>`).join('')
  }</tbody></table>`;
  $('delScale').style.background = `linear-gradient(90deg, ${BAD_RAMP.join(',')})`;

  table($('delModeTable'), [
    { label: 'Mode', key: 'name' },
    { label: 'Promise', key: 'promised', num: true, fmt: v => `${v}d` },
    { label: 'Actual', key: 'avgDays', num: true, fmt: v => Number.isFinite(v) ? `${v.toFixed(2)}d` : 'n/a' },
    { label: 'On time', key: 'lateRate', num: true, fmt: v => fmt.pct(1 - v, 0) },
    { label: 'Late', key: 'lateRate', num: true, fmt: v => fmt.pct(v, 1), bad: () => true },
    { label: 'Items', key: 'n', num: true, fmt: fmt.int },
  ], present);

  renderPromiseWhatif(t);

  // trend
  const nM = M.dicts.months.length;
  const mn = M.dicts.modes.map(() => new Uint32Array(nM)), ml = M.dicts.modes.map(() => new Uint32Array(nM));
  const an = new Uint32Array(nM), al = new Uint32Array(nM);
  for (const i of IDX) { const m = C.month[i], md = C.mode[i]; mn[md][m]++; an[m]++; if (isLate(i)) { ml[md][m]++; al[m]++; } }
  const range = [...Array(S.f.to - S.f.from + 1).keys()].map(k => k + S.f.from);
  lineChart($('delTrend'), {
    labels: range.map(m => fmt.month(M.dicts.months[m])),
    series: [
      ...M.dicts.modes.map((name, md) => ({ name, values: range.map(m => mn[md][m] >= 30 ? ml[md][m] / mn[md][m] : NaN), color: css('mark'), width: 1.5 }))
        .filter(s => s.values.some(Number.isFinite)),
      { name: 'All modes', values: range.map(m => an[m] ? al[m] / an[m] : NaN), color: css('bad'), width: 2.5 },
    ],
    yFmt: v => fmt.pct(v, 0), yLabel: 'late rate (% of items)', yMin: 0, yMax: 1, height: 260, endLabels: true,
  });
  const fc = present.find(d => d.name === 'First Class');
  const head = fc && fc.lateRate > 0.95
    ? `First Class is late on ${fmt.pct(fc.lateRate, 0)} of items: it always ships in ${fc.avgDays.toFixed(0)} days against a ${fc.promised}-day promise.`
    : `${fmt.pct(t.lateRate, 0)} of items arrive later than promised.`;
  const sc = present.find(d => d.name === 'Second Class'), st = present.find(d => d.name === 'Standard Class');
  takeaway('Delivery performance · Q1', head,
    sc && st ? `Second Class takes ${sc.avgDays.toFixed(2)} days on average, no faster than Standard Class (${st.avgDays.toFixed(2)}), yet promises 2 days, so ${fmt.pct(sc.lateRate, 0)} of it is late. Regions barely differ: fix the promise per mode.` :
      'Late rates differ by shipping mode, not by region.', true);
  return { modes: present };
}

function renderPromiseWhatif(t) {
  const promise = Uint8Array.from(M.promisedArr);
  const fi = M.dicts.modes.indexOf('First Class'), si = M.dicts.modes.indexOf('Second Class');
  promise[fi] = +$('pFirst').value; promise[si] = +$('pSecond').value;
  let late = 0;
  for (const i of IDX) if (C.actual_days[i] > promise[C.mode[i]]) late++;
  const nr = late / IDX.length;
  $('delWhatif').innerHTML = `
    <span class="lbl">Late rate today</span><span class="v">${fmt.pct(t.lateRate)}</span>
    <span class="lbl">With these promises</span><span class="v big">${fmt.pct(nr)}</span>
    <span class="lbl">Change</span><span class="v">${fmt.pts(nr - t.lateRate)}</span>`;
}

// ---------- page 3: discounts ----------
function bandStats() {
  const b = BANDS.map(([name]) => ({ name, n: 0, rev: 0, prof: 0, sales: 0, qty: 0 }));
  for (const i of IDX) {
    const r = rate(i);
    const k = r < 0.05 - 1e-9 ? 0 : r < 0.10 - 1e-9 ? 1 : r < 0.15 - 1e-9 ? 2 : r < 0.20 - 1e-9 ? 3 : 4;
    const x = b[k]; x.n++; x.rev += C.item_total[i]; x.prof += C.profit[i]; x.sales += C.sales[i]; x.qty += C.quantity[i];
  }
  b.forEach(x => { x.margin = x.prof / x.rev; x.avgQty = x.qty / x.n; x.disc = x.sales - x.rev; });
  return b;
}

let whatifCurve = null;
function renderDiscounts() {
  const t = totals();
  const bands = bandStats();
  const cap10 = capRecovery(0.10);
  let qLo = 0, nLo = 0, qHi = 0, nHi = 0, pLo = 0, rLo = 0, pHi = 0, rHi = 0;
  for (const i of IDX) {
    if (rate(i) > 0.10 + 1e-9) { qHi += C.quantity[i]; nHi++; pHi += C.profit[i]; rHi += C.item_total[i]; }
    else { qLo += C.quantity[i]; nLo++; pLo += C.profit[i]; rLo += C.item_total[i]; }
  }
  kpiTiles($('disKpis'), [
    { label: 'Profit margin', value: fmt.pct(t.margin), delta: `${fmt.pct(pLo / rLo)} at ≤10% vs ${fmt.pct(pHi / rHi)} above` },
    { label: 'Discount spend', value: fmt.money(t.disc), delta: `${fmt.pct(t.disc / (t.disc + t.rev))} of gross sales` },
    { label: 'Discount above 10%', value: fmt.money(cap10.overCapWindow), bad: true, delta: `${fmt.int(cap10.items)} items (${fmt.pct(cap10.items / t.n, 0)})` },
    { label: 'Units per line', value: `${(qHi / nHi).toFixed(2)} vs ${(qLo / nLo).toFixed(2)}`, delta: 'above 10% vs at or below' },
  ]);
  const valid = bands.filter(b => b.n > 0);
  barChart($('disMargin'), {
    labels: valid.map(b => b.name), values: valid.map(b => b.margin), colors: valid.map(() => css('mark')),
    yFmt: v => fmt.pct(v, 0), valueFmt: v => fmt.pct(v, 1), yLabel: 'profit ÷ net revenue', xLabel: 'discount band (applied rate)', valueLabels: true, height: 240,
    tips: valid.map(b => `<b>${b.name}</b><div>Margin ${fmt.pct(b.margin)}</div><div>${fmt.int(b.n)} items · ${fmt.money(b.rev)} revenue</div><div>Discount spend ${fmt.money(b.disc)}</div>`),
  });
  barChart($('disQty'), {
    labels: valid.map(b => b.name), values: valid.map(b => b.avgQty), colors: valid.map(() => css('mark')),
    yFmt: v => v.toFixed(2), yLabel: 'units per order line', xLabel: 'discount band (applied rate)', valueLabels: true, height: 240,
  });

  // what-if curve for caps 0..25 (computed once per filter change; the slider only reads it)
  whatifCurve = Array.from({ length: 26 }, (_, c) => capRecovery(c / 100));
  $('betaTxt').textContent = `${M.whatif.beta_estimate.toFixed(3)}, 95% CI ${M.whatif.beta_ci[0].toFixed(3)} to ${M.whatif.beta_ci[1].toFixed(3)}`;
  renderCap();

  // category drill-down
  const nc = M.dicts.categories.length;
  const cs = Array.from({ length: nc }, (_, k) => ({ k, name: M.dicts.categories[k], n: 0, pLo: 0, rLo: 0, pHi: 0, rHi: 0, qLo: 0, nLo: 0, qHi: 0, nHi: 0, over: 0 }));
  for (const i of IDX) {
    const c = cs[C.category[i]], r = rate(i);
    c.n++;
    if (r > 0.10 + 1e-9) { c.pHi += C.profit[i]; c.rHi += C.item_total[i]; c.qHi += C.quantity[i]; c.nHi++; c.over += (r - 0.10) * C.sales[i]; }
    else { c.pLo += C.profit[i]; c.rLo += C.item_total[i]; c.qLo += C.quantity[i]; c.nLo++; }
  }
  const minItems = S.f.category >= 0 ? 1 : 500;
  const rows = cs.filter(c => c.n >= minItems && c.nHi && c.nLo).map(c => ({ ...c, mLo: c.pLo / c.rLo, mHi: c.pHi / c.rHi, gap: c.pHi / c.rHi - c.pLo / c.rLo }))
    .sort((a, b) => b.over - a.over);
  table($('disCat'), [
    { label: 'Category', key: 'name' },
    { label: 'Items', key: 'n', num: true, fmt: fmt.int },
    { label: 'Margin ≤10%', key: 'mLo', num: true, fmt: v => fmt.pct(v) },
    { label: 'Margin >10%', key: 'mHi', num: true, fmt: v => fmt.pct(v) },
    { label: 'Gap', key: 'gap', num: true, fmt: v => fmt.pts(v), bad: r => r.gap < -0.01 },
    { label: 'Units ≤10% / >10%', key: 'qLo', num: true, fmt: (_, r) => `${(r.qLo / r.nLo).toFixed(2)} / ${(r.qHi / r.nHi).toFixed(2)}` },
    { label: 'Discount above 10%', key: 'over', num: true, html: r => inbar(r.over, rows[0].over, true, fmt.money(r.over)) },
  ], rows, r => { S.f.category = r.k; syncFilterControls(); refresh(); });

  takeaway('Discounts and margin · Q2',
    `Items discounted above 10% sell ${(qHi / nHi).toFixed(2)} units per line vs ${(qLo / nLo).toFixed(2)} at or below: the extra discount buys no volume.`,
    `Capping discounts at 10% recovers an estimated ${fmt.money(cap10.lo)} to ${fmt.money(cap10.hi)} a year (central ${fmt.money(cap10.cen)}), and still pays unless more than ${fmt.pct(cap10.breakeven, 0)} of the capped volume is lost. Test it in one market first.`,
    true);
  return { bands, cap10 };
}

function renderCap() {
  const c = +$('capSlider').value; S.cap = c;
  $('capOut').textContent = `${c}%`;
  const r = whatifCurve[c];
  $('disScen').innerHTML = `
    <span class="lbl">Items above the cap</span><span class="v">${fmt.int(r.items)} (${fmt.pct(r.items / IDX.length, 0)})</span>
    <span class="lbl">High · volume holds</span><span class="v">${fmt.money(r.hi)} / yr</span>
    <span class="lbl">Central · data elasticity</span><span class="v big">${fmt.money(r.cen)} / yr</span>
    <span class="lbl">Low · elasticity −1.5</span><span class="v">${fmt.money(r.lo)} / yr</span>
    <span class="lbl">Break-even volume loss</span><span class="v">${r.items ? fmt.pct(r.breakeven, 0) : 'n/a'}</span>`;
  lineChart($('disWhatifChart'), {
    labels: whatifCurve.map((_, k) => `${k}%`),
    series: [{ name: 'Central', values: whatifCurve.map(w => w.cen), color: css('mark-2') }],
    band: { name: 'Low to high', lower: whatifCurve.map(w => w.lo), upper: whatifCurve.map(w => w.hi), color: css('mark') },
    yFmt: fmt.axisMoney, yLabel: 'profit recovered, USD per year', xLabel: 'discount cap', yMin: 0, marker: c, height: 260,
  });
}

// ---------- page 4: customers ----------
function renderCustomers() {
  const nM = M.dicts.months.length;
  const nCust = M.rfm_by_customer.length;
  const first = new Uint8Array(nCust).fill(255);
  const active = new Uint8Array(nCust * nM);
  const segN = new Uint32Array(7), segRev = new Float64Array(7), segOrders = new Uint32Array(7);
  const seen = new Uint8Array(nCust);
  let prevOrder = -1;
  for (const i of IDX) {
    const c = C.customer[i], m = C.month[i];
    if (m < first[c]) first[c] = m;
    active[c * nM + m] = 1;
    const s = M.rfm_by_customer[c] === 255 ? 6 : M.rfm_by_customer[c];
    segRev[s] += C.item_total[i];
    if (!seen[c]) { seen[c] = 1; segN[s]++; }
    if (C.order[i] !== prevOrder) { segOrders[s]++; prevOrder = C.order[i]; }
  }
  // cohorts
  const size = new Uint32Array(nM), ret = Array.from({ length: nM }, () => new Uint32Array(nM));
  let m3num = 0, m3den = 0;
  for (let c = 0; c < nCust; c++) {
    const f = first[c]; if (f === 255) continue;
    size[f]++;
    for (let k = 1; f + k <= S.f.to; k++) if (active[c * nM + f + k]) ret[f][k]++;
    if (f + 3 <= S.f.to) { m3den++; if (active[c * nM + f + 3]) m3num++; }
  }
  const customers = segN.reduce((a, b) => a + b, 0);
  const totRev = segRev.reduce((a, b) => a + b, 0);
  const names = M.rfm_segments.concat(['Not scored']);
  const segRows = names.map((name, s) => ({ name, n: segN[s], share: segN[s] / customers, rev: segRev[s], revShare: segRev[s] / totRev,
    orders: segOrders[s] / segN[s] })).filter(r => r.n > 0).sort((a, b) => b.rev - a.rev);
  const champ = segRows.find(r => r.name === 'Champions');
  const val = M.rfm_validation;
  const vmin = Math.min(...val.map(v => v.share_ordering_next_6m)), vmax = Math.max(...val.map(v => v.share_ordering_next_6m));
  kpiTiles($('cusKpis'), [
    { label: 'Customers', value: fmt.int(customers), delta: 'with a valid order in the filter' },
    { label: 'Month-3 retention', value: fmt.pct(m3num / m3den), delta: `${fmt.int(m3num)} of ${fmt.int(m3den)} cohort customers` },
    { label: 'Champions revenue share', value: champ ? fmt.pct(champ.revShare, 0) : 'n/a', delta: champ ? `${fmt.pct(champ.share, 0)} of customers` : '' },
    { label: 'Next-6-month buyers', value: `${fmt.pct(vmin, 0)}–${fmt.pct(vmax, 0)}`, delta: 'range across RFM segments' },
  ]);
  table($('cusSeg'), [
    { label: 'Segment', key: 'name' },
    { label: 'Customers', key: 'n', num: true, fmt: fmt.int },
    { label: 'Share', key: 'share', num: true, fmt: v => fmt.pct(v, 0) },
    { label: 'Revenue', key: 'rev', num: true, fmt: fmt.money },
    { label: 'Revenue share', key: 'revShare', num: true, html: r => inbar(r.revShare, segRows[0].revShare, false, fmt.pct(r.revShare, 0)) },
    { label: 'Orders / cust.', key: 'orders', num: true, fmt: v => v.toFixed(1) },
  ], segRows);
  const v = [...val].sort((a, b) => b.past_revenue_per_customer - a.past_revenue_per_customer);
  barChart($('cusVal'), {
    labels: v.map(x => ({ 'Champions': 'Champ.', 'New & promising': 'New', 'Needs attention': 'Needs att.', 'Hibernating': 'Hibern.' }[x.rfm_segment] || x.rfm_segment)),
    values: v.map(x => x.share_ordering_next_6m), colors: v.map(() => css('mark')),
    yFmt: x => fmt.pct(x, 0), yMax: 1, yLabel: 'ordered in next 6 months', valueLabels: true, height: 240,
    tips: v.map(x => `<b>${esc(x.rfm_segment)}</b><div>${fmt.pct(x.share_ordering_next_6m)} ordered Apr–Sep 2017</div><div>${fmt.int(x.customers)} customers · past ${fmt.money(x.past_revenue_per_customer)} each</div>`),
  });
  // cohort heat table
  const maxK = Math.min(24, S.f.to - S.f.from);
  const cohorts = [...Array(nM).keys()].filter(f => f >= S.f.from && f <= S.f.to && size[f] >= 50);
  const ks = [...Array(maxK).keys()].map(k => k + 1);
  $('cusCohort').innerHTML = `<table class="heat compact"><thead><tr><th>Cohort</th><th class="col">n</th>${ks.map(k => `<th class="col">${k}</th>`).join('')}</tr></thead><tbody>${
    cohorts.map(f => `<tr><th>${fmt.month(M.dicts.months[f])}</th><td class="empty">${fmt.int(size[f])}</td>${ks.map(k => {
      if (f + k > S.f.to) return '<td class="empty"></td>';
      const r = ret[f][k] / size[f];
      return `<td style="background:${ramp(GREY_RAMP, r / 0.25)};color:${r > 0.15 ? '#fff' : '#111110'}" title="${fmt.month(M.dicts.months[f])} cohort, month ${k}: ${fmt.pct(r)}">${(r * 100).toFixed(0)}</td>`;
    }).join('')}</tr>`).join('')
  }</tbody></table>`;
  $('cusScale').style.background = `linear-gradient(90deg, ${GREY_RAMP.join(',')})`;
  takeaway('Customers · Q3',
    `About ${fmt.pct(m3num / m3den, 0)} of a cohort orders again in any given month, and RFM segments do not change that.`,
    `Champions hold ${champ ? fmt.pct(champ.revShare, 0) : 'n/a'} of revenue, but scored on data to March 2017 every segment ordered again at ${fmt.pct(vmin, 0)} to ${fmt.pct(vmax, 0)} over the next six months. Target retention spend by randomised test, not by RFM list.`,
    false);
  return { customers, m3: m3num / m3den, segRows };
}

// ---------- page 5: products ----------
function renderProducts() {
  const np = M.products.length;
  const p = Array.from({ length: np }, (_, k) => ({ k, name: M.products[k].name, category: M.products[k].category, rev: 0, prof: 0, n: 0, loss: 0 }));
  for (const i of IDX) { const x = p[C.product[i]]; x.rev += C.item_total[i]; x.prof += C.profit[i]; x.n++; if (C.profit[i] < 0) x.loss++; }
  const sold = p.filter(x => x.n > 0);
  const totP = sold.reduce((a, x) => a + x.prof, 0), totR = sold.reduce((a, x) => a + x.rev, 0);
  const byProf = [...sold].sort((a, b) => b.prof - a.prof), byRev = [...sold].sort((a, b) => b.rev - a.rev);
  let cum = 0;
  byProf.forEach(x => { const before = cum; cum += x.prof; x.cum = cum / totP; x.abc = before / totP < 0.8 ? 'A' : before / totP < 0.95 ? 'B' : 'C'; x.margin = x.prof / x.rev; });
  let cumR = 0; const cumRev = byRev.map(x => (cumR += x.rev) / totR);
  const top = Math.ceil(0.2 * sold.length);
  const topProfShare = byProf.slice(0, top).reduce((a, x) => a + x.prof, 0) / totP;
  const topRevShare = byRev.slice(0, top).reduce((a, x) => a + x.rev, 0) / totR;
  const losers = sold.filter(x => x.prof < 0);
  const nA = byProf.filter(x => x.abc === 'A').length;
  kpiTiles($('proKpis'), [
    { label: 'Profit share, top 20%', value: fmt.pct(topProfShare), delta: `${top} of ${sold.length} products; revenue share ${fmt.pct(topRevShare)}` },
    { label: 'A-class products', value: fmt.int(nA), delta: 'first 80% of cumulative profit' },
    { label: 'Loss-making products', value: fmt.int(losers.length), bad: losers.length > 0, delta: losers.length ? `${fmt.money(-losers.reduce((a, x) => a + x.prof, 0))} lost in total` : 'none' },
    { label: 'Loss-making lines', value: fmt.pct(sold.reduce((a, x) => a + x.loss, 0) / IDX.length), bad: true, delta: 'of valid order lines' },
  ]);
  const shown = Math.min(30, byProf.length);
  lineChart($('proPareto'), {
    labels: byProf.slice(0, shown).map((_, k) => `${k + 1}`),
    series: [
      { name: 'Profit', values: byProf.slice(0, shown).map(x => x.cum), color: css('mark-2'), width: 2.5 },
      { name: 'Revenue', values: cumRev.slice(0, shown), color: css('mark'), width: 2 },
    ],
    yFmt: v => fmt.pct(v, 0), yLabel: 'cumulative share', yMin: 0, yMax: 1, height: 240,
    xLabel: `top ${shown} products, ranked (the other ${byProf.length - shown} add ${fmt.pct(1 - byProf[shown - 1].cum, 1)} of profit)`,
  });
  const half = byRev.slice(0, Math.ceil(byRev.length / 2));
  const flagged = sold.filter(x => x.prof < 0 || (half.includes(x) && x.prof / x.rev < 0.10)).sort((a, b) => b.rev - a.rev);
  table($('proFlag'), [
    { label: 'Product', key: 'name' },
    { label: 'Revenue', key: 'rev', num: true, fmt: fmt.money },
    { label: 'Profit', key: 'prof', num: true, fmt: fmt.money, bad: r => r.prof < 0 },
    { label: 'Margin', key: 'margin', num: true, fmt: (_, r) => fmt.pct(r.prof / r.rev), bad: r => r.prof < 0 },
    { label: 'Lines', key: 'n', num: true, fmt: fmt.int },
  ], flagged);
  if (!flagged.length) $('proFlag').innerHTML = '<p class="desc">No product matches in this filter.</p>';
  table($('proTable'), [
    { label: '#', key: 'k', num: true, fmt: (_, r) => byProf.indexOf(r) + 1 },
    { label: 'Product', key: 'name' },
    { label: 'Category', key: 'category' },
    { label: 'Revenue', key: 'rev', num: true, fmt: fmt.money },
    { label: 'Profit', key: 'prof', num: true, html: r => inbar(Math.max(r.prof, 0), byProf[0].prof, r.prof < 0, fmt.money(r.prof)) },
    { label: 'Margin', key: 'margin', num: true, fmt: v => fmt.pct(v) },
    { label: 'Cum. profit', key: 'cum', num: true, fmt: v => fmt.pct(v, 0) },
    { label: 'Class', key: 'abc' },
  ], byProf.slice(0, 15));
  takeaway('Products · Q4',
    `${nA} products earn ${fmt.pct(byProf[nA - 1] ? byProf[nA - 1].cum : 0, 0)} of profit, and they are the same products that earn the revenue.`,
    `The top 20% of products earn ${fmt.pct(topProfShare)} of profit and ${fmt.pct(topRevShare)} of revenue. Only ${losers.length} product${losers.length === 1 ? '' : 's'} lose money, and loss-making lines are spread evenly, so product mix is not the profit lever; the discount policy is.`,
    false);
  return { topProfShare, topRevShare, losers: losers.length, nA };
}

// ---------- routing & controls ----------
const PAGES = { summary: renderSummary, delivery: renderDelivery, discounts: renderDiscounts, customers: renderCustomers, products: renderProducts };

function render() {
  document.querySelectorAll('[data-view]').forEach(s => s.classList.toggle('hidden', s.dataset.view !== S.page));
  document.querySelectorAll('nav.tabs a').forEach(a => { if (a.dataset.page === S.page) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  const isDefs = S.page === 'definitions';
  $('takeaway').classList.toggle('hidden', isDefs);
  if (isDefs) {
    takeaway('', '', '', false);
    return;
  }
  if (!IDX.length) {
    takeaway('No data', 'No order items match these filters.', 'Widen the date range or reset the filters.', false);
    document.querySelectorAll('[data-view]').forEach(s => s.classList.add('hidden'));
    return;
  }
  window.__dashboard = window.__dashboard || {};
  window.__dashboard[S.page] = PAGES[S.page]();
  window.__dashboard.ready = true;
}

function refresh() { applyFilters(); render(); }

function fillSelect(sel, items, allLabel) {
  sel.innerHTML = (allLabel ? `<option value="-1">${allLabel}</option>` : '') + items.map(([v, l]) => `<option value="${v}">${esc(l)}</option>`).join('');
}

function syncFilterControls() {
  $('fFrom').value = S.f.from; $('fTo').value = S.f.to;
  $('fMarket').value = S.f.market; $('fSegment').value = S.f.segment; $('fCategory').value = S.f.category;
}

function initControls() {
  const months = M.dicts.months.map((m, k) => [k, fmt.month(m)]);
  fillSelect($('fFrom'), months); fillSelect($('fTo'), months);
  fillSelect($('fMarket'), M.dicts.markets.map((m, k) => [k, m]), 'All markets');
  fillSelect($('fSegment'), M.dicts.segments.map((m, k) => [k, m]), 'All segments');
  fillSelect($('fCategory'), M.dicts.categories.map((m, k) => [k, m]).sort((a, b) => a[1].localeCompare(b[1])), 'All categories');
  syncFilterControls();
  const on = (id, key) => $(id).addEventListener('change', e => {
    S.f[key] = +e.target.value;
    if (S.f.from > S.f.to) { if (key === 'from') S.f.to = S.f.from; else S.f.from = S.f.to; syncFilterControls(); }
    refresh();
  });
  on('fFrom', 'from'); on('fTo', 'to'); on('fMarket', 'market'); on('fSegment', 'segment'); on('fCategory', 'category');
  $('resetBtn').addEventListener('click', () => { S.f = defaults(); syncFilterControls(); refresh(); });
  $('capSlider').addEventListener('input', renderCap);
  ['pFirst', 'pSecond'].forEach(id => $(id).addEventListener('change', () => renderPromiseWhatif(totals())));
  window.addEventListener('hashchange', () => { S.page = pageFromHash(); render(); window.scrollTo(0, 0); });
  let rt; window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(render, 150); });
  $('themeBtn').addEventListener('click', () => {
    const dark = document.documentElement.dataset.theme === 'dark' ||
      (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.dataset.theme = dark ? 'light' : 'dark';
    try { localStorage.setItem('scdd-theme', document.documentElement.dataset.theme); } catch (e) { /* storage unavailable */ }
    setThemeLabel(); render();
  });
}

function setThemeLabel() {
  const dark = document.documentElement.dataset.theme === 'dark' ||
    (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);
  $('themeBtn').setAttribute('aria-pressed', String(dark));
}

const pageFromHash = () => { const h = location.hash.replace('#', ''); return h in PAGES || h === 'definitions' ? h : 'summary'; };

(async function main() {
  try { const t = localStorage.getItem('scdd-theme'); if (t) document.documentElement.dataset.theme = t; } catch (e) { /* ignore */ }
  setThemeLabel();
  try {
    await load();
  } catch (e) {
    $('loading').textContent = 'Could not load data/items.bin. Serve this folder over HTTP (python -m http.server) rather than opening the file directly.';
    return;
  }
  S.f = defaults();
  $('subtitle').textContent = `DataCo orders · ${fmt.int(N)} valid order items, ${fmt.month(M.dicts.months[0])} – ${fmt.month(M.dicts.months[M.dicts.months.length - 1])}`;
  initControls();
  $('loading').classList.add('hidden');
  $('takeaway').classList.remove('hidden');
  S.page = pageFromHash();
  refresh();
})();
