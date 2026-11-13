// Minimal SVG chart helpers: line (with optional band), vertical bars, and a shared tooltip.
// Colours are CSS custom properties so light/dark themes swap in one place.
(function () {
'use strict';

const SVGNS = 'http://www.w3.org/2000/svg';

function el(tag, attrs = {}, parent) {
  const e = document.createElementNS(SVGNS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}

function niceTicks(min, max, count = 4) {
  if (min === max) { max = min + 1; }
  const step0 = (max - min) / count;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const err = step0 / mag;
  const step = (err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1) * mag;
  const lo = Math.floor(min / step + 1e-9) * step;
  const hi = Math.ceil(max / step - 1e-9) * step;
  const ticks = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(+v.toFixed(10));
  return ticks;
}

const tip = {
  node: null,
  show(ev, html) {
    if (!this.node) {
      this.node = document.createElement('div');
      this.node.className = 'tooltip';
      document.body.appendChild(this.node);
    }
    this.node.innerHTML = html;
    this.node.style.display = 'block';
    const r = this.node.getBoundingClientRect();
    let x = ev.clientX + 14, y = ev.clientY + 14;
    if (x + r.width > window.innerWidth - 8) x = ev.clientX - r.width - 14;
    if (y + r.height > window.innerHeight - 8) y = ev.clientY - r.height - 14;
    this.node.style.left = `${Math.max(8, x)}px`;
    this.node.style.top = `${Math.max(8, y)}px`;
  },
  hide() { if (this.node) this.node.style.display = 'none'; },
};

function frame(host, height, margin) {
  host.innerHTML = '';
  const W = Math.max(280, host.clientWidth || 600);
  const H = height;
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, class: 'chart' }, host);
  return { svg, W, H, m: margin };
}

function yAxis(svg, ticks, y, m, W, fmt, label, H) {
  for (const t of ticks) {
    el('line', { x1: m.l, x2: W - m.r, y1: y(t), y2: y(t), class: t === 0 ? 'baseline' : 'grid' }, svg);
    const tx = el('text', { x: m.l - 8, y: y(t) + 4, class: 'tick', 'text-anchor': 'end' }, svg);
    tx.textContent = fmt(t);
  }
  if (label) {
    const t = el('text', { x: 12, y: m.t + (H - m.t - m.b) / 2, class: 'axis-title', 'text-anchor': 'middle',
      transform: `rotate(-90 12 ${m.t + (H - m.t - m.b) / 2})` }, svg);
    t.textContent = label;
  }
}

/**
 * Line chart. series: [{name, values, color, width}], optional band: {lower, upper, color, name}.
 * marker: index to draw a vertical reference line at.
 */
function lineChart(host, opts) {
  const { labels, series, yFmt, yLabel, xLabel, band, marker, height = 260, yMin, yMax, endLabels } = opts;
  const m = { l: 64, r: endLabels ? 96 : 16, t: 14, b: xLabel ? 46 : 32 };
  const { svg, W, H } = frame(host, height, m);
  const vals = series.flatMap(s => s.values).concat(band ? band.lower.concat(band.upper) : []).filter(Number.isFinite);
  const lo = yMin !== undefined ? Math.min(yMin, ...vals) : Math.min(...vals);
  const hi = yMax !== undefined ? yMax : Math.max(...vals);
  const ticks = niceTicks(lo, hi, 4);
  const y0 = ticks[0], y1 = ticks[ticks.length - 1];
  const n = labels.length;
  const x = i => m.l + (n === 1 ? 0.5 : i / (n - 1)) * (W - m.l - m.r);
  const y = v => m.t + (1 - (v - y0) / (y1 - y0 || 1)) * (H - m.t - m.b);
  yAxis(svg, ticks, y, m, W, yFmt, yLabel, H);
  const every = Math.max(1, Math.ceil(n / Math.max(2, Math.floor((W - m.l - m.r) / 64))));
  labels.forEach((l, i) => {
    if (i % every) return;
    const t = el('text', { x: x(i), y: H - m.b + 18, class: 'tick', 'text-anchor': 'middle' }, svg);
    t.textContent = l;
  });
  if (xLabel) {
    const t = el('text', { x: m.l + (W - m.l - m.r) / 2, y: H - 6, class: 'axis-title', 'text-anchor': 'middle' }, svg);
    t.textContent = xLabel;
  }
  if (band) {
    const top = band.upper.map((v, i) => `${x(i)},${y(v)}`);
    const bottom = band.lower.map((v, i) => `${x(i)},${y(v)}`).reverse();
    el('polygon', { points: top.concat(bottom).join(' '), style: `fill:${band.color};opacity:.35` }, svg);
  }
  if (marker !== undefined && marker !== null) {
    el('line', { x1: x(marker), x2: x(marker), y1: m.t, y2: H - m.b, class: 'refline' }, svg);
  }
  const ends = [];
  for (const s of series) {
    let d = '', pen = false;
    s.values.forEach((v, i) => {
      if (!Number.isFinite(v)) { pen = false; return; }
      d += `${pen ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      pen = true;
    });
    el('path', { d, style: `stroke:${s.color};stroke-width:${s.width || 2}`, class: 'line' }, svg);
    if (endLabels) {
      const last = s.values.length - 1 - [...s.values].reverse().findIndex(Number.isFinite);
      ends.push({ name: s.name, x: x(last) + 8, y: y(s.values[last]) + 4 });
    }
  }
  // End labels: keep at least 13px apart so neighbours never overlap.
  ends.sort((a, b) => a.y - b.y);
  for (let k = 1; k < ends.length; k++) if (ends[k].y - ends[k - 1].y < 13) ends[k].y = ends[k - 1].y + 13;
  for (const e of ends) el('text', { x: e.x, y: e.y, class: 'end-label' }, svg).textContent = e.name;
  const cross = el('line', { y1: m.t, y2: H - m.b, class: 'cross', visibility: 'hidden' }, svg);
  const dots = series.map(s => el('circle', { r: 4, style: `fill:${s.color}`, class: 'dot', visibility: 'hidden' }, svg));
  const hit = el('rect', { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: 'transparent' }, svg);
  hit.addEventListener('pointermove', ev => {
    const r = svg.getBoundingClientRect();
    const px = (ev.clientX - r.left) * (W / r.width);
    const i = Math.max(0, Math.min(n - 1, Math.round((px - m.l) / (W - m.l - m.r) * (n - 1))));
    cross.setAttribute('x1', x(i)); cross.setAttribute('x2', x(i)); cross.setAttribute('visibility', 'visible');
    series.forEach((s, k) => {
      const v = s.values[i];
      if (!Number.isFinite(v)) { dots[k].setAttribute('visibility', 'hidden'); return; }
      dots[k].setAttribute('cx', x(i)); dots[k].setAttribute('cy', y(v)); dots[k].setAttribute('visibility', 'visible');
    });
    let html = `<b>${labels[i]}</b>`;
    if (band) html += `<div><span class="sw" style="background:${band.color}"></span>${band.name}: ${yFmt(band.lower[i])} to ${yFmt(band.upper[i])}</div>`;
    html += series.map(s => `<div><span class="sw" style="background:${s.color}"></span>${s.name}: ${Number.isFinite(s.values[i]) ? yFmt(s.values[i]) : 'n/a'}</div>`).join('');
    tip.show(ev, html);
  });
  hit.addEventListener('pointerleave', () => {
    cross.setAttribute('visibility', 'hidden');
    dots.forEach(d => d.setAttribute('visibility', 'hidden'));
    tip.hide();
  });
}

/** Vertical bar chart. colors: one CSS colour per bar. tips: optional per-bar tooltip HTML. */
function barChart(host, opts) {
  const { labels, values, colors, yFmt, yLabel, xLabel, height = 220, yMin = 0, yMax, valueLabels, refX, refLabel, tips } = opts;
  const m = { l: 56, r: 12, t: valueLabels ? 22 : 12, b: xLabel ? 46 : 30 };
  const { svg, W, H } = frame(host, height, m);
  const hi = yMax !== undefined ? yMax : Math.max(...values, 0);
  const lo = Math.min(yMin, ...values);
  const ticks = niceTicks(lo, hi, 4);
  const y0 = ticks[0], y1 = ticks[ticks.length - 1];
  const y = v => m.t + (1 - (v - y0) / (y1 - y0 || 1)) * (H - m.t - m.b);
  yAxis(svg, ticks, y, m, W, yFmt, yLabel, H);
  const n = labels.length;
  const slot = (W - m.l - m.r) / n;
  const bw = Math.min(56, slot * 0.68);
  const r = Math.min(4, bw / 2);
  labels.forEach((l, i) => {
    const cx = m.l + slot * (i + 0.5);
    const v = values[i];
    const top = y(Math.max(v, 0)), base = y(Math.min(v, 0)) ;
    const h = Math.max(0, Math.abs(base - top));
    const x0 = cx - bw / 2;
    const rr = Math.min(r, h);
    // rounded data-end, square at the baseline
    const d = v >= 0
      ? `M${x0},${base}V${top + rr}Q${x0},${top} ${x0 + rr},${top}H${x0 + bw - rr}Q${x0 + bw},${top} ${x0 + bw},${top + rr}V${base}Z`
      : `M${x0},${top}V${base - rr}Q${x0},${base} ${x0 + rr},${base}H${x0 + bw - rr}Q${x0 + bw},${base} ${x0 + bw},${base - rr}V${top}Z`;
    const bar = el('path', { d, style: `fill:${colors[i]}`, class: 'bar' }, svg);
    const hit = el('rect', { x: cx - slot / 2, y: m.t, width: slot, height: H - m.t - m.b, fill: 'transparent' }, svg);
    const html = tips ? tips[i] : `<b>${l}</b><div>${yFmt(v)}</div>`;
    hit.addEventListener('pointermove', ev => { bar.classList.add('hover'); tip.show(ev, html); });
    hit.addEventListener('pointerleave', () => { bar.classList.remove('hover'); tip.hide(); });
    const t = el('text', { x: cx, y: H - m.b + 18, class: 'tick', 'text-anchor': 'middle' }, svg);
    t.textContent = l;
    if (valueLabels) {
      const vt = el('text', { x: cx, y: (v >= 0 ? top : base) - 6, class: 'value-label', 'text-anchor': 'middle' }, svg);
      vt.textContent = (opts.valueFmt || yFmt)(v);
    }
  });
  if (refX !== undefined) {
    const rx = m.l + slot * refX;
    el('line', { x1: rx, x2: rx, y1: m.t - 4, y2: H - m.b, class: 'refline' }, svg);
    if (refLabel) {
      const t = el('text', { x: rx + 4, y: m.t + 6, class: 'ref-label' }, svg);
      t.textContent = refLabel;
    }
  }
  if (xLabel) {
    const t = el('text', { x: m.l + (W - m.l - m.r) / 2, y: H - 6, class: 'axis-title', 'text-anchor': 'middle' }, svg);
    t.textContent = xLabel;
  }
}

/** Interpolate a ramp of hex colours at t in [0, 1]. */
function ramp(stops, t) {
  t = Math.max(0, Math.min(1, t));
  const p = t * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(p));
  const f = p - i;
  const a = stops[i].match(/\w\w/g).map(h => parseInt(h, 16));
  const b = stops[i + 1].match(/\w\w/g).map(h => parseInt(h, 16));
  return `rgb(${a.map((v, k) => Math.round(v + (b[k] - v) * f)).join(',')})`;
}

window.charts = { lineChart, barChart, ramp, tip };
})();
