'use strict';
/* Wealth dashboard front end. Talks to app.py over /api/*. */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtN = (n, d = 0) => Math.abs(n).toLocaleString('en-GB', {minimumFractionDigits: d, maximumFractionDigits: d});
const eur = (n, d = 0) => n == null ? '<span class="muted">n/a</span>' : `<span class="amt">${n < 0 ? '−' : ''}€${fmtN(n, d)}</span>`;
const sgn = (n, d = 0) => n == null ? '<span class="muted">n/a</span>' : Math.abs(n) < 0.5 / 10 ** d ? `<span class="amt muted">€${fmtN(0, d)}</span>` : `<span class="amt ${n < 0 ? 'neg' : 'pos'}">${n < 0 ? '−' : '+'}€${fmtN(n, d)}</span>`;
// a day's result with its percentage: +€12 (0.3%), the percentage of what it was worth before today
const dayc = (change, value) => {
  if (change == null) return '<span class="muted">n/a</span>';
  const before = (value || 0) - change;
  return `${sgn(change)}${before > 0 && Math.abs(change) >= 0.005 ? ` <span class="dpct ${change < 0 ? 'neg' : 'pos'}">(${change < 0 ? '−' : '+'}${Math.abs(change / before * 100).toFixed(Math.abs(change / before * 100) < 10 ? 2 : 1)}%)</span>` : ''}`;
};
const pct = (n, d) => n == null ? '<span class="muted">n/a</span>' : `<span class="${n < 0 ? 'neg' : 'pos'}">${n < 0 ? '−' : '+'}${Math.abs(n).toFixed(d ?? (Math.abs(n) < 10 ? 1 : 0))}%</span>`;
const today = () => new Date().toISOString().slice(0, 10);
const store = {
  get(k, d) { try { const v = localStorage.getItem('wealth.' + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem('wealth.' + k, JSON.stringify(v)); } catch {} },
};
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const fdate = s => { if (!s) return ''; const [y, m, d] = s.split('-'); return d ? `${+d} ${MONTHS[m - 1]} ${y}` : `${MONTHS[m - 1]} ${y}`; };
const TITLES = {overview: 'Overview', holdings: 'Investments', accounts: 'Accounts', cash: 'Savings & debt', spending: 'Spending & income', history: 'History',
  plan: 'Plan', taxes: 'Taxes', advice: 'Advice', import: 'Import', settings: 'Settings', account: 'Account'};
// known categories are grouped; any new category (Crypto, Gold, Real estate ...) becomes its own group
const TYPE_OF = c => ({'Broad ETF': 'ETFs', 'Tech ETF': 'ETFs', 'Stock': 'Stocks', 'Bond': 'Bonds', 'Bond fund': 'Bonds'}[c] || c || 'Other');
const SERIES = ['--s1', '--s2', '--s3', '--s4', '--s5', '--s6', '--s7', '--s8'];

let S = null;
let view = 'overview';
const ui = {
  account: '',
  allocBy: store.get('allocBy', 'type'),
  hold: {q: '', acct: 'all', cat: 'all', sort: 'value', dir: -1, combine: store.get('combine', false)},
  imp: {images: [], note: '', busy: false, error: null, result: null},
};

/* ---------- data ---------- */
async function load() {
  try {
    const r = await fetch('/api/state', {cache: 'no-store'});
    S = await r.json();
    renderChrome();
    const typing = document.activeElement && $('#view').contains(document.activeElement) && /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
    // the home page redraws itself only when the numbers changed, so charts don't flicker every 30 seconds
    const sig = JSON.stringify([S.totals, S.status.last_refresh, (S.history || []).length]);
    const quiet = view === 'overview' && sig === load.sig;
    load.sig = sig;
    if (!['import', 'spending', 'plan', 'taxes'].includes(view) && !quiet && !$('#dlg').open && !typing && !$('.menu, .pop, .fs, .cmdk-wrap')) renderView();
    chatBadge();
    milestones();
  } catch (e) {
    $('#pricePill').innerHTML = '<span class="dot off"></span>App not reachable. Is it running?';
  }
}
async function post(url, body) {
  const r = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  const j = await r.json().catch(() => ({error: 'Unexpected response'}));
  if (!r.ok || j.error) throw new Error(j.error || 'Request failed');
  return j;
}
async function edit(payload, msg) {
  try { await post('/api/edit', payload); toast(msg || 'Saved'); await load(); renderView(); }
  catch (e) { toast(e.message); }
}
function toast(msg) {
  const t = document.createElement('div'); t.className = 'toast'; t.textContent = msg;
  document.body.appendChild(t); setTimeout(() => t.remove(), 2600);
}

/* ---------- chrome ---------- */
function renderChrome() {
  const st = S.status;
  const when = st.last_refresh ? new Date(st.last_refresh).toLocaleTimeString('en-GB', {hour: '2-digit', minute: '2-digit'}) : 'not yet';
  const cls = st.refreshing ? 'busy' : st.live_positions ? '' : 'off';
  $('#pricePill').innerHTML = `<span class="dot ${cls}"></span>${st.refreshing ? 'Updating prices' : `${st.live_positions} of ${st.total_positions} live, ${when}`}`;
  $('#pricePill').title = st.errors.length ? `${st.errors.length} pricing issues, see Settings` : 'Prices from Yahoo Finance, about 15 minutes delayed';
  if (st.demo) { $('#pricePill').innerHTML = '<span class="dot off"></span>Demo · synthetic prices'; $('#pricePill').title = 'All balances, payments and prices are invented demo data.'; }
}
let lastView = 'overview';
function route() {
  const hash = decodeURIComponent(location.hash.slice(1) || 'overview');
  if (hash === 'chat') { openChat(); history.replaceState(null, '', '#' + lastView); return; }
  if (hash === 'accounts') { history.replaceState(null, '', '#overview'); setTimeout(() => { const c = $('#acctCard'); if (c) c.scrollIntoView({behavior: 'smooth', block: 'start'}); }, 300); }
  view = hash.startsWith('account/') ? 'account' : hash === 'accounts' ? 'overview' : hash;
  if (view === 'account') ui.account = hash.slice(8);
  if (!TITLES[view]) view = 'overview';
  lastView = view === 'account' ? hash : view;
  const navOf = view === 'account' ? 'overview' : view;
  $$('#nav a').forEach(a => a.setAttribute('aria-current', a.getAttribute('href') === '#' + navOf ? 'page' : 'false'));
  $('#title').textContent = view === 'account' ? ui.account : TITLES[view];
  document.title = $('#title').textContent + ', Wealth';
  closeMenus();
  if (typeof closePop === 'function') closePop();
  renderRangeSlot();
  if (S || ['import', 'settings', 'spending'].includes(view)) renderView();
  else $('#view').innerHTML = skeleton();
  window.scrollTo(0, 0);
  if (CP.open) renderChat();
}
function renderView() {
  if (!S && !['import', 'spending', 'settings'].includes(view)) { $('#view').innerHTML = skeleton(); return; }
  ({overview, holdings, account: accountPage, cash, spending: () => spendingPage(), history: historyPage, plan: planPage, taxes: taxesPage,
    advice: advicePage, import: importView, settings})[view]();
}

/* ---------- shared pieces ---------- */
function allPositions() { return S.positions; }
function combined(rows) {
  const m = new Map();
  for (const p of rows) {
    const k = p.isin || p.name.toLowerCase();
    const c = m.get(k);
    if (!c) { m.set(k, {...p, accounts: [p.account]}); continue; }
    c.units += p.units; c.value += p.value; c.day_change += p.day_change;
    c.cost = c.cost != null && p.cost != null ? c.cost + p.cost : null;
    c.profit = c.profit != null && p.profit != null ? c.profit + p.profit : null;
    c.live = c.live && p.live; c.accounts.push(p.account);
  }
  for (const c of m.values()) {
    c.price = c.units ? c.value / c.units : c.price;
    c.since_buy_pct = c.cost ? (c.value / c.cost - 1) * 100 : null;
    c.account = c.accounts.join(', ');
  }
  return [...m.values()];
}
function allocation(by) {
  const t = S.totals;
  let parts;
  if (by === 'account') {
    parts = S.accounts.map(a => [a.name, a.value + a.cash]);
    parts.push([S.managed.name, t.managed], ['Savings & cash', t.savings]);
  } else {
    const g = {};
    for (const p of S.positions) if (!p.managed) g[TYPE_OF(p.category)] = (g[TYPE_OF(p.category)] || 0) + p.value;
    const cash = S.accounts.reduce((s, a) => s + a.cash, 0);
    parts = [['Managed portfolio', t.managed], ['Savings & cash', t.savings + cash], ...Object.entries(g)];
  }
  parts = parts.filter(p => Math.abs(p[1]) > 0.5).sort((a, b) => b[1] - a[1]);
  if (parts.length > 6) { const rest = parts.splice(5); parts.push(['Other', rest.reduce((s, p) => s + p[1], 0)]); }
  return parts;
}
function maturities() {
  const out = [];
  for (const s of S.savings) if (s.maturity) out.push({name: s.name, date: s.maturity, value: s.value, kind: 'Deposit'});
  const seen = new Set();
  for (const p of S.positions) if (p.maturity && !seen.has(p.name)) { seen.add(p.name); out.push({name: p.name, date: p.maturity, value: p.value, kind: 'Bond'}); }
  return out.sort((a, b) => a.date.localeCompare(b.date));
}
function monthsUntil(d) {
  const [y, m] = d.split('-').map(Number); const n = new Date();
  const months = (y - n.getFullYear()) * 12 + (m - 1 - n.getMonth());
  return months <= 0 ? 'this month' : months === 1 ? 'in 1 month' : months < 24 ? `in ${months} months` : `in ${(months / 12).toFixed(1)} years`;
}
function seg(id, options, current) {
  return `<div class="seg" data-seg="${id}">${options.map(([v, l]) => `<button type="button" data-v="${v}" aria-pressed="${v === current}">${l}</button>`).join('')}</div>`;
}
function onSeg(id, fn) {
  const el = $(`[data-seg="${id}"]`); if (!el) return;
  el.onclick = e => { const b = e.target.closest('button'); if (b) fn(b.dataset.v); };
}

function niceTicks(min, max, n = 4) {
  const span = max - min || Math.abs(max) || 1;
  const step0 = span / n, mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map(f => f * mag).find(s => s >= step0);
  const lo = Math.floor(min / step) * step, hi = Math.ceil(max / step) * step;
  const out = []; for (let v = lo; v <= hi + step / 2; v += step) out.push(v);
  return out;
}
/* ---------- savings plans ---------- */
const FREQ = {weekly: 'every week', biweekly: 'every 2 weeks', monthly: 'every month', quarterly: 'every quarter'};
function planFor(p) {
  const x = (S.savings_plans || []).find(x => x.active && x.account === p.account && (x.isin ? x.isin === p.isin : x.instrument === p.name));
  return x ? `Savings plan: €${x.amount_eur} ${FREQ[x.frequency] || x.frequency}` : '';
}
function plansCard() {
  const P = S.savings_plans || [];
  const running = P.filter(x => x.active), per = running.reduce((s, x) => s + x.per_month, 0);
  return `<section class="card" data-card="plans">
    <div class="card-head"><div><h2>Savings plans</h2><p class="sub">${running.length ? `${running.length} running, about ${eur(per)} a month, ${eur(per * 12)} a year` : 'None yet'}</p></div><button class="btn ghost" id="planAdd">Add</button></div>
    ${P.length ? `<div class="table-wrap"><table><thead><tr><th>Plan</th><th class="num">Amount</th><th>How often</th><th>Next buy</th><th></th></tr></thead><tbody>
      ${P.map((x, i) => `<tr class="${x.active ? '' : 'muted'}"><td><div class="nm">${esc(x.instrument)}</div><div class="meta">${esc(x.account)}${x.since ? ', since ' + fdate(x.since) : ''}${x.executions ? `, ${x.executions} buys` : ''}</div></td>
        <td class="num">${eur(x.amount_eur, x.amount_eur % 1 ? 2 : 0)}</td><td>${esc(FREQ[x.frequency] || x.frequency)}${x.day ? ` on day ${x.day}` : ''}</td>
        <td>${x.active ? (x.next ? fdate(x.next) : '') : 'stopped'}</td><td class="num"><button class="btn ghost" data-plan="${i}">Edit</button></td></tr>`).join('')}
    </tbody></table></div>` : ''}
  </section>`;
}
function wirePlans() {
  const fields = x => [
    {k: 'instrument', label: 'Fund or stock', type: 'text', value: x.instrument || ''},
    {k: 'account', label: 'Account', type: 'text', value: x.account || 'Trade Republic'},
    {k: 'amount_eur', label: 'Amount per buy (€)', type: 'number', value: x.amount_eur ?? ''},
    {k: 'frequency', label: 'How often: weekly, biweekly, monthly or quarterly', type: 'text', value: x.frequency || 'monthly'},
    {k: 'day', label: 'Day of the month (monthly or quarterly)', type: 'number', value: x.day ?? ''},
    {k: 'active', label: 'Running', type: 'checkbox', value: x.active ?? true}];
  $('#planAdd').onclick = () => form('Add savings plan', fields({}), v => edit({section: 'savings_plans', action: 'add', fields: v}, 'Plan added'));
  $$('[data-plan]').forEach(b => b.onclick = () => { const i = +b.dataset.plan, x = S.savings_plans[i];
    form('Edit ' + x.instrument, fields(x), v => edit({section: 'savings_plans', index: i, fields: v}, 'Plan saved'),
      () => edit({section: 'savings_plans', action: 'delete', index: i}, 'Plan removed')); });
}

/* ---------- chat ---------- */
function md(text) {
  // ```chart blocks become clickable charts, ```actions become buttons, other fences become code, the rest is Markdown
  return text.split(/```(\w*)[^\n]*\n([\s\S]*?)```/).map((part, i, all) => {
    if (i % 3 === 1) return '';
    if (i % 3 === 2) {
      if (all[i - 1] === 'chart') { try { return chartHtml({...JSON.parse(part), pick: 'chat'}); } catch { return '<div class="muted small">(chart could not be drawn)</div>'; } }
      if (all[i - 1] === 'actions') return actionsHtml(part);
      return `<pre>${esc(part)}</pre>`;
    }
    return mdText(part);
  }).join('');
}
const fmtV = (v, unit, compact) => {
  if (unit === '%') return `${v < 0 ? '−' : ''}${Math.abs(v).toFixed(Math.abs(v) < 10 && !(compact && Number.isInteger(v)) ? 1 : 0)}%`;
  const a = Math.abs(v), s = v < 0 ? '−' : '', c = unit === '€' ? '€' : '';
  if (compact && a >= 1e6) return `${s}${c}${(a / 1e6).toFixed(1)}m`;
  if (compact && a >= 1e4) return `${s}${c}${Math.round(a / 1e3)}k`;
  return `${s}${c}${a.toLocaleString('en-GB', {maximumFractionDigits: a < 100 && unit !== '€' ? 2 : 0})}`;
};
const CHART_DATA = {};
let chartSeq = 0;
let CHART_W = 640;  // the chat panel draws its charts narrower
function chartHtml(c, width = CHART_W) {
  // every chart keeps its numbers, for downloads and for Claude; chat charts can be clicked open
  const id = 'c' + (++chartSeq);
  CHART_DATA[id] = c;
  delete CHART_DATA['c' + (chartSeq - 400)];
  if (c.pick === 'chat') { PICKS['chart:' + id] = (i, k) => chatDrill(c, i, k); c = {...c, pick: 'chart:' + id}; }
  const wrap = html => `<div class="c-box" data-chart="${id}"${typeof c.pick === 'string' ? ` data-pick="${c.pick}"` : ''}>${html}</div>`;
  const labels = (c.labels || []).map(String), unit = c.unit || '';
  const series = (c.series || []).slice(0, c.type === 'split' ? 1 : c.type === 'stacked' ? SERIES.length : 4).map((s, k) => ({name: String(s.name || ''), values: (s.values || []).map(Number), color: s.color || col(k)}));
  if (!labels.length || !series.length) throw new Error('empty');
  const tip = (lab, s, v) => esc(`${lab}${s ? ', ' + s : ''}: ${fmtV(v, unit)}`);
  const px = i => c.xkeys ? ` data-x="${esc(c.xkeys[i])}"` : '';
  const legend = series.length > 1 || c.type === 'stacked' ? `<div class="c-legend">${series.map(s => `<span data-series="${esc(s.name)}"><i style="background:${s.color}"></i>${esc(s.name)}</span>`).join('')}</div>` : '';
  const title = c.title ? `<div class="c-title">${esc(c.title)}</div>` : '';
  let svg = '';
  if (c.type === 'split') {
    let vals = series[0].values.map(v => Math.max(0, v));
    if (vals.length > SERIES.length) {
      // never reuse a color: keep the five largest parts and fold the rest into Other
      const order = vals.map((v, i) => i).sort((a, b) => vals[b] - vals[a]);
      const keep = order.slice(0, SERIES.length - 1).sort((a, b) => a - b);
      const rest = order.slice(SERIES.length - 1).reduce((s, i) => s + vals[i], 0);
      labels.splice(0, labels.length, ...keep.map(i => labels[i]), 'Other');
      vals = [...keep.map(i => vals[i]), rest];
    }
    const tot = vals.reduce((a, b) => a + b, 0) || 1;
    return wrap(`${title}<div class="alloc">${vals.map((v, i) => `<div data-s="${esc(labels[i])}" data-tip="${tip(labels[i], '', v)} (${(v / tot * 100).toFixed(0)}%)" style="flex:${v};background:${col(i)}"></div>`).join('')}</div>
      <div class="legend">${vals.map((v, i) => `<div class="row" data-series="${esc(labels[i])}"><span class="sw" style="background:${col(i)}"></span><span>${esc(labels[i])}</span><span class="num">${fmtV(v, unit)}</span><span class="pct">${(v / tot * 100).toFixed(0)}%</span></div>`).join('')}</div>`);
  }
  const all = series.flatMap(s => s.values).filter(Number.isFinite);
  const stackSum = sign => labels.map((_, i) => series.reduce((s, x) => s + (sign > 0 ? Math.max(0, x.values[i] || 0) : Math.min(0, x.values[i] || 0)), 0));
  const lo = c.type === 'stacked' ? Math.min(0, ...stackSum(-1)) : Math.min(0, ...all);
  const hi = c.type === 'stacked' ? Math.max(0, ...stackSum(1)) : Math.max(0, ...all);
  if (c.type === 'hbar') {
    const rowH = series.length > 1 ? 14 * series.length + 10 : 26, W = width, lw = 150, vw = 70, H = labels.length * rowH + 6;
    const X = v => lw + (v - lo) / ((hi - lo) || 1) * (W - lw - vw * (lo < 0 ? 2 : 1)) + (lo < 0 ? vw : 0);
    const bh = series.length > 1 ? 12 : 16;
    svg = `<svg viewBox="0 0 ${W} ${H}" class="c-svg">${lo < 0 ? `<line class="c-base" x1="${X(0)}" x2="${X(0)}" y1="0" y2="${H}"/>` : ''}
      ${labels.map((l, r) => `<text class="c-lab" x="${lw - 10}" y="${r * rowH + rowH / 2 + 4}" text-anchor="end">${esc(l.length > 22 ? l.slice(0, 21) + '…' : l)}</text>` +
        series.map((s, k) => { const v = s.values[r] ?? 0, y = r * rowH + (rowH - bh * series.length - 2 * (series.length - 1)) / 2 + k * (bh + 2);
          const x0 = Math.min(X(0), X(v)), w = Math.max(1.5, Math.abs(X(v) - X(0)));
          const fill = series.length === 1 && v < 0 ? 'var(--loss)' : s.color;
          return `<rect data-s="${esc(s.name)}" data-tip="${tip(l, series.length > 1 ? s.name : '', v)}"${c.pick ? ` data-pt="${r}|${k}"` : ''} x="${x0}" y="${y}" width="${w}" height="${bh}" rx="3" fill="${fill}"/>` +
            (series.length === 1 ? `<text class="c-val" x="${v < 0 ? x0 - 6 : x0 + w + 6}" y="${y + bh / 2 + 4}" text-anchor="${v < 0 ? 'end' : 'start'}">${fmtV(v, unit, true)}</text>` : ''); }).join('')).join('')}</svg>`;
  } else {
    const W = width, H = 240, pl = 56, pr = 12, pt = 12, pb = 28;
    const ticks = niceTicks(lo, hi), y0 = ticks[0], y1 = ticks[ticks.length - 1];
    const Y = v => pt + (1 - (v - y0) / ((y1 - y0) || 1)) * (H - pt - pb);
    const n = labels.length, every = Math.ceil(n / 8);
    const grid = ticks.map(v => `<line class="c-grid" x1="${pl}" x2="${W - pr}" y1="${Y(v)}" y2="${Y(v)}"/><text class="c-ax" x="${pl - 8}" y="${Y(v) + 4}" text-anchor="end">${fmtV(v, unit, true)}</text>`).join('');
    if (c.type === 'line') {
      const X = i => pl + (n === 1 ? (W - pl - pr) / 2 : i / (n - 1) * (W - pl - pr));
      svg = `<svg viewBox="0 0 ${W} ${H}" class="c-svg">${grid}
        ${labels.map((l, i) => i % every === 0 || i === n - 1 ? `<text class="c-ax" x="${X(i)}" y="${H - 8}" text-anchor="${i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'}">${esc(l)}</text>` : '').join('')}
        ${series.map((s, k) => `<polyline data-s="${esc(s.name)}" fill="none" stroke="${s.color}" stroke-width="2" stroke-linejoin="round" points="${s.values.map((v, i) => `${X(i)},${Y(v)}`).join(' ')}"/>` +
          s.values.map((v, i) => `<circle data-tip="${tip(labels[i], series.length > 1 ? s.name : '', v)}" cx="${X(i)}" cy="${Y(v)}" r="${n <= 24 ? 4 : 9}" fill="${n <= 24 ? s.color : 'transparent'}" stroke="${n <= 24 ? 'var(--surface-2)' : 'none'}" stroke-width="2"/>`).join('')).join('')}</svg>`;
    } else if (c.type === 'stacked') {
      const band = (W - pl - pr) / n, bw = Math.min(56, band * 0.62);
      svg = `<svg viewBox="0 0 ${W} ${H}" class="c-svg">${grid}<line class="c-base" x1="${pl}" x2="${W - pr}" y1="${Y(0)}" y2="${Y(0)}"/>
        ${labels.map((l, i) => {
          const x = pl + band * i + (band - bw) / 2;
          let up = 0, down = 0, total = 0;
          const segs = series.map((s, k) => {
            const v = s.values[i] || 0; total += v;
            if (!v) return '';
            const from = v > 0 ? up : down, to = from + v;
            if (v > 0) up = to; else down = to;
            return `<rect data-s="${esc(s.name)}" data-tip="${tip(l, s.name, v)}"${c.pick ? ` data-pt="${i}|${k}"` : ''}${px(i)} x="${x}" y="${Math.min(Y(from), Y(to))}" width="${bw}" height="${Math.max(1, Math.abs(Y(to) - Y(from)))}" fill="${s.color}" stroke="var(--surface)" stroke-width="1.5"/>`;
          }).join('');
          return (i % every === 0 ? `<text class="c-ax" x="${x + bw / 2}" y="${H - 8}" text-anchor="middle">${esc(l)}</text>` : '') + segs +
            (n <= 12 && total ? `<text class="c-val" x="${x + bw / 2}" y="${Y(up) - 6}" text-anchor="middle">${fmtV(total, unit, true)}</text>` : '');
        }).join('')}</svg>`;
    } else {
      const band = (W - pl - pr) / n, gap = 2, bw = Math.min(46, (band * 0.7 - gap * (series.length - 1)) / series.length);
      svg = `<svg viewBox="0 0 ${W} ${H}" class="c-svg">${grid}<line class="c-base" x1="${pl}" x2="${W - pr}" y1="${Y(0)}" y2="${Y(0)}"/>
        ${labels.map((l, i) => {
          const cx = pl + band * i + band / 2, start = cx - (bw * series.length + gap * (series.length - 1)) / 2;
          return (i % every === 0 ? `<text class="c-ax" x="${cx}" y="${H - 8}" text-anchor="middle">${esc(l.length > 12 ? l.slice(0, 11) + '…' : l)}</text>` : '') +
            series.map((s, k) => { const v = s.values[i] ?? 0, y = Math.min(Y(0), Y(v)), h = Math.max(1.5, Math.abs(Y(v) - Y(0)));
              const fill = series.length === 1 && v < 0 ? 'var(--loss)' : s.color;
              return `<rect data-s="${esc(s.name)}" data-tip="${tip(l, series.length > 1 ? s.name : '', v)}"${c.pick ? ` data-pt="${i}|${k}"` : ''}${px(i)} x="${start + k * (bw + gap)}" y="${y}" width="${bw}" height="${h}" rx="3" fill="${fill}"/>`; }).join('');
        }).join('')}</svg>`;
    }
  }
  return wrap(`${title}${legend}${svg}`);
}
function mdText(text) {
  // small, safe Markdown: escape first, then add formatting
  const lines = esc(text).split('\n'), out = [];
  let list = null, table = [];
  // links open in a new tab; a bare address shows just its site name
  const link = (href, label) => `<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`;
  const links = s => s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_, t, u) => link(u, t))
    .replace(/(^|[\s(])(https?:\/\/[^\s<)]+[^\s<).,;:])/g, (_, pre, u) => pre + link(u, u.replace(/^https?:\/\/(www\.)?/, '').split('/')[0]));
  const inline = s => links(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/(^|[^*])\*([^*]+)\*/g, '$1<i>$2</i>').replace(/`([^`]+)`/g, '<code>$1</code>');
  const flushList = () => { if (list) { out.push(`<${list.t}>${list.items.map(i => `<li>${inline(i)}</li>`).join('')}</${list.t}>`); list = null; } };
  const flushTable = () => {
    if (!table.length) return;
    const rows = table.filter(r => !/^\|?\s*:?-{2,}/.test(r)).map(r => r.replace(/^\||\|$/g, '').split('|').map(c => inline(c.trim())));
    out.push(`<div class="table-wrap"><table><thead><tr>${rows[0].map(c => `<th>${c}</th>`).join('')}</tr></thead><tbody>${rows.slice(1).map(r => `<tr>${r.map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`);
    table = [];
  };
  for (const l of lines) {
    if (/^\s*\|/.test(l)) { flushList(); table.push(l.trim()); continue; } else flushTable();
    let m;
    if ((m = l.match(/^\s*[-*•]\s+(.*)/))) { if (!list || list.t !== 'ul') { flushList(); list = {t: 'ul', items: []}; } list.items.push(m[1]); continue; }
    if ((m = l.match(/^\s*\d+[.)]\s+(.*)/))) { if (!list || list.t !== 'ol') { flushList(); list = {t: 'ol', items: []}; } list.items.push(m[1]); continue; }
    flushList();
    if ((m = l.match(/^#{1,4}\s+(.*)/))) out.push(`<h4>${inline(m[1])}</h4>`);
    else if (l.trim()) out.push(`<p>${inline(l)}</p>`);
  }
  flushList(); flushTable();
  return out.join('');
}
function stepsHtml(steps) {
  // the last few things the AI did, newest at the bottom
  const recent = (steps || []).slice(-4);
  return `<div class="steps">${recent.slice(0, -1).map(s => `<div class="step old">${esc(s)}</div>`).join('')}
    <div class="step now"><span class="spinner"></span> ${esc(recent[recent.length - 1] || 'Thinking about your numbers')}</div></div>`;
}
function watchProgress(pid, isBusy, target) {
  // poll what the AI is doing and update just that bubble, so typing is not interrupted
  const tick = async () => {
    if (!isBusy()) return;
    try {
      const r = await fetch('/api/progress?id=' + encodeURIComponent(pid), {cache: 'no-store'});
      const j = await r.json();
      const el = $(target);
      if (el && j.steps) el.innerHTML = stepsHtml(j.steps);
      const box = el && el.closest('.panel-body, .msgs');
      if (box) box.scrollTop = box.scrollHeight;
    } catch {}
    if (isBusy()) setTimeout(tick, 900);
  };
  setTimeout(tick, 500);
}
function changedBar(m, i) {
  if (!m.undo) return '';
  return m.undone ? '<div class="changed muted">This change was undone.</div>'
    : `<div class="changed"><span>Your data was updated.</span><button class="btn" data-undo="${i}">Undo</button></div>`;
}
function attachTips(host, area) {
  // one shared tooltip for every chart mark inside `area`
  const tipEl = document.createElement('div'); tipEl.className = 'tip c-tip'; tipEl.hidden = true; host.appendChild(tipEl);
  area.addEventListener('mousemove', e => {
    const t = e.target.closest('[data-tip]');
    if (!t) { tipEl.hidden = true; return; }
    const r = host.getBoundingClientRect();
    tipEl.textContent = t.dataset.tip; tipEl.hidden = false;
    tipEl.style.left = e.clientX - r.left + 'px'; tipEl.style.top = e.clientY - r.top - 8 + 'px';
  });
  area.addEventListener('mouseleave', () => { tipEl.hidden = true; });
}

/* ---------- import ---------- */
function importPage() {
  const I = ui.imp;
  const hasKey = S ? !!S.status.ai_mode : true;
  $('#view').innerHTML = `<div class="stack-y">
    ${I.result ? `<section class="card msg-like"><div class="card-head"><h2>${I.result.undone ? 'Import undone' : 'Import done'}</h2>
        ${I.result.undo && !I.result.undone ? '<button class="btn" id="undoImport">Undo</button>' : ''}</div>${md(I.result.summary)}</section>` : ''}
    ${!hasKey ? '<div class="banner warn">No AI available to read files. See <a href="#settings">Settings</a>.</div>' : ''}
    <section class="card">
      <h2>Import screenshots and files</h2>
      <p class="sub">Drop anything: screenshots, transaction lists, yearly statements, CSV or Excel exports, PDFs, or a zip holding a whole folder of them, from any bank, broker or crypto exchange. The AI updates your investments and balances, adds new accounts when needed, and builds your history over the years. Payment account exports, statements and screenshots of payments (current account, credit card) go to <a href="#spending">Spending</a> automatically. Every import can be undone.</p>
      <div class="drop" id="drop" tabindex="0" role="button" aria-label="Choose files"><strong>Drop screenshots or files here</strong><span class="muted">Images, CSV, Excel, PDF, text, or a zip of them. Click to choose, or paste with Ctrl+V</span></div>
      <input type="file" id="file" accept="image/*,.csv,.tsv,.txt,.json,.xml,.pdf,.xlsx,.xls,.xlsm,.zip" multiple hidden>
      <div class="thumbs">${I.images.map((im, i) => im.url
        ? `<div class="thumb"><img src="${im.url}" alt="${esc(im.name)}"><button data-rm="${i}" aria-label="Remove">×</button></div>`
        : `<div class="thumb file"><span class="ext">${esc(im.name.split('.').pop().toUpperCase().slice(0, 4))}</span><span class="fn">${esc(im.name)}</span><button data-rm="${i}" aria-label="Remove">×</button></div>`).join('')}</div>
      <div class="field" style="margin-top:16px">Note for the AI (optional)
        <textarea id="note" rows="2" placeholder="For example: these are all investments in my ABN AMRO managed portfolio">${esc(I.note)}</textarea></div>
      ${I.error ? `<div class="banner err" style="margin-bottom:12px">${esc(I.error)}</div>` : ''}
      <button class="btn primary" id="analyse" ${!I.images.length || I.busy || !hasKey ? 'disabled' : ''}>${I.busy ? '<span class="spinner"></span> Importing' : `Import ${I.images.length || ''} file${I.images.length === 1 ? '' : 's'}`}</button>
      ${I.busy ? `<div class="card working-box" id="impSteps">${stepsHtml(I.steps)}</div>` : ''}
    </section>
    <section class="card"><h2>Tips</h2><p class="sub" style="margin:0">Yearly statements are the best source for history. Very long transaction lists work, but the AI reads them as text, so check the totals. A Trade Republic Transaction_export.csv on its own is calculated exactly, without AI. You can also just tell Claude what changed (press /).</p></section>
    <div id="importExtras" class="stack-y"></div>
  </div>`;
  if ($('#undoImport')) $('#undoImport').onclick = async () => {
    try { await post('/api/undo', {id: I.result.undo}); I.result.undone = true; toast('Import undone'); await load(); } catch (e) { toast(e.message); }
    importView();
  };
  const drop = $('#drop'), file = $('#file');
  drop.onclick = () => file.click();
  drop.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); file.click(); } };
  file.onchange = () => addFiles(file.files);
  drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
  drop.ondragleave = () => drop.classList.remove('over');
  drop.ondrop = e => { e.preventDefault(); drop.classList.remove('over'); addFiles(e.dataTransfer.files); };
  $$('[data-rm]').forEach(b => b.onclick = () => { I.images.splice(+b.dataset.rm, 1); importView(); });
  $('#note').oninput = e => { I.note = e.target.value; };
  $('#analyse').onclick = analyse;
}
document.addEventListener('paste', e => {
  if (CP.open && document.activeElement && document.activeElement.closest('#chatPanel') && e.clipboardData?.files?.length) {
    e.preventDefault(); readFiles(e.clipboardData.files).then(f => { CP.files.push(...f); renderChat(); }); return;
  }
  if (view !== 'import' || ui.imp.busy) return;
  const files = [...(e.clipboardData?.files || [])];
  if (files.length) { e.preventDefault(); addFiles(files); }
  else if (document.activeElement?.id !== 'note') {
    const text = e.clipboardData?.getData('text/plain');
    if (text && text.length > 40) { e.preventDefault(); addFiles([new File([text], 'pasted text.txt', {type: 'text/plain'})]); }
  }
});
const MIME = {csv: 'text/csv', tsv: 'text/tab-separated-values', txt: 'text/plain', json: 'application/json', xml: 'text/xml', pdf: 'application/pdf',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', xls: 'application/vnd.ms-excel', xlsm: 'application/vnd.ms-excel.sheet.macroEnabled.12',
  zip: 'application/zip'};
async function readFiles(list) {
  // images are shrunk to stay inside the AI's limits, other files are sent as they are
  const out = [];
  for (const f of [...list]) {
    try {
      if (f.type.startsWith('image/')) { out.push({name: f.name || 'screenshot.png', ...await shrink(f)}); continue; }
      const ext = (f.name.split('.').pop() || '').toLowerCase();
      if (!MIME[ext]) { toast(`${f.name}: this file type is not supported`); continue; }
      if (f.size > 25e6) { toast(`${f.name} is larger than 25 MB`); continue; }
      const data = await new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result.split(',')[1]); r.onerror = rej; r.readAsDataURL(f); });
      out.push({name: f.name, media_type: f.type || MIME[ext], data});
    } catch { toast(`Could not read ${f.name}`); }
  }
  return out;
}
async function addFiles(list) {
  ui.imp.images.push(...await readFiles(list));
  ui.imp.result = null; ui.imp.error = null;
  importView();
}
function shrink(file) {
  // keep text sharp but stay well inside the API's image limits
  return new Promise((res, rej) => {
    const img = new Image(), url = URL.createObjectURL(file);
    img.onload = () => {
      const scale = Math.min(1, 2000 / Math.max(img.width, img.height));
      const c = document.createElement('canvas');
      c.width = Math.round(img.width * scale); c.height = Math.round(img.height * scale);
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      let data = c.toDataURL('image/png'), type = 'image/png';
      if (data.length > 4.5e6) { data = c.toDataURL('image/jpeg', 0.9); type = 'image/jpeg'; }
      res({media_type: type, data: data.split(',')[1], url: data});
      URL.revokeObjectURL(url);
    };
    img.onerror = rej; img.src = url;
  });
}
async function analyse() {
  const I = ui.imp;
  I.busy = true; I.error = null; I.result = null; I.steps = []; importView();
  const pid = 'i' + Date.now() + Math.random().toString(36).slice(2, 7);
  watchProgress(pid, () => I.busy, '#impSteps');
  try {
    const r = await post('/api/import', {files: I.images.map(({name, media_type, data}) => ({name, media_type, data})),
      note: I.note, progress_id: pid});
    Object.assign(I, {images: [], note: '', result: {summary: r.summary, undo: r.undo}});
    await load();
  } catch (e) { I.error = e.message; }
  I.busy = false; importView();
}
let pendingConfirm = null;
function confirmTwice(key, msg) {
  if (pendingConfirm === key) { pendingConfirm = null; return true; }
  pendingConfirm = key; toast(msg); setTimeout(() => { if (pendingConfirm === key) pendingConfirm = null; }, 5000);
  return false;
}

/* ---------- settings ---------- */
function settingsBase() {
  const st = S ? S.status : {errors: [], has_api_key: false};
  const theme = store.get('theme', 'system');
  $('#view').innerHTML = `<div class="grid g2">
    <section class="card">
      <h2>AI import</h2>
      <p class="sub">Screenshots and files you import are sent to Claude to be read.</p>
      <div class="banner ${st.ai_mode ? 'ok' : 'warn'}" style="margin-bottom:12px">${st.ai_mode === 'api' ? 'Using your Anthropic API key (billed per import).' : st.ai_mode === 'claude_code' ? 'Using Claude Code on your normal Claude plan. No extra costs.' : 'No AI found. Install Claude Code or add an API key below.'}</div>
      <p class="sub">Optional: an API key from console.anthropic.com is a bit faster, but is billed separately. Leave it empty to keep using your Claude plan.</p>
      <form id="keyForm" class="controls" style="margin:0"><input type="password" id="key" placeholder="${st.has_api_key ? 'Key saved. Save empty to remove it' : 'sk-ant-...'}" autocomplete="off" style="flex:1" aria-label="API key"><button class="btn">Save key</button></form>
    </section>
    <section class="card">
      <h2>Prices</h2>
      <p class="sub">From Yahoo Finance, refreshed every 5 minutes, about 15 minutes delayed.</p>
      <div class="kv"><span>Live priced</span><span>${S ? `${st.live_positions} of ${st.total_positions}` : ''}</span><span>Last update</span><span>${st.last_refresh ? new Date(st.last_refresh).toLocaleString('en-GB', {dateStyle: 'medium', timeStyle: 'short'}) : 'not yet'}</span></div>
      <button class="btn" id="refresh" style="margin-top:14px">Refresh prices now</button>
      ${st.errors.length ? `<h2 style="margin-top:18px">Pricing issues</h2>${st.errors.map(e => `<div class="list-row small">${esc(e)}</div>`).join('')}` : ''}
    </section>
    <section class="card">
      <h2>Display</h2>
      <div class="controls" style="margin-top:12px">${seg('theme', [['system', 'System'], ['light', 'Light'], ['dark', 'Dark']], theme)}</div>
      <label class="check"><input type="checkbox" id="priv" ${document.body.classList.contains('private') ? 'checked' : ''}> Hide amounts (hover to reveal one)</label>
    </section>
    <section class="card" id="cloudCard">
      <h2>Cloud database (Supabase)</h2>
      <p class="sub">Keeps a copy of all investments, accounts, savings, debts, daily history and a full backup in your own Supabase database. It syncs every 15 minutes and after every change.</p>
      ${st.cloud && st.cloud.connected
        ? `<div class="banner ${st.cloud.error ? 'err' : 'ok'}" style="margin-bottom:12px">${st.cloud.error ? esc(st.cloud.error) : `Connected to ${esc(st.cloud.url.replace('https://', ''))}. ${st.cloud.last_sync ? 'Last sync ' + new Date(st.cloud.last_sync).toLocaleString('en-GB', {dateStyle: 'medium', timeStyle: 'short'}) + '.' : 'Not synced yet.'}`}</div>
           <div class="controls" style="margin:0"><button class="btn primary" id="syncNow">Sync now</button><button class="btn ghost danger" id="cloudOff">Disconnect</button></div>`
        : `<ol class="sub" style="padding-left:18px;margin:0 0 12px">
             <li>Create a free project at supabase.com (<a href="https://supabase.com/dashboard/new" target="_blank" rel="noopener">open</a>).</li>
             <li>Open SQL Editor, paste the contents of supabase-schema.sql from the app folder, and press Run.</li>
             <li>Under Project Settings, API Keys, copy the Project URL and the secret key, and paste them here.</li></ol>
           <form id="cloudForm" class="stack-y" style="margin:0">
             <input type="text" id="cloudUrl" placeholder="https://yourproject.supabase.co" aria-label="Project URL" style="width:100%">
             <input type="password" id="cloudKey" placeholder="Secret key (sb_secret_...)" autocomplete="off" aria-label="Secret key" style="width:100%">
             <button class="btn primary">Connect and sync</button></form>`}
    </section>
    <section class="card">
      <h2>Your data</h2>
      <p class="sub" style="margin:0">Everything lives in portfolio.json in the app folder. Before every change a copy goes to the backups folder (the last 50 are kept). A Trade Republic Transaction_export.csv dropped on the Import page is calculated exactly, without AI.</p>
    </section>
    <div id="settingsExtras" style="display:contents"></div>
  </div>`;
  $('#keyForm').onsubmit = async e => {
    e.preventDefault();
    try { await post('/api/settings', {anthropic_api_key: $('#key').value}); toast('Key saved'); await load(); settings(); }
    catch (err) { toast(err.message); }
  };
  $('#refresh').onclick = async () => { await post('/api/refresh', {}); toast('Refreshing prices'); setTimeout(load, 1500); };
  const cloudCall = async (url, body, btn) => {
    btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Working';
    try { const r = await post(url, body); toast(r.done); } catch (err) { toast(err.message); }
    await load(); settings();
  };
  if ($('#cloudForm')) $('#cloudForm').onsubmit = e => { e.preventDefault(); cloudCall('/api/cloud', {url: $('#cloudUrl').value, key: $('#cloudKey').value}, $('#cloudForm button')); };
  if ($('#syncNow')) $('#syncNow').onclick = e => cloudCall('/api/cloud/sync', {}, e.target);
  if ($('#cloudOff')) $('#cloudOff').onclick = e => { if (confirmTwice('cloudoff', 'Click Disconnect again to stop syncing. Your Supabase data stays where it is.')) cloudCall('/api/cloud', {url: '', key: ''}, e.target); };
  onSeg('theme', v => { store.set('theme', v); applyTheme(); settings(); });
  $('#priv').onchange = e => setPrivate(e.target.checked);
}

/* ---------- dialog form ---------- */
function form(title, fields, onSave, onDelete) {
  const f = $('#dlgForm');
  f.innerHTML = `<h3>${esc(title)}</h3>${fields.map(x => x.type === 'checkbox'
    ? `<label class="check" style="margin-bottom:12px"><input type="checkbox" name="${x.k}" ${x.value ? 'checked' : ''}> ${esc(x.label)}</label>`
    : x.type === 'select' ? `<label class="field">${esc(x.label)}<select name="${x.k}">${x.options.map(([v, l]) => `<option value="${esc(v)}" ${String(x.value ?? '') === v ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></label>`
    : `<label class="field">${esc(x.label)}<input type="${x.type}" name="${x.k}" ${x.type === 'number' ? 'step="any"' : ''} value="${esc(x.value ?? '')}"></label>`).join('')}
    <div class="dialog-actions">${onDelete ? '<button type="button" class="btn danger" id="dlgDel" style="margin-right:auto">Delete</button>' : ''}<button type="button" class="btn" id="dlgCancel">Cancel</button><button class="btn primary" value="save">Save</button></div>`;
  const dlg = $('#dlg');
  $('#dlgCancel').onclick = () => dlg.close();
  if (onDelete) $('#dlgDel').onclick = e => {
    if (e.target.dataset.armed) { dlg.close(); onDelete(); } else { e.target.dataset.armed = 1; e.target.textContent = 'Click again to delete'; }
  };
  f.onsubmit = e => {
    e.preventDefault();
    const v = {};
    for (const x of fields) {
      const el = f.elements[x.k];
      v[x.k] = x.type === 'checkbox' ? el.checked : x.type === 'number' ? (el.value === '' ? null : +el.value) : el.value;
    }
    dlg.close(); onSave(v);
  };
  dlg.showModal();
}

/* ---------- theme and privacy ---------- */
function applyTheme() {
  const t = store.get('theme', 'system');
  if (t === 'system') document.documentElement.removeAttribute('data-theme'); else document.documentElement.dataset.theme = t;
}
function setPrivate(on) { document.body.classList.toggle('private', on); store.set('private', on); }
$('#privacyBtn').onclick = () => { setPrivate(!document.body.classList.contains('private')); if (view === 'settings') settings(); };
$('#pricePill').style.cursor = 'pointer';
$('#pricePill').onclick = () => { location.hash = '#settings'; };

applyTheme();
setPrivate(store.get('private', false));
window.addEventListener('hashchange', route);
let rz, lastW = innerWidth;
window.addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(() => { if (Math.abs(innerWidth - lastW) > 40 && S) { lastW = innerWidth; renderView(); } }, 200); });
window.addEventListener('DOMContentLoaded', () => {
  shellInit();
  route();
  load().then(() => { if (view === 'import' || view === 'settings') renderView(); });
  setInterval(load, 30000);
});
