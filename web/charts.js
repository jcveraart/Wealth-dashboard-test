'use strict';
/* Charts drawn as SVG: sparklines, an interactive time chart, waterfall, treemap, sunburst, sankey, bubbles,
   heat tables, progress rings and small maps. Uses helpers from app.js (esc, fmtV, niceTicks, fdate, SERIES). */

const col = i => `var(${SERIES[i % SERIES.length]})`;
const DAY = 864e5;
const isoOf = t => new Date(t).toISOString().slice(0, 10);
const tOf = iso => Date.parse(iso.length === 7 ? iso + '-15' : iso);
const monthKey = t => isoOf(t).slice(0, 7);

/* ---------- sparkline: the trend in the quiet hue, today in the accent ---------- */
function spark(vals, {w = 88, h = 26} = {}) {
  const v = vals.filter(Number.isFinite);
  if (v.length < 2) return '';
  const lo = Math.min(...v), hi = Math.max(...v);
  const X = i => 2 + i / (v.length - 1) * (w - 6), Y = x => h - 4 - (x - lo) / ((hi - lo) || 1) * (h - 8);
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true">
    <path d="${v.map((x, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(x).toFixed(1)}`).join('')}"/>
    <circle cx="${X(v.length - 1).toFixed(1)}" cy="${Y(v[v.length - 1]).toFixed(1)}" r="2.6"/></svg>`;
}

/* ---------- time chart ----------
   o.series: [{name, pts: [[t, v], ...], color, area, step, dash}]  (t in ms, or a plain number with xfmt 'num')
   o.stacked, o.pct ('index' = change since the first point, 'share' = share of the total), o.unit,
   o.markers [{t, label}], o.dots [{t, v, label}], o.bands [{pts: [[t, lo, hi]], color, op}], o.hline {v, label},
   o.select (drag to compare two dates), o.sync (hover links to other charts by month), o.height, o.xfmt, o.legend */
function timeChart(el, o) {
  // drawn before its card has a width (just inserted, or folded): wait one frame instead of drawing a shrunken chart
  if ((!el.isConnected || !el.clientWidth) && !o._waited) { o._waited = true; requestAnimationFrame(() => timeChart(el, o)); return; }
  el.classList.add('tc');
  const W = Math.max(280, Math.round(el.clientWidth || 640)), H = o.height || 240, pl = 56, pr = 14, pt = 12, pb = 26;
  let series = (o.series || []).filter(s => s.pts && s.pts.length).map((s, i) => ({...s, color: s.color || col(i), pts: s.pts.map(p => [p[0], p[1]])}));
  if (!series.length || series.every(s => s.pts.length < 2 && !o.bands)) {
    el.innerHTML = `<div class="empty">${o.empty || 'Not enough data yet.'}</div>`;
    return;
  }
  if (o.pct === 'index') series.forEach(s => { const b = (s.pts.find(p => p[1]) || [0, 1])[1]; s.pts = s.pts.map(([t, v]) => [t, (v / b - 1) * 100]); });
  if (o.pct === 'share') {
    const tot = new Map();
    series.forEach(s => s.pts.forEach(([t, v]) => tot.set(t, (tot.get(t) || 0) + Math.max(0, v))));
    series = series.filter(s => !s.neg).map(s => ({...s, pts: s.pts.map(([t, v]) => [t, tot.get(t) ? Math.max(0, v) / tot.get(t) * 100 : 0])}));
  }
  const unit = o.pct ? '%' : (o.unit ?? '€');
  const ts = [...new Set(series.flatMap(s => s.pts.map(p => p[0])))].sort((a, b) => a - b);
  // stacking: positives build up from zero, negatives build down
  const layers = series.map(() => []);
  if (o.stacked) {
    const at = series.map(s => new Map(s.pts));
    for (const t of ts) {
      let up = 0, down = 0;
      series.forEach((s, k) => { const v = at[k].get(t) || 0; const a = v >= 0 ? up : down; if (v >= 0) up += v; else down += v; layers[k].push([t, a, a + v]); });
    }
  }
  const all = o.stacked ? layers.flat().flatMap(l => [l[1], l[2]]) : series.flatMap(s => s.pts.map(p => p[1]));
  for (const b of o.bands || []) for (const p of b.pts) all.push(p[1], p[2]);
  if (o.hline) all.push(o.hline.v);
  const needZero = o.stacked || o.zero;
  const ticks = niceTicks(Math.min(...all, ...(needZero ? [0] : [])), Math.max(...all, ...(needZero ? [0] : [])));
  const y0 = ticks[0], y1 = ticks[ticks.length - 1];
  const tmin = ts[0], tmax = ts[ts.length - 1] === ts[0] ? ts[0] + 1 : ts[ts.length - 1];
  const X = t => pl + (t - tmin) / (tmax - tmin) * (W - pl - pr), Y = v => pt + (1 - (v - y0) / ((y1 - y0) || 1)) * (H - pt - pb);
  const xlab = t => o.xfmt === 'num' ? String(t) : o.xfmt === 'day' ? `${t}` : o.xfmt === 'year' ? new Date(t).getFullYear() :
    (tmax - tmin > 400 * DAY ? `${MONTHS[new Date(t).getMonth()]} ${String(new Date(t).getFullYear()).slice(2)}` : `${new Date(t).getDate()} ${MONTHS[new Date(t).getMonth()]}`);
  const xticks = o.xticks || Array.from({length: 6}, (_, i) => tmin + (tmax - tmin) * i / 5);
  const path = (pts, step) => pts.map(([t, v], i) => i ? (step ? `H${X(t).toFixed(1)}V${Y(v).toFixed(1)}` : `L${X(t).toFixed(1)},${Y(v).toFixed(1)}`) : `M${X(t).toFixed(1)},${Y(v).toFixed(1)}`).join('');
  let marks = '';
  for (const b of o.bands || []) {
    marks += `<path class="tc-band" style="fill:${b.color || col(0)};opacity:${b.op ?? 0.14}" d="${b.pts.map(([t, , hi], i) => `${i ? 'L' : 'M'}${X(t).toFixed(1)},${Y(hi).toFixed(1)}`).join('')}${[...b.pts].reverse().map(([t, lo]) => `L${X(t).toFixed(1)},${Y(lo).toFixed(1)}`).join('')}Z"/>`;
  }
  if (o.stacked) {
    layers.forEach((L, k) => {
      const d = L.map(([t, , top], i) => `${i ? 'L' : 'M'}${X(t).toFixed(1)},${Y(top).toFixed(1)}`).join('') + [...L].reverse().map(([t, bot]) => `L${X(t).toFixed(1)},${Y(bot).toFixed(1)}`).join('') + 'Z';
      marks += `<path class="tc-layer" data-s="${esc(series[k].name)}" style="fill:${series[k].color}" d="${d}"/>`;
    });
    layers.forEach(L => { marks += `<path class="tc-gap" d="${L.map(([t, , top], i) => `${i ? 'L' : 'M'}${X(t).toFixed(1)},${Y(top).toFixed(1)}`).join('')}"/>`; });
  } else {
    series.forEach(s => {
      const base = Math.min(Math.max(0, y0), y1);
      if (s.area) marks += `<path class="tc-area" data-s="${esc(s.name)}" style="fill:${s.color}" d="${path(s.pts, s.step)}L${X(s.pts[s.pts.length - 1][0]).toFixed(1)},${Y(base).toFixed(1)}L${X(s.pts[0][0]).toFixed(1)},${Y(base).toFixed(1)}Z"/>`;
      marks += `<path class="tc-line${s.dash ? ' dash' : ''}" data-s="${esc(s.name)}" style="stroke:${s.color}${s.width ? ';stroke-width:' + s.width : ''}" d="${path(s.pts, s.step)}"/>`;
    });
  }
  if (o.hline) marks += `<line class="tc-hline" x1="${pl}" x2="${W - pr}" y1="${Y(o.hline.v)}" y2="${Y(o.hline.v)}"/><text class="c-ax" x="${W - pr}" y="${Y(o.hline.v) - 5}" text-anchor="end">${esc(o.hline.label || '')}</text>`;
  const onLine = t => {
    // the y of the first series (or the stack top) at time t, for markers
    const L = o.stacked ? layers[layers.length - 1].map(([x, , top]) => [x, top]) : series[0].pts;
    let best = L[0]; for (const p of L) if (Math.abs(p[0] - t) < Math.abs(best[0] - t)) best = p;
    return Y(best[1]);
  };
  let hits = '';
  for (const d of o.dots || []) {
    marks += `<circle class="tc-dot" cx="${X(d.t)}" cy="${Y(d.v)}" r="4" style="fill:${d.color || 'var(--ink)'}"/>`;
    hits += `<circle class="tc-hit" data-tip="${esc(d.label)}" cx="${X(d.t)}" cy="${Y(d.v)}" r="11"/>`;
  }
  for (const m of o.markers || []) {
    if (m.t < tmin || m.t > tmax) continue;
    const y = onLine(m.t);
    marks += `<circle class="tc-marker" cx="${X(m.t).toFixed(1)}" cy="${y.toFixed(1)}" r="4.5"/>`;
    hits += `<circle class="tc-hit" data-tip="${esc(fdate(isoOf(m.t)) + ': ' + m.label)}" cx="${X(m.t).toFixed(1)}" cy="${y.toFixed(1)}" r="11"/>`;
  }
  const legend = (o.legend ?? series.length > 1) ? `<div class="c-legend">${series.map(s => `<span data-series="${esc(s.name)}"><i style="background:${s.color}"></i>${esc(s.name)}</span>`).join('')}${o.legendExtra || ''}</div>` : '';
  // short axis labels, unless rounding makes two of them the same (a balance that barely moves)
  const yl = ticks.map(v => fmtV(v, unit, true)), ylabs = new Set(yl).size < yl.length ? ticks.map(v => fmtV(v, unit)) : yl;
  const xlabs = xticks.map(t => String(xlab(t))).map((l, i, a) => i && l === a[i - 1] ? '' : l);
  el.innerHTML = `${legend}<div class="tc-sel" hidden></div><svg viewBox="0 0 ${W} ${H}" class="c-svg tc-svg" role="img" aria-label="${esc(o.label || 'Chart')}">
    ${ticks.map((v, i) => `<line class="c-grid" x1="${pl}" x2="${W - pr}" y1="${Y(v)}" y2="${Y(v)}"/><text class="c-ax" x="${pl - 8}" y="${Y(v) + 4}" text-anchor="end">${ylabs[i]}</text>`).join('')}
    ${y0 < 0 && y1 > 0 ? `<line class="c-base" x1="${pl}" x2="${W - pr}" y1="${Y(0)}" y2="${Y(0)}"/>` : ''}
    ${xticks.map((t, i) => xlabs[i] ? `<text class="c-ax" x="${X(t)}" y="${H - 7}" text-anchor="${i === 0 ? 'start' : i === xticks.length - 1 ? 'end' : 'middle'}">${esc(xlabs[i])}</text>` : '').join('')}
    <rect class="tc-selrect" y="${pt}" height="${H - pt - pb}" width="0" visibility="hidden"/>
    ${marks}
    <line class="tc-cross" y1="${pt}" y2="${H - pb}" visibility="hidden"/>
    <rect class="tc-hitarea" x="${pl}" y="${pt}" width="${W - pl - pr}" height="${H - pt - pb}"/>
    ${hits}
  </svg><div class="tip tc-tip" hidden></div>`;
  const svg = $('svg', el), cross = $('.tc-cross', el), tip = $('.tc-tip', el), hit = $('.tc-hitarea', el), selRect = $('.tc-selrect', el), selBox = $('.tc-sel', el);
  const toT = clientX => { const r = svg.getBoundingClientRect(); return tmin + ((clientX - r.left) / r.width * W - pl) / (W - pl - pr) * (tmax - tmin); };
  const nearest = t => { let b = ts[0]; for (const x of ts) if (Math.abs(x - t) < Math.abs(b - t)) b = x; return b; };
  const valAt = (s, t) => { const p = s.pts.find(p => p[0] === t); return p ? p[1] : null; };
  const showCross = t => { cross.setAttribute('x1', X(t)); cross.setAttribute('x2', X(t)); cross.setAttribute('visibility', 'visible'); };
  const readout = t => {
    const lines = series.map((s, k) => { const v = o.stacked ? (layers[k].find(l => l[0] === t) || [0, 0, 0]) : null; const val = o.stacked ? v[2] - v[1] : valAt(s, t); return val == null ? '' : `<div class="tr"><i style="background:${s.color}"></i><b class="amt">${fmtV(val, unit)}</b><span>${esc(s.name)}</span></div>`; }).join('');
    const total = o.stacked && !o.pct ? `<div class="tr tot"><b class="amt">${fmtV(series.reduce((a, s, k) => a + ((layers[k].find(l => l[0] === t) || [0, 0, 0])[2] - (layers[k].find(l => l[0] === t) || [0, 0, 0])[1]), 0), unit)}</b><span>Total</span></div>` : '';
    return `<div class="muted small">${o.xfmt === 'num' || o.xfmt === 'day' ? esc(o.xname ? o.xname(t) : t) : fdate(isoOf(t))}</div>${lines}${total}`;
  };
  let drag = null;
  hit.addEventListener('pointermove', e => {
    const t = nearest(toT(e.clientX)), r = el.getBoundingClientRect(), sr = svg.getBoundingClientRect();
    showCross(t);
    tip.hidden = false; tip.innerHTML = readout(t);
    const x = X(t) / W * sr.width + sr.left - r.left;
    tip.style.left = Math.min(Math.max(x, 70), r.width - 70) + 'px'; tip.style.top = (sr.top - r.top + 8) + 'px';
    if (o.sync && o.xfmt !== 'num' && o.xfmt !== 'day') document.dispatchEvent(new CustomEvent('xsync', {detail: {x: monthKey(t), from: el}}));
    if (drag) {
      const a = X(Math.min(drag, t)), b = X(Math.max(drag, t));
      selRect.setAttribute('x', a); selRect.setAttribute('width', Math.max(1, b - a)); selRect.setAttribute('visibility', 'visible');
    }
  });
  hit.addEventListener('pointerleave', () => { if (!drag) { cross.setAttribute('visibility', 'hidden'); tip.hidden = true; if (o.sync) document.dispatchEvent(new CustomEvent('xsync', {detail: {x: null, from: el}})); } });
  if (o.select) {
    hit.addEventListener('pointerdown', e => { drag = nearest(toT(e.clientX)); hit.setPointerCapture(e.pointerId); selBox.hidden = true; });
    hit.addEventListener('pointerup', e => {
      if (drag == null) return;
      const a = Math.min(drag, nearest(toT(e.clientX))), b = Math.max(drag, nearest(toT(e.clientX)));
      drag = null;
      if (X(b) - X(a) < 6) { selRect.setAttribute('visibility', 'hidden'); return; }
      const sum = t => o.stacked ? layers.reduce((s, L) => { const l = L.find(x => x[0] === t); return s + (l ? l[2] - l[1] : 0); }, 0) : valAt(series[0], t);
      const va = sum(a), vb = sum(b), d = vb - va;
      selBox.hidden = false;
      selBox.innerHTML = `<b class="${d < 0 ? 'neg' : 'pos'} amt">${unit === '%' ? fmtV(d, '%') + ' points' : (d < 0 ? '−' : '+') + fmtV(Math.abs(d), unit)}</b>${unit !== '%' && va ? ` <span class="${d < 0 ? 'neg' : 'pos'}">(${d < 0 ? '−' : '+'}${Math.abs(d / va * 100).toFixed(1)}%)</span>` : ''}
        <span class="muted">between ${fdate(isoOf(a))} and ${fdate(isoOf(b))}</span><button type="button" class="x-btn" aria-label="Clear">×</button>`;
      $('button', selBox).onclick = () => { selBox.hidden = true; selRect.setAttribute('visibility', 'hidden'); };
    });
  }
  if (o.sync) {
    const onSync = e => {
      if (!document.body.contains(el)) return document.removeEventListener('xsync', onSync);
      if (e.detail.from === el) return;
      if (!e.detail.x) { cross.setAttribute('visibility', 'hidden'); return; }
      const t = tOf(e.detail.x);
      if (t >= tmin - 20 * DAY && t <= tmax + 20 * DAY) showCross(nearest(t));
    };
    document.addEventListener('xsync', onSync);
  }
  el.chartData = () => [['date', ...series.map(s => s.name)], ...ts.map(t => [o.xfmt === 'num' || o.xfmt === 'day' ? t : isoOf(t), ...series.map(s => { const v = valAt(s, t); return v == null ? '' : +v.toFixed(2); })])];
}

/* ---------- waterfall: where a change came from ---------- */
function waterfall(steps, W = 640) {
  // steps: [{label, v, total}] ; totals stand on zero, the rest float from the running sum
  const H = 230, pl = 56, pr = 10, pt = 22, pb = 38;
  let run = 0;
  const bars = steps.map(s => { const a = s.total ? 0 : run, b = s.total ? s.v : run + s.v; run = s.total ? s.v : run + s.v; return {...s, a, b}; });
  const vals = bars.flatMap(b => [b.a, b.b]);
  const ticks = niceTicks(Math.min(0, ...vals), Math.max(...vals)), y0 = ticks[0], y1 = ticks[ticks.length - 1];
  const band = (W - pl - pr) / bars.length, bw = Math.min(40, band * 0.56);
  const Y = v => pt + (1 - (v - y0) / ((y1 - y0) || 1)) * (H - pt - pb);
  return `<svg viewBox="0 0 ${W} ${H}" class="c-svg" role="img" aria-label="Waterfall">
    ${ticks.map(v => `<line class="c-grid" x1="${pl}" x2="${W - pr}" y1="${Y(v)}" y2="${Y(v)}"/><text class="c-ax" x="${pl - 8}" y="${Y(v) + 4}" text-anchor="end">${fmtV(v, '€', true)}</text>`).join('')}
    ${bars.map((b, i) => {
      const x = pl + band * i + (band - bw) / 2, top = Math.min(Y(b.a), Y(b.b)), h = Math.max(1.5, Math.abs(Y(b.a) - Y(b.b)));
      const fill = b.total ? 'var(--s1)' : b.v >= 0 ? 'var(--gain)' : 'var(--loss)';
      const next = bars[i + 1];
      return `<rect data-tip="${esc(b.label + ': ' + (b.total ? '' : b.v >= 0 ? '+' : '−') + fmtV(Math.abs(b.v), '€'))}" x="${x}" y="${top}" width="${bw}" height="${h}" rx="3" fill="${fill}"/>
        ${next ? `<line class="c-base" x1="${x + bw}" x2="${x + band}" y1="${Y(b.b)}" y2="${Y(b.b)}"/>` : ''}
        <text class="c-val amt" x="${x + bw / 2}" y="${top - 6}" text-anchor="middle">${b.total ? fmtV(b.v, '€', true) : (b.v >= 0 ? '+' : '−') + fmtV(Math.abs(b.v), '€', true)}</text>
        <text class="c-ax" x="${x + bw / 2}" y="${H - 20}" text-anchor="middle">${esc(b.label.split(' ')[0])}</text>
        <text class="c-ax" x="${x + bw / 2}" y="${H - 7}" text-anchor="middle">${esc(b.label.split(' ').slice(1).join(' '))}</text>`;
    }).join('')}</svg>`;
}

/* ---------- treemap: squarified, two levels ---------- */
function squarify(values, x, y, w, h) {
  const total = values.reduce((a, b) => a + b, 0) || 1, areas = values.map(v => v * w * h / total), out = new Array(values.length);
  const worst = (row, sum, side) => { const mx = Math.max(...row), mn = Math.min(...row); return Math.max(side * side * mx / (sum * sum), sum * sum / (side * side * mn)); };
  let i = 0;
  while (i < areas.length) {
    const side = Math.min(w, h);
    let row = [areas[i]], sum = areas[i], score = worst(row, sum, side);
    while (i + row.length < areas.length) {
      const next = areas[i + row.length], s2 = worst([...row, next], sum + next, side);
      if (s2 > score) break;
      row.push(next); sum += next; score = s2;
    }
    if (w >= h) { const rw = sum / h; let yy = y; row.forEach((a, j) => { out[i + j] = [x, yy, rw, a / rw]; yy += a / rw; }); x += rw; w -= rw; }
    else { const rh = sum / w; let xx = x; row.forEach((a, j) => { out[i + j] = [xx, y, a / rh, rh]; xx += a / rh; }); y += rh; h -= rh; }
    i += row.length;
  }
  return out;
}
function treemap(groups, W = 900, H = 420) {
  // groups: [{name, items: [{id, label, value, change, tip}]}]; colour shows today's change
  groups = groups.map(g => ({...g, items: g.items.filter(i => i.value > 0).sort((a, b) => b.value - a.value)})).filter(g => g.items.length);
  groups.forEach(g => g.value = g.items.reduce((s, i) => s + i.value, 0));
  groups.sort((a, b) => b.value - a.value);
  const outer = squarify(groups.map(g => g.value), 0, 0, W, H);
  const tone = c => c == null ? 'var(--surface-2)' : `color-mix(in srgb, var(${c < 0 ? '--loss' : '--gain'}) ${Math.round(Math.min(55, Math.abs(c) / 2.5 * 55))}%, var(--surface-2))`;
  let svg = '';
  groups.forEach((g, gi) => {
    const [gx, gy, gw, gh] = outer[gi], head = gh > 46 && gw > 60 ? 18 : 0;
    if (head) svg += `<text class="tm-group" x="${gx + 6}" y="${gy + 13}">${esc(g.name)}</text>`;
    const inner = squarify(g.items.map(i => i.value), gx + 1, gy + head + 1, Math.max(1, gw - 2), Math.max(1, gh - head - 2));
    g.items.forEach((it, j) => {
      const [x, y, w, h] = inner[j];
      const fits = w > 64 && h > 34, big = w > 90 && h > 50;
      svg += `<g class="tm-cell" data-open="${esc(it.open || '')}" data-tip="${esc(it.tip)}">
        <rect x="${(x + 1).toFixed(1)}" y="${(y + 1).toFixed(1)}" width="${Math.max(0, w - 2).toFixed(1)}" height="${Math.max(0, h - 2).toFixed(1)}" rx="4" style="fill:${tone(it.change)}"/>
        ${fits ? `<text class="tm-label" x="${x + 8}" y="${y + 19}">${esc(it.label.length > (w - 16) / 8.4 ? it.label.slice(0, Math.max(3, Math.floor((w - 16) / 8.4) - 1)) + '…' : it.label)}</text>
          <text class="tm-sub amt" x="${x + 8}" y="${y + 35}">${big ? fmtV(it.value, '€', true) + ' · ' : ''}${it.change == null ? '' : (it.change < 0 ? '−' : '+') + Math.abs(it.change).toFixed(1) + '%'}</text>` : ''}</g>`;
    });
  });
  return `<svg viewBox="0 0 ${W} ${H}" class="c-svg tm" role="img" aria-label="Investments treemap">${svg}</svg>`;
}

/* ---------- sunburst: three rings ---------- */
function sunburst(root, size = 360) {
  // root.children: [{name, value, children: [{name, value, children: [{name, value, open}]}]}]
  const c = size / 2, R = [c * 0.34, c * 0.6, c * 0.8, c * 0.98];
  const total = root.children.reduce((s, x) => s + x.value, 0) || 1;
  const pt = (a, r) => `${(c + r * Math.sin(a)).toFixed(2)},${(c - r * Math.cos(a)).toFixed(2)}`;
  const arc = (a0, a1, r0, r1) => {
    if (a1 - a0 >= Math.PI * 2 - 1e-6) a1 = a0 + Math.PI * 2 - 1e-4;
    const L = a1 - a0 > Math.PI ? 1 : 0;
    return `M${pt(a0, r1)}A${r1},${r1} 0 ${L} 1 ${pt(a1, r1)}L${pt(a1, r0)}A${r0},${r0} 0 ${L} 0 ${pt(a0, r0)}Z`;
  };
  let out = '';
  const ring = (nodes, a0, depth, color, trail) => {
    let a = a0;
    for (const n of nodes) {
      const span = n.value / total * Math.PI * 2, clr = depth === 0 ? col(nodes.indexOf(n)) : color;
      const fill = depth === 0 ? clr : `color-mix(in srgb, ${clr} ${depth === 1 ? 70 : 45}%, var(--surface))`;
      const name = [...trail, n.name].join(' › ');
      if (span > 0.002) out += `<path class="sb-arc" d="${arc(a, a + span, R[depth], R[depth + 1])}" style="fill:${fill}" data-tip="${esc(`${name}: ${fmtV(n.value, '€')} (${(n.value / total * 100).toFixed(1)}%)`)}" ${n.open ? `data-open="${esc(n.open)}"` : `data-sb="${esc(name)}"`}/>`;
      if (n.children && depth < 2) ring(n.children, a, depth + 1, clr, [...trail, n.name]);
      a += span;
    }
  };
  ring(root.children, 0, 0, null, []);
  return `<svg viewBox="0 0 ${size} ${size}" class="c-svg sb" role="img" aria-label="Allocation rings">${out}
    <text class="sb-total amt" x="${c}" y="${c - 2}" text-anchor="middle">${fmtV(total, '€', true)}</text>
    <text class="c-ax" x="${c}" y="${c + 16}" text-anchor="middle">${esc(root.name || '')}</text></svg>`;
}

/* ---------- sankey: money from left to right ---------- */
function sankey(nodes, links, W = 900, H = 380) {
  // nodes: [{id, label, col, color}], links: [{s, t, v}] ; a node is as tall as the larger of what flows in and out
  const byId = Object.fromEntries(nodes.map(n => [n.id, {...n, in: 0, out: 0}]));
  links = links.filter(l => l.v > 0.5 && byId[l.s] && byId[l.t]);
  for (const l of links) { byId[l.s].out += l.v; byId[l.t].in += l.v; }
  const N = Object.values(byId).filter(n => n.in || n.out);
  N.forEach(n => n.v = Math.max(n.in, n.out));
  const cols = Math.max(...N.map(n => n.col)) + 1, nw = 10, gap = 10, padL = 128, padR = 150;
  const colX = k => padL + k * (W - padL - padR - nw) / Math.max(1, cols - 1);
  const k = Math.min(...[...Array(cols).keys()].map(c => { const ns = N.filter(n => n.col === c); return (H - 8 - gap * (ns.length - 1)) / (ns.reduce((s, n) => s + n.v, 0) || 1); }));
  for (let c = 0; c < cols; c++) {
    const ns = N.filter(n => n.col === c), h = ns.reduce((s, n) => s + n.v * k, 0) + gap * (ns.length - 1);
    let y = Math.max(4, (H - h) / 2);
    for (const n of ns) { n.x = colX(c); n.y = y; n.h = Math.max(1.5, n.v * k); n.oy = n.y; n.iy = n.y; y += n.h + gap; }
  }
  links.sort((a, b) => byId[a.t].y - byId[b.t].y);
  let paths = '';
  for (const l of links) {
    const s = byId[l.s], t = byId[l.t], w = l.v * k, x0 = s.x + nw, x1 = t.x, xm = (x0 + x1) / 2;
    const y0 = s.oy, yt = t.iy; s.oy += w; t.iy += w;
    paths += `<path class="sk-link" data-s="${esc(t.label)}" style="fill:${(s.col === 0 ? s.color : t.color) || 'var(--s1)'}" d="M${x0},${y0}C${xm},${y0} ${xm},${yt} ${x1},${yt}L${x1},${yt + w}C${xm},${yt + w} ${xm},${y0 + w} ${x0},${y0 + w}Z"
      data-tip="${esc(`${s.label} → ${t.label}: ${fmtV(l.v, '€')}`)}" ${t.pick ? `data-sk="${esc(t.pick)}"` : ''}/>`;
  }
  const labels = N.map(n => {
    const right = n.col < cols - 1 && n.col > 0, last = n.col === cols - 1, x = n.col === 0 ? n.x - 8 : n.x + nw + 8;
    return `<rect class="sk-node" data-s="${esc(n.label)}" x="${n.x}" y="${n.y}" width="${nw}" height="${n.h}" rx="2" style="fill:${n.color || 'var(--ink-2)'}" data-tip="${esc(`${n.label}: ${fmtV(n.v, '€')}`)}" ${n.pick ? `data-sk="${esc(n.pick)}"` : ''}/>
      ${n.h > 9 || last || n.col === 0 ? `<text class="sk-label" x="${x}" y="${n.y + n.h / 2 + 4}" text-anchor="${n.col === 0 ? 'end' : 'start'}">${esc(n.label)} <tspan class="sk-val amt">${fmtV(n.v, '€', true)}</tspan></text>` : ''}`;
  }).join('');
  return `<svg viewBox="0 0 ${W} ${H}" class="c-svg sk" role="img" aria-label="Where the money goes">${paths}${labels}</svg>`;
}

/* ---------- bubbles: how often against how much ---------- */
function bubbles(points, W = 640, H = 300, {xname = 'Payments', yname = 'Average amount'} = {}) {
  // points: [{label, x, y, r (value for the area), open, tip}] ; log scales on both axes
  if (!points.length) return '<div class="empty">Not enough data.</div>';
  const pl = 52, pr = 16, pt = 14, pb = 34;
  const lx = points.map(p => Math.log10(Math.max(1, p.x))), ly = points.map(p => Math.log10(Math.max(1, p.y)));
  const x0 = 0, x1 = Math.max(1, Math.ceil(Math.max(...lx) * 2) / 2), yA = Math.floor(Math.min(...ly)), yB = Math.max(yA + 1, Math.ceil(Math.max(...ly)));
  const X = v => pl + (Math.log10(Math.max(1, v)) - x0) / (x1 - x0) * (W - pl - pr), Y = v => pt + (1 - (Math.log10(Math.max(1, v)) - yA) / (yB - yA)) * (H - pt - pb);
  const rmax = Math.max(...points.map(p => p.r)), R = v => 4 + Math.sqrt(v / rmax) * 22;
  const xt = [1, 2, 5, 10, 20, 50, 100, 200, 500].filter(v => Math.log10(v) <= x1 + 1e-9), yt = [];
  for (let e = yA; e <= yB; e++) yt.push(10 ** e);
  const placed = [], top = [];
  for (const p of [...points].sort((a, b) => b.r - a.r).slice(0, 10)) {
    const x = X(p.x), y = Y(p.y) - R(p.r) - 4, w = Math.min(16, p.label.length) * 6.2;
    if (placed.every(q => Math.abs(q[0] - x) > (w + q[2]) / 2 + 4 || Math.abs(q[1] - y) > 13)) { placed.push([x, y, w]); top.push(p); }
  }
  return `<svg viewBox="0 0 ${W} ${H}" class="c-svg bub" role="img" aria-label="Merchants">
    ${yt.map(v => `<line class="c-grid" x1="${pl}" x2="${W - pr}" y1="${Y(v)}" y2="${Y(v)}"/><text class="c-ax" x="${pl - 8}" y="${Y(v) + 4}" text-anchor="end">${fmtV(v, '€', true)}</text>`).join('')}
    ${xt.map(v => `<text class="c-ax" x="${X(v)}" y="${H - 16}" text-anchor="middle">${v}</text>`).join('')}
    <text class="c-ax" x="${(W + pl) / 2}" y="${H - 2}" text-anchor="middle">${esc(xname)} (log scale)</text>
    ${[...points].sort((a, b) => b.r - a.r).map(p => `<circle class="bub-c" cx="${X(p.x).toFixed(1)}" cy="${Y(p.y).toFixed(1)}" r="${R(p.r).toFixed(1)}" data-tip="${esc(p.tip)}" ${p.open ? `data-merchant-pick="${esc(p.open)}"` : ''}/>`).join('')}
    ${top.map(p => `<text class="bub-l" x="${X(p.x).toFixed(1)}" y="${(Y(p.y) - R(p.r) - 4).toFixed(1)}" text-anchor="middle">${esc(p.label.length > 16 ? p.label.slice(0, 15) + '…' : p.label)}</text>`).join('')}
  </svg>`;
}

/* ---------- heat table: a grid of values as an HTML table ---------- */
function heatTable(rows, cols, cell, {diverging = false, fmt = v => fmtV(v, '%'), max, pick} = {}) {
  // cell(r, c) -> number or null ; diverging uses loss/gain around zero, otherwise one hue
  const vals = rows.flatMap((_, r) => cols.map((_, c) => cell(r, c))).filter(v => v != null && Number.isFinite(v));
  const m = max || Math.max(1e-9, ...vals.map(Math.abs));
  const bg = v => v == null ? 'transparent' : diverging
    ? `color-mix(in srgb, var(${v < 0 ? '--loss' : '--gain'}) ${Math.round(Math.min(1, Math.abs(v) / m) * 55)}%, var(--surface-2))`
    : `color-mix(in srgb, var(--s1) ${Math.round(Math.min(1, v / m) * 70)}%, var(--surface-2))`;
  return `<div class="table-wrap"><table class="heat"><thead><tr><th></th>${cols.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead>
    <tbody>${rows.map((rl, r) => `<tr><th>${esc(rl)}</th>${cols.map((cl, c) => { const v = cell(r, c);
      return `<td style="background:${bg(v)}" ${v != null ? `data-tip="${esc(`${rl} ${cl}: ${fmt(v)}`)}"` : ''} ${pick && v ? `data-heat="${r}|${c}"` : ''}>${v == null ? '' : `<span class="amt">${fmt(v)}</span>`}</td>`; }).join('')}</tr>`).join('')}</tbody></table></div>`;
}

/* ---------- progress ring ---------- */
function ring(share, size = 54, tone = 'var(--s1)') {
  const r = size / 2 - 5, c = 2 * Math.PI * r, p = Math.max(0, Math.min(1, share));
  return `<svg class="ring" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" aria-hidden="true">
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" class="ring-track"/>
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" class="ring-fill" style="stroke:${tone}" stroke-dasharray="${(c * p).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 ${size / 2} ${size / 2})"/>
    <text x="${size / 2}" y="${size / 2 + 4}" text-anchor="middle" class="ring-t">${Math.round(p * 100)}%</text></svg>`;
}

/* ---------- small map of a few countries ---------- */
function miniMap(codes, W = 240, H = 130) {
  const G = window.GEO;
  if (!G || !codes.length) return '';
  const boxes = codes.map(c => G.countries[c] && G.countries[c].b).filter(Boolean);
  if (!boxes.length) return '';
  let [x0, y0, x1, y1] = boxes.reduce((a, b) => [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[2], b[2]), Math.max(a[3], b[3])]);
  const pad = Math.max(8, (x1 - x0) * 0.35, (y1 - y0) * 0.35);
  x0 -= pad; y0 -= pad; x1 += pad; y1 += pad;
  // keep the aspect of the box we draw into
  const want = W / H, have = (x1 - x0) / (y1 - y0);
  if (have < want) { const d = ((y1 - y0) * want - (x1 - x0)) / 2; x0 -= d; x1 += d; } else { const d = ((x1 - x0) / want - (y1 - y0)) / 2; y0 -= d; y1 += d; }
  const near = Object.entries(G.countries).filter(([, c]) => c.p && c.b && c.b[2] > x0 && c.b[0] < x1 && c.b[3] > y0 && c.b[1] < y1);
  return `<svg class="mini-map" viewBox="${x0.toFixed(1)} ${y0.toFixed(1)} ${(x1 - x0).toFixed(1)} ${(y1 - y0).toFixed(1)}" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
    ${near.map(([k, c]) => `<path d="${c.p}" class="${codes.includes(k) ? 'on' : ''}"/>`).join('')}</svg>`;
}
