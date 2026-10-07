'use strict';
/* Spending section: payment account transactions, categories, subscriptions, trips and analytics.
   Uses helpers from app.js, charts.js and shell.js. */

const SP = {d: null, geo: null, rows: [], tab: 'overview',
  // payment accounts and spending groups to look at; empty means all
  accts: store.get('sp.accts', (a => a && a !== 'all' ? [a] : [])(store.get('sp.acct', 'all'))), focus: store.get('sp.focus', []),
  tx: {q: '', cat: 'all', month: 'all', country: 'all', status: 'all', tag: 'all', group: 'all', limit: 150}, learn: store.get('sp.learn', true), timer: null,
  pop: null, check: {queue: null, pos: 0, key: '', order: store.get('sp.checkOrder', 'big'), dir: 1, review: null, log: []}, map: null, budMonth: null, subOpen: null};
const SP_TABS = [['overview', 'Overview'], ['spending', 'Spending'], ['income', 'Income'], ['transactions', 'Transactions'],
  ['subscriptions', 'Subscriptions'], ['trips', 'Trips'], ['countries', 'Countries'],
  ['check', 'Quick check'], ['review', 'To review'], ['categories', 'Categories']];
const MON = MONTHS;
const mLabel = m => `${MON[+m.slice(5, 7) - 1]} ${m.slice(2, 4)}`;
const SRC = {user: 'set by you', rule: 'rule', auto: 'automatic', ai: 'AI', unsure: 'AI unsure'};
const TICK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
const FIXED_GROUPS = ['Housing', 'Fixed costs'];

async function loadSpending() {
  const [r] = await Promise.all([fetch('/api/spending', {cache: 'no-store'}), loadGeo()]);
  SP.d = await r.json();
  SP.geo = window.GEO;
  SP.d.subscriptions = SP.d.subscriptions || {};
  SP.cat = Object.fromEntries(SP.d.categories.map(c => [c.id, c]));
  // accounts the bank runs for investing belong to the portfolio, not to spending
  SP.invest = new Set(Object.entries(SP.d.accounts).filter(([, a]) => a.role === 'investment').map(([id]) => id));
  SP.allTx = SP.d.transactions;
  SP.d.transactions = SP.d.transactions.filter(t => !SP.invest.has(t.account));
  // what the analytics count: split payments once per category, payments left out of totals not at all
  SP.rows = SP.d.transactions.filter(t => !t.excluded).flatMap(t => t.splits ? t.splits.map(p => ({...t, amount: p.amount, category: p.category, split: true})) : [t]);
  for (const t of SP.rows) { const m = /\d\d\.\d\d\.\d\d\/(\d\d):\d\d/.exec(t.description); t.hour = m ? +m[1] : null; }
  // each spending group keeps one colour on every chart, the biggest groups first
  const gt = {};
  for (const t of SP.rows) if (kindOf(t) === 'expense') gt[groupOf(t)] = (gt[groupOf(t)] || 0) - t.amount;
  SP.gOrder = Object.keys(gt).sort((a, b) => gt[b] - gt[a]);
  const n = {};
  for (const t of SP.d.transactions) if (t.country) n[t.country] = (n[t.country] || 0) + 1;
  SP.home = Object.keys(n).sort((a, b) => n[b] - n[a])[0] || null;
  SP.accts = SP.accts.filter(a => SP.d.transactions.some(t => t.account === a));
  SP.focus = SP.focus.filter(g => SP.d.categories.some(c => c.group === g) || g === 'Uncategorised');
  // keep polling while the AI is working in the background
  clearTimeout(SP.timer);
  if (SP.d.status.ai) SP.timer = setTimeout(async () => {
    await loadSpending();
    const busy = document.activeElement && /SELECT|INPUT|TEXTAREA/.test(document.activeElement.tagName);
    if (view === 'spending' && !busy && !$('#dlg').open) spendingPage();
  }, 5000);
}
const acctName = id => (SP.d.accounts[id] || {}).name || id;
const inAcct = t => !SP.accts.length || SP.accts.includes(t.account);
// the group filter narrows spending only; money coming in stays, so income and saved still make sense
const inFocus = t => !SP.focus.length || kindOf(t) !== 'expense' || SP.focus.includes(groupOf(t));
const focusBtn = g => `<div class="pop-focus"><button type="button" class="linkish small" data-focus="${esc(g)}">${SP.focus.includes(g) ? 'Stop showing only ' : 'Show only '}${esc(g)} on these pages</button></div>`;
function toggleFocus(g) {
  SP.focus = SP.focus.includes(g) ? SP.focus.filter(x => x !== g) : [...SP.focus, g];
  store.set('sp.focus', SP.focus); closePop(); spendingPage();
}
const kindOf = t => {
  const k = t.category && SP.cat[t.category] ? SP.cat[t.category].kind : (t.amount > 0 ? 'income' : 'expense');
  // money coming in is never spending. Linked to the payment it pays back, it still lowers that payment.
  return k === 'expense' && t.amount > 0 && !t.linked_to ? 'income' : k;
};
const groupColor = g => { const i = (SP.gOrder || []).indexOf(g); return g === 'Other' || g === 'Rest' || i < 0 ? 'var(--muted)' : col(i % SERIES.length); };
function spBuckets(list, from, to) {
  // bars per day, week, month or year over the part of the period that has data
  const dates = list.map(t => t.date).sort();
  if (!dates.length) return {B: bucketer('month'), keys: []};
  const lo = from > dates[0] ? from : dates[0], hi = to < dates[dates.length - 1] ? to : dates[dates.length - 1];
  const B = bucketer(grainFor(lo, hi));
  return {B, keys: bucketsBetween(B, lo, hi)};
}
const groupOf = t => t.category && SP.cat[t.category] ? SP.cat[t.category].group : 'Uncategorised';
const catName = id => id && SP.cat[id] ? SP.cat[id].name : 'Uncategorised';
const BACK = 'Money back';
// a refund or a friend paying you back carries a spending category, so name it for what it is
const inName = t => t.category && SP.cat[t.category] && SP.cat[t.category].kind === 'expense' ? BACK : catName(t.category);
const ctyName = c => c ? (window.GEO && GEO.countries[c] ? GEO.countries[c].n : c) : 'Not known';
const needsReview = t => !t.category;
const txById = id => SP.d.transactions.find(t => t.id === id);
const amt = t => `<span class="amt ${t.amount > 0 ? 'pos' : ''}">${t.amount > 0 ? '+' : '−'}€${fmtN(Math.abs(t.amount), 2)}</span>`;
const where = t => [acctName(t.account), t.country && t.country !== SP.home ? ctyName(t.country) : ''].filter(Boolean).map(esc).join(' · ');
const spRows = () => SP.rows;
const groupKey = k => k.startsWith('group:') ? k.slice(6) : catName(k.slice(4));
const pid4 = p => p.isin || 'n:' + p.name.trim().toLowerCase();

function spRange() {
  // the shared period; rolling periods end at the last month with data, so a month without an export yet doesn't count as zero
  const last = SP.d.transactions.length ? new Date(SP.d.transactions[0].date + 'T12:00') : new Date();
  const now = new Date(), stale = last < new Date(now.getFullYear(), now.getMonth(), 1);
  const rolling = !RANGE.p.startsWith('y:') && RANGE.p !== 'ytd' && RANGE.p !== 'custom';
  const r = rangeFor(RANGE.p, stale && rolling ? last : now);
  if (r.to.startsWith('9999')) r.to = '9999-12-31';
  r.stale = stale && rolling;
  return r;
}
function txs(from, to) { return SP.rows.filter(t => t.date >= from && t.date <= to && inAcct(t) && inFocus(t)); }
function totals(list) {
  let spent = 0, income = 0;
  for (const t of list) { const k = kindOf(t); if (k === 'expense') spent -= t.amount; else if (k === 'income') income += t.amount; }
  return {spent, income, saved: income - spent, rate: income > 0 ? (income - spent) / income * 100 : null};
}
function monthsIn(list) { return [...new Set(list.map(t => t.date.slice(0, 7)))].sort(); }
function delta(now, before, inverse, label = 'vs before') {
  if (before == null || !before) return '';
  const d = (now - before) / Math.abs(before) * 100;
  const good = inverse ? d < 0 : d > 0;
  return `<span class="${good ? 'pos' : 'neg'}">${d < 0 ? '−' : '+'}${Math.abs(d).toFixed(0)}%</span> ${label}`;
}
function paymentsMatching(f) {
  // the payments behind a filter from Claude, the briefing or a chart; category and group by id or by name
  const low = x => String(x || '').toLowerCase();
  const cat = f.category && (SP.cat[f.category] ? f.category : (SP.d.categories.find(c => low(c.name) === low(f.category)) || {}).id || '__none');
  return SP.rows.filter(t => (!cat || t.category === cat) && (!f.group || low(groupOf(t)) === low(f.group))
    && (!f.merchant || low(t.merchant) === low(f.merchant) || low(t.merchant).includes(low(f.merchant)))
    && (!f.q || low(t.merchant + ' ' + t.description + ' ' + (t.note || '')).includes(low(f.q)))
    && (!f.month || t.date.startsWith(f.month)) && (!f.from || t.date >= f.from) && (!f.to || t.date <= f.to)
    && (!f.country || (f.country === 'none' ? !t.country : t.country === f.country)) && (!f.account || t.account === f.account)
    && (!f.tag || (t.tags || []).includes(low(f.tag).replace('#', ''))) && (!f.day || t.date === f.day) && (f.hour == null || t.hour === f.hour)
    && (f.weekday == null || (new Date(t.date + 'T12:00').getDay() + 6) % 7 === f.weekday)
    && (!f.kind || (f.kind === 'flow' ? kindOf(t) !== 'transfer' : kindOf(t) === f.kind)) && (!f.ids || f.ids.includes(t.id)) && (!f.key || t.key === f.key));
}
function txFilterFrom(f) {
  const cat = f.category && (SP.cat[f.category] ? f.category : (SP.d.categories.find(c => c.name.toLowerCase() === String(f.category).toLowerCase()) || {}).id);
  return {cat: cat || 'all', q: f.merchant || f.q || '', month: f.month || 'all', from: f.from || f.day || null, to: f.to || f.day || (f.from ? '9999-12-31' : null),
    country: f.country || 'all', tag: f.tag || 'all', group: f.group || 'all'};
}

/* ---------- page shell ---------- */
async function spendingPage() {
  if (!SP_TABS.some(([v]) => v === SP.tab)) SP.tab = 'overview';
  if (!SP.d) { $('#view').innerHTML = skeleton(); await loadSpending(); if (view !== 'spending') return; }
  const review = SP.d.transactions.filter(t => needsReview(t) && inAcct(t)).length;
  const count = {};
  for (const t of SP.d.transactions) count[t.account] = (count[t.account] || 0) + 1;
  const accts = Object.keys(count).sort((a, b) => count[b] - count[a]);
  $('#view').innerHTML = `<div class="stack-y" id="sp">
    <div class="sp-head">
      <div class="seg tabs" data-seg="sptab">${SP_TABS.map(([v, l]) => `<button type="button" data-v="${v}" aria-pressed="${v === SP.tab}">${l}${v === 'review' && review ? ` (${review})` : ''}</button>`).join('')}</div>
      ${accts.length > 1 ? `<div class="fchips" role="group" aria-label="Payment accounts, choose one or more">${[['all', 'All accounts'], ...accts.map(a => [a, acctName(a)])].map(([v, l]) =>
        `<button type="button" data-acct-f="${esc(v)}" aria-pressed="${v === 'all' ? !SP.accts.length : SP.accts.includes(v)}">${esc(l)}</button>`).join('')}</div>` : ''}
      ${SP.focus.length && ['overview', 'spending'].includes(SP.tab) ? `<div class="fchips focus-chips" role="group" aria-label="Spending groups shown"><span class="muted small">Only</span>${SP.focus.map(g =>
        `<button type="button" class="on" data-unfocus="${esc(g)}" aria-label="Stop filtering on ${esc(g)}"><i style="background:${groupColor(g)}"></i>${esc(g)} ×</button>`).join('')}<button type="button" class="linkish small" id="focusClear">Show all</button></div>` : ''}
    </div>
    ${SP.d.status.ai && !SP.d.status.note_tx ? `<div class="banner"><span class="spinner"></span> ${esc(SP.d.status.ai)}. This page updates by itself.</div>` : ''}
    ${SP.d.status.error ? `<div class="banner err">${esc(SP.d.status.error)}</div>` : ''}
    ${S && (S.inbox || []).some(i => i.source === 'spending') ? '<div class="banner warn">Claude has a question about some transactions it couldn\'t place. <button type="button" class="linkish" id="spInbox">Answer it</button></div>' : ''}
    <div id="spBody"></div>
  </div>`;
  onSeg('sptab', v => { SP.tab = v; closePop(); spendingPage(); });
  $$('[data-acct-f]').forEach(b => b.onclick = () => {
    const a = b.dataset.acctF;
    SP.accts = a === 'all' ? [] : SP.accts.includes(a) ? SP.accts.filter(x => x !== a) : [...SP.accts, a];
    store.set('sp.accts', SP.accts); closePop(); spendingPage();
  });
  $$('[data-unfocus]').forEach(b => b.onclick = () => toggleFocus(b.dataset.unfocus));
  if ($('#focusClear')) $('#focusClear').onclick = () => { SP.focus = []; store.set('sp.focus', []); spendingPage(); };
  if ($('#spInbox')) $('#spInbox').onclick = () => openChat();
  if (!SP.d.transactions.length && SP.tab !== 'categories') spEmpty();
  else ({overview: spOverview, spending: spSpending, income: spIncome, transactions: spTransactions,
    subscriptions: spSubs, trips: spTrips, check: spCheck, countries: spCountries, review: spReview,
    categories: spCategories})[SP.tab]();
  const sp = $('#sp');
  sp.style.position = 'relative';
  attachTips(sp, sp);
  if (SP.pop) renderPop();
}

/* ---------- drill down popover ---------- */
function openPop(make, e) {
  closePop();
  $$('.c-tip').forEach(x => x.hidden = true);
  const el = document.createElement('div');
  el.className = 'pop' + (innerWidth < 640 ? ' sheet' : '');
  el.setAttribute('role', 'dialog');
  document.body.appendChild(el);
  SP.pop = {el, make};
  renderPop();
  if (!el.classList.contains('sheet')) {
    const W = el.offsetWidth, H = el.offsetHeight;
    // opened from the chat panel or a drawer: sit beside it instead of on top of it
    const side = e.target && e.target.closest ? e.target.closest('.panel, .drawer') : null;
    const x = side && side.getBoundingClientRect().left > W + 24 ? side.getBoundingClientRect().left - W - 12 : Math.min(Math.max(12, e.clientX + 14), innerWidth - W - 12);
    const y = Math.min(Math.max(12, e.clientY - 60), innerHeight - H - 12);
    el.style.left = x + 'px'; el.style.top = y + 'px';
    el.style.transformOrigin = `${e.clientX - x}px ${e.clientY - y}px`;
  }
  setTimeout(() => {
    document.addEventListener('mousedown', popOutside);
    document.addEventListener('keydown', popKey);
    window.addEventListener('scroll', closePop, {once: true, passive: true});
  });
}
function renderPop() {
  const p = SP.pop; if (!p) return;
  let spec;
  try { spec = p.make(); } catch { spec = null; }
  if (!spec) return closePop();
  const keep = p.el.querySelector('.pop-list'), top = keep ? keep.scrollTop : 0;
  let sub, rows;
  if (spec.rows) {
    // anything that is not a payment: accounts, holdings, savings
    const tot = spec.rows.reduce((s, r) => s + (r.v || 0), 0);
    sub = `${spec.rows.length} item${spec.rows.length === 1 ? '' : 's'}, ${spec.rows.some(r => r.sign) ? sgn(tot) : eur(tot)}`;
    rows = spec.rows.map(r => `<button type="button" class="mini rowx" ${r.open ? `data-open="${esc(r.open)}"` : ''} ${r.ctx ? `data-ctx="${esc(r.ctx)}"` : ''}><span class="m"><b>${esc(r.t)}</b><span>${esc(r.s || '')}</span></span><span class="a num">${r.sign ? sgn(r.v) : eur(r.v)}</span></button>`).join('');
  } else {
    const list = [...spec.list].sort((a, b) => b.date.localeCompare(a.date)), total = list.reduce((s, t) => s + t.amount, 0);
    sub = `${list.length} payment${list.length === 1 ? '' : 's'}, ${sgn(total, 2)}`;
    rows = list.slice(0, 400).map(miniRow).join('');
  }
  p.el.innerHTML = `<div class="pop-head"><div style="min-width:0"><div class="pop-t">${esc(spec.title)}</div>
      <div class="muted small">${sub}</div></div>
      <button type="button" class="x-btn" data-x aria-label="Close">×</button></div>
    ${spec.top || ''}
    <div class="pop-list">${rows || '<div class="empty">Nothing here.</div>'}</div>
    ${spec.filter ? '<div class="pop-foot"><button type="button" class="btn ghost" data-all>Open in Transactions</button></div>' : ''}`;
  p.el.querySelector('.pop-list').scrollTop = top;
  p.el.querySelector('[data-x]').onclick = closePop;
  p.el.onclick = e => { const r = e.target.closest('[data-open-tx]'); if (r) txSheet(r.dataset.openTx); };
  if (spec.filter) p.el.querySelector('[data-all]').onclick = () => {
    Object.assign(SP.tx, {q: '', cat: 'all', month: 'all', country: 'all', status: 'all', tag: 'all', group: 'all', from: null, to: null, limit: 150}, spec.filter);
    SP.tab = 'transactions'; closePop();
    if (view === 'spending') { spendingPage(); scrollTo(0, 0); } else location.hash = '#spending';
  };
  if (spec.after) spec.after(p.el);
}
function miniRow(t) {
  return `<button type="button" class="mini ${t.excluded ? 'excluded' : ''}" data-open-tx="${t.id}" data-ctx="tx:${t.id}"><span class="d">${fdate(t.date).replace(/ \d{4}$/, '')}<i>${t.date.slice(0, 4)}</i></span>
    <span class="m"><b>${esc(t.merchant)}</b><span>${esc(catName(t.category))}${t.split ? ' (part)' : ''} · ${where(t)}</span></span>
    <span class="a num">${amt(t)}${t.checked ? `<i class="ok">${TICK}</i>` : ''}</span></button>`;
}
function popOutside(e) { if (SP.pop && !SP.pop.el.contains(e.target) && !e.target.closest('[data-pt],#dlg,[data-cty],[data-cat],[data-merchant],[data-rec],[data-link],[data-sk],[data-day],[data-heat],[data-merchant-pick],[data-sb],[data-tagpick],[data-trip],.menu,[data-open]')) closePop(); }
function popKey(e) { if (e.key === 'Escape' && !$('#dlg').open) closePop(); }
function closePop() {
  clearPicked();
  if (!SP.pop) return;
  SP.pop.el.remove(); SP.pop = null;
  document.removeEventListener('mousedown', popOutside);
  document.removeEventListener('keydown', popKey);
  window.removeEventListener('scroll', closePop);
}
const payPop = (title, f, e, extra = {}) => openPop(() => ({title, list: paymentsMatching({...f}).filter(inAcct), filter: txFilterFrom(f), ...extra}), e);

/* ---------- overview ---------- */
/* ---------- overview: spending and income side by side ---------- */
function spOverview() {
  const R = spRange(), {from, to} = R;
  const list = txs(from, to), T = totals(list);
  const months = monthsIn(list), n = Math.max(1, months.length);
  const W = Math.max(320, $('#view').clientWidth - 42), half = innerWidth > 900 ? (W - 58) / 2 : W;
  const inc = list.filter(t => kindOf(t) === 'income'), exp = list.filter(t => kindOf(t) === 'expense');
  // what you really live on: your own income against spending after the money that came back
  const back = inc.filter(t => inName(t) === BACK).reduce((s, t) => s + t.amount, 0);
  const own = inc.filter(t => !/gift/i.test(inName(t)) && inName(t) !== BACK).reduce((s, t) => s + t.amount, 0);
  // one bar per month for each side, stacked by the biggest groups
  const {B, keys} = spBuckets(list, from, to);
  const bars = (rows, by, sign, name, color) => {
    const tot = {};
    for (const t of rows) tot[by(t)] = (tot[by(t)] || 0) + sign * t.amount;
    const order = Object.keys(tot).sort((a, b) => tot[b] - tot[a]);
    const keep = order.length > SERIES.length ? order.slice(0, SERIES.length - 1) : order;
    const series = keep.map(k => ({name: k, color: color && color(k), values: keys.map(b => rows.filter(t => B.key(t.date) === b && by(t) === k).reduce((s, t) => s + sign * t.amount, 0))}));
    const member = (t, k) => k < keep.length ? by(t) === keep[k] : !keep.includes(by(t));
    if (order.length > keep.length) {
      const label = keep.includes('Other') ? 'Rest' : 'Other';  // never two legend entries with the same name
      series.push({name: label, color: color && 'var(--muted)', values: keys.map(b => rows.filter(t => B.key(t.date) === b && !keep.includes(by(t))).reduce((s, t) => s + sign * t.amount, 0))});
    }
    return {chart: {type: 'stacked', unit: '€', labels: keys.map(B.label), series, pick: name, xkeys: keys}, tot, order, member, rows};
  };
  const S = bars(exp, t => groupOf(t), -1, 'ovSpend', groupColor), I = bars(inc, t => inName(t), 1, 'ovInc');
  PICKS.ovSpend = (i, k) => ({title: `${B.label(keys[i])} · ${S.chart.series[k].name}`, filter: B.span(keys[i]),
    list: S.rows.filter(t => B.key(t.date) === keys[i] && S.member(t, k))});
  PICKS.ovInc = (i, k) => ({title: `${B.label(keys[i])} · ${I.chart.series[k].name}`, filter: B.span(keys[i]),
    list: I.rows.filter(t => B.key(t.date) === keys[i] && I.member(t, k))});
  PICKS.ovGrp = g => ({title: g, filter: {from, to, group: g}, list: exp.filter(t => groupOf(t) === g), top: focusBtn(g)});
  PICKS.ovCat = c => ({title: c, filter: {from, to}, list: inc.filter(t => inName(t) === c)});
  const bar = (entries, total, key) => entries.slice(0, 7).map(([k, v]) => `<button class="barrow" data-${key}="${esc(k)}"${key === 'ogrp' ? ` data-series="${esc(k)}"` : ''}><span class="bl">${key === 'ogrp' ? `<i class="sw-dot" style="background:${groupColor(k)}"></i>` : ''}<b>${esc(k)}</b></span>
    <span class="bb"><i style="width:${v / entries[0][1] * 100}%"></i></span><span class="bv">${eur(v)}<span class="muted small">${total ? (v / total * 100).toFixed(0) : 0}%</span></span></button>`).join('');
  const sEntries = Object.entries(S.tot).sort((a, b) => b[1] - a[1]), iEntries = Object.entries(I.tot).sort((a, b) => b[1] - a[1]);
  $('#spBody').innerHTML = `<div class="stack-y">
    <div class="grid g4">
      <div class="card tile"><div class="k">Money in</div><div class="v">${eur(T.income)}</div><div class="n">${eur(T.income / n)} a month</div></div>
      <div class="card tile"><div class="k">Spent</div><div class="v">${eur(T.spent)}</div><div class="n">${eur(T.spent / n)} a month</div></div>
      <div class="card tile"><div class="k">Left over</div><div class="v">${sgn(T.saved)}</div><div class="n">${T.rate == null ? 'no money in' : `${T.rate.toFixed(0)}% of money in`}</div></div>
      <div class="card tile"><div class="k">On what you earn yourself</div><div class="v">${sgn(own - (T.spent - back))}</div><div class="n">gifts left out</div></div>
    </div>
    <div class="grid g2">
      <section class="card" data-pick="ovSpend"><div class="card-head"><h2>Spending per ${B.noun}</h2><button class="btn ghost" data-go="spending">Details</button></div>
        ${keys.length ? chartHtml(S.chart, half) : '<div class="empty">Nothing in this period.</div>'}</section>
      <section class="card" data-pick="ovInc"><div class="card-head"><h2>Income per ${B.noun}</h2><button class="btn ghost" data-go="income">Details</button></div>
        ${keys.length ? chartHtml(I.chart, half) : '<div class="empty">Nothing in this period.</div>'}</section>
    </div>
    <div class="grid g2">
      <section class="card"><div class="card-head"><h2>Where the money goes</h2><button class="btn ghost" data-go="spending">All</button></div>
        ${bar(sEntries, T.spent, 'ogrp') || '<div class="empty">Nothing spent.</div>'}</section>
      <section class="card"><div class="card-head"><h2>Where it comes from</h2><button class="btn ghost" data-go="income">All</button></div>
        ${bar(iEntries, T.income, 'oinc') || '<div class="empty">Nothing yet.</div>'}</section>
    </div>
  </div>`;
  $$('[data-go]').forEach(b => b.onclick = () => { SP.tab = b.dataset.go; spendingPage(); });
  $$('[data-ogrp]').forEach(b => b.onclick = e => openPop(() => PICKS.ovGrp(b.dataset.ogrp), e));
  $$('[data-oinc]').forEach(b => b.onclick = e => openPop(() => PICKS.ovCat(b.dataset.oinc), e));
}

function spSpending() {
  const R = spRange(), {from, to} = R;
  // compare with the chosen period, or with the period before when the data covers all of it
  const first = SP.d.transactions.length ? SP.d.transactions[SP.d.transactions.length - 1].date : '9999';
  const C = R.cmp || (R.prev && first <= R.prev[0] ? {from: R.prev[0], to: R.prev[1], label: 'the period before', auto: true} : null);
  const list = txs(from, to), T = totals(list), P = C ? totals(txs(C.from, C.to)) : null;
  const months = monthsIn(list), nMonths = Math.max(1, months.length);
  const W = Math.max(320, $('#view').clientWidth - 42), half = innerWidth > 900 ? (W - 58) / 2 : W;
  const exp = list.filter(t => kindOf(t) === 'expense');
  const period = {from, to};
  // spending per day, week, month or year, stacked by group
  const {B, keys: buckets} = spBuckets(list, from, to);
  const bucket = t => B.key(t.date), span = B.span;
  const groupTotals = {};
  for (const t of exp) groupTotals[groupOf(t)] = (groupTotals[groupOf(t)] || 0) - t.amount;
  const groups = Object.keys(groupTotals).sort((a, b) => groupTotals[b] - groupTotals[a]);
  const keep = groups.length > SERIES.length ? groups.slice(0, SERIES.length - 1) : groups;
  const inSeries = (t, k) => k < keep.length ? groupOf(t) === keep[k] : !keep.includes(groupOf(t));
  const series = keep.map(g => ({name: g, color: groupColor(g)}));
  if (groups.length > keep.length) series.push({name: 'Other', color: 'var(--muted)'});
  series.forEach((s, k) => s.values = buckets.map(b => exp.filter(t => bucket(t) === b && inSeries(t, k)).reduce((v, t) => v - t.amount, 0)));
  const labels = buckets.map(B.label);
  PICKS.monthly = (i, k) => ({title: `${labels[i]} · ${series[k].name}`, filter: span(buckets[i]), list: exp.filter(t => bucket(t) === buckets[i] && inSeries(t, k))});
  const inout = {type: 'bar', unit: '€', labels, pick: 'inout', xkeys: buckets, series: [
    {name: 'Income', values: buckets.map(b => totals(list.filter(t => bucket(t) === b)).income)},
    {name: 'Spending', values: buckets.map(b => totals(list.filter(t => bucket(t) === b)).spent)}]};
  PICKS.inout = (i, k) => ({title: `${labels[i]} · ${k ? 'Spending' : 'Income'}`, filter: span(buckets[i]), list: list.filter(t => bucket(t) === buckets[i] && kindOf(t) === (k ? 'expense' : 'income'))});
  // categories with a six month trend and the comparison
  const catSum = l => { const m = {}; for (const t of l) if (kindOf(t) === 'expense') m[t.category || ''] = (m[t.category || ''] || 0) - t.amount; return m; };
  const cs = catSum(list), cp = C ? catSum(txs(C.from, C.to)) : {};
  const cats = Object.entries(cs).filter(([, v]) => v > 0.5).sort((a, b) => b[1] - a[1]);
  const maxCat = Math.max(1, ...cats.map(c => c[1]), ...(R.cmp ? Object.values(cp) : []));
  const last6 = [...new Set(SP.rows.map(t => t.date.slice(0, 7)))].filter(m => m <= to.slice(0, 7)).sort().slice(-6);
  const trendOf = id => last6.map(m => SP.rows.filter(t => inAcct(t) && t.date.startsWith(m) && (t.category || '') === id && kindOf(t) === 'expense').reduce((s, t) => s - t.amount, 0));
  const merch = {}, merchC = {};
  for (const t of exp) merch[t.merchant] = (merch[t.merchant] || 0) - t.amount;
  if (C) for (const t of txs(C.from, C.to)) if (kindOf(t) === 'expense') merchC[t.merchant] = (merchC[t.merchant] || 0) - t.amount;
  const topM = Object.entries(merch).sort((a, b) => b[1] - a[1]).slice(0, 10), maxM = topM.length ? topM[0][1] : 1;
  const biggest = [...exp].sort((a, b) => a.amount - b.amount).slice(0, 8);
  PICKS.cat = id => ({title: catName(id), filter: {...period, cat: id || 'none'}, list: exp.filter(t => (t.category || '') === id), top: focusBtn(id ? SP.cat[id].group : 'Uncategorised')});
  PICKS.merchant = m => ({title: m, filter: {...period, q: m}, list: exp.filter(t => t.merchant === m)});
  const per = RANGE.p === 'month' ? 'the month' : `${nMonths} month${nMonths > 1 ? 's' : ''}`;
  const vs = (now, before, inverse) => R.cmp ? `<span class="cmp-v">vs <span class="amt">${fmtV(before, '€')}</span></span> ${delta(now, before, inverse, '')}` : delta(now, before, inverse);
  $('#spBody').innerHTML = `<div class="stack-y">
    ${R.stale ? `<div class="muted small">Your data runs to ${fdate(SP.d.transactions[0].date)}, so ${esc(R.label.toLowerCase())} ends there.</div>` : ''}
    <div class="grid g4">
      <div class="card tile"><div class="k">Spent</div><div class="v" data-count="${T.spent}">${eur(T.spent)}</div><div class="n">${P ? vs(T.spent, P.spent, true) : per}</div></div>
      <div class="card tile"><div class="k">Income</div><div class="v" data-count="${T.income}">${eur(T.income)}</div><div class="n">${P ? vs(T.income, P.income) : per}</div></div>
      <div class="card tile"><div class="k">Saved</div><div class="v" data-count="${T.saved}" data-fmt="sgn">${sgn(T.saved)}</div><div class="n">${T.rate == null ? 'No income in this period' : `${T.rate.toFixed(0)}% of income${P && P.rate != null && R.cmp ? `, vs ${P.rate.toFixed(0)}%` : ''}`}</div></div>
      <div class="card tile"><div class="k">Spent per month</div><div class="v" data-count="${T.spent / nMonths}">${eur(T.spent / nMonths)}</div><div class="n">Average over ${per}</div></div>
    </div>
    <section class="card" data-pick="monthly"><h2>Spending per ${B.noun}</h2><p class="sub">By group. Transfers between your own accounts, saving and investing are left out.</p>
      ${buckets.length ? chartHtml({type: 'stacked', unit: '€', labels, series, pick: true, xkeys: buckets}, W) : '<div class="empty">No transactions in this period.</div>'}</section>
    <section class="card" data-pick="sankey"><h2>Where your money goes</h2><p class="sub">From what came in to what it went to, ${esc(R.label.toLowerCase())}</p><div id="sankey"></div></section>
    <div class="grid g2">
      <section class="card"><h2>Where the money goes</h2>${R.cmp ? `<p class="sub">Thin bar: ${esc(R.cmp.label)}</p>` : ''}
        ${cats.map(([id, v]) => `<button class="barrow" data-cat="${esc(id)}" data-series="${esc(id ? SP.cat[id].group : 'Uncategorised')}"><span class="bl"><b>${esc(catName(id))}</b><span class="muted small">${esc(id ? SP.cat[id].group : 'Needs a category')}</span></span>
          <span class="bb-wrap">${spark(trendOf(id), {w: 54, h: 20})}<span class="bb"><i style="width:${v / maxCat * 100}%"></i>${R.cmp ? `<i class="cmp" style="width:${(cp[id] || 0) / maxCat * 100}%"></i>` : ''}</span></span>
          <span class="bv">${eur(v)}<span class="muted small">${(v / T.spent * 100).toFixed(0)}%${C && cp[id] ? ', ' + delta(v, cp[id], true, '') : ''}</span></span></button>`).join('') || '<div class="empty">Nothing spent.</div>'}
      </section>
      <div class="stack-y">
        <section class="card" data-pick="inout"><h2>Income & spending</h2>${buckets.length ? chartHtml(inout, half) : '<div class="empty">No data.</div>'}</section>
        <section class="card"><h2>Top merchants</h2>
          ${topM.map(([m, v]) => `<button class="barrow" data-merchant="${esc(m)}"><span class="bl"><b>${esc(m)}</b></span><span class="bb"><i style="width:${v / maxM * 100}%"></i>${R.cmp ? `<i class="cmp" style="width:${Math.min(100, (merchC[m] || 0) / maxM * 100)}%"></i>` : ''}</span><span class="bv">${eur(v)}</span></button>`).join('') || '<div class="empty">Nothing yet.</div>'}
        </section>
      </div>
    </div>
    <div class="grid g2">${thisMonthCards(half)}</div>
    <section class="card" data-pick="cal"><div class="card-head"><h2>Spending per day</h2><span class="muted small">Click a day to see its payments</span></div><div id="cal"></div></section>
    <div class="grid g2">
      <section class="card"><h2>Merchants</h2><p class="sub">How often against how much. Bigger means more in total.</p><div id="bubbles"></div></section>
      <section class="card"><h2>When you spend</h2><div id="when"></div></section>
    </div>
    <div class="grid g2">${recurringCard()}
      <section class="card"><h2>Biggest expenses</h2>
        ${biggest.map(t => `<button class="list-row row-btn" data-open-tx="${t.id}" data-ctx="tx:${t.id}"><div><div style="font-weight:600">${esc(t.merchant)}</div><div class="muted small">${fdate(t.date)}, ${esc(catName(t.category))}</div></div><div class="num">${eur(-t.amount)}</div></button>`).join('') || '<div class="empty">Nothing yet.</div>'}
      </section></div>
    <div class="grid g2">${yearTable()}${tagsCard(list)}</div>
  </div>`;
  $$('[data-cat]').forEach(b => b.onclick = e => openPop(() => PICKS.cat(b.dataset.cat), e));
  $$('[data-merchant]').forEach(b => b.onclick = e => openPop(() => PICKS.merchant(b.dataset.merchant), e));
  $$('[data-rec]').forEach(b => b.onclick = e => openPop(() => PICKS.rec(b.dataset.rec), e));
  $$('[data-tagpick]').forEach(b => b.onclick = e => payPop('#' + b.dataset.tagpick, {tag: b.dataset.tagpick, ...period}, e));
  drawSankey(list, W);
  drawCalendar(from, to, W);
  drawBubbles(exp, half);
  drawWhen(exp, half);
  drawThisMonth();
  countUp($('#spBody'));
}

/* sankey: income sources, then fixed costs, day to day, saving and investing, and what was kept */
function drawSankey(list, W) {
  const box = $('#sankey'); if (!box) return;
  const inc = {}, grp = {};
  for (const t of list) {
    const k = kindOf(t);
    if (k === 'income') inc[t.category || ''] = (inc[t.category || ''] || 0) + t.amount;
    else if (k === 'expense') grp[groupOf(t)] = (grp[groupOf(t)] || 0) - t.amount;
  }
  const invested = Math.max(0, -list.filter(t => t.category === 'saving-investing').reduce((s, t) => s + t.amount, 0));
  const income = Object.values(inc).reduce((a, b) => a + b, 0), spent = Object.values(grp).reduce((a, b) => a + b, 0);
  if (income + spent < 1) { box.innerHTML = '<div class="empty">No income or spending in this period.</div>'; return; }
  const kept = income - spent - invested;
  const nodes = [], links = [];
  const srcs = Object.entries(inc).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
  const topS = srcs.slice(0, 4), restS = srcs.slice(4).reduce((s, x) => s + x[1], 0);
  topS.forEach(([id, v], i) => { nodes.push({id: 'in' + i, label: catName(id), col: 0, color: 'var(--gain)', pick: 'cat:' + id}); links.push({s: 'in' + i, t: 'income', v}); });
  if (restS > 0) { nodes.push({id: 'inR', label: 'Other income', col: 0, color: 'var(--gain)'}); links.push({s: 'inR', t: 'income', v: restS}); }
  if (kept < 0) { nodes.push({id: 'draw', label: 'From savings', col: 0, color: 'var(--ink-2)'}); links.push({s: 'draw', t: 'income', v: -kept}); }
  nodes.push({id: 'income', label: 'Money in', col: 1, color: 'var(--ink-2)'});
  const fixed = Object.entries(grp).filter(([g]) => FIXED_GROUPS.includes(g)), daily = Object.entries(grp).filter(([g]) => !FIXED_GROUPS.includes(g));
  const sum = a => a.reduce((s, x) => s + x[1], 0);
  if (sum(fixed) > 0) { nodes.push({id: 'fixed', label: 'Fixed costs', col: 2, color: col(1)}); links.push({s: 'income', t: 'fixed', v: sum(fixed)}); }
  if (sum(daily) > 0) { nodes.push({id: 'daily', label: 'Day to day', col: 2, color: col(0)}); links.push({s: 'income', t: 'daily', v: sum(daily)}); }
  if (invested > 0) { nodes.push({id: 'inv', label: 'Saving and investing', col: 2, color: col(2), pick: 'cat:saving-investing'}); links.push({s: 'income', t: 'inv', v: invested}); }
  if (kept > 0) { nodes.push({id: 'kept', label: 'Kept', col: 2, color: col(3)}); links.push({s: 'income', t: 'kept', v: kept}); }
  const order = [...fixed.sort((a, b) => b[1] - a[1]), ...daily.sort((a, b) => b[1] - a[1])];
  order.forEach(([g, v], i) => { const isF = FIXED_GROUPS.includes(g); nodes.push({id: 'g' + i, label: g, col: 3, color: isF ? col(1) : col(0), pick: 'group:' + g}); links.push({s: isF ? 'fixed' : 'daily', t: 'g' + i, v}); });
  box.innerHTML = sankey(nodes, links, W, Math.max(300, Math.min(520, order.length * 34 + 40)));
  const R = spRange();
  box.onclick = e => {
    const el = e.target.closest('[data-sk]'); if (!el) return;
    const [kind, v] = el.dataset.sk.split(/:(.*)/s);
    payPop(kind === 'group' ? v : catName(v), kind === 'group' ? {group: v, from: R.from, to: R.to} : {category: v, from: R.from, to: R.to}, e);
  };
}

/* calendar heatmap: one square per day */
function drawCalendar(from, to, W) {
  const box = $('#cal'); if (!box) return;
  const end = new Date(Math.min(Date.now(), Date.parse((to.startsWith('9999') ? today() : to) + 'T12:00'), Date.parse((SP.d.transactions[0] || {date: today()}).date + 'T12:00') + 864e5 * 0));
  const start = new Date(Math.max(Date.parse((from === '0000-01-01' ? '1900-01-01' : from) + 'T12:00'), end - 370 * 864e5));
  const byDay = {};
  for (const t of SP.rows) if (inAcct(t) && kindOf(t) === 'expense' && t.date >= isoD(start) && t.date <= isoD(end)) byDay[t.date] = (byDay[t.date] || 0) - t.amount;
  const vals = Object.values(byDay).sort((a, b) => a - b), cap = vals.length ? vals[Math.floor(vals.length * 0.95)] || vals[vals.length - 1] : 1;
  const first = new Date(start); first.setDate(first.getDate() - ((first.getDay() + 6) % 7));
  const weeks = Math.ceil((end - first) / (7 * 864e5)) + 1, cell = Math.max(9, Math.min(15, Math.floor((W - 40) / weeks) - 2)), gap = 2;
  let svg = '', lastMonth = -1;
  for (let w = 0; w < weeks; w++) for (let d = 0; d < 7; d++) {
    const day = new Date(first.getTime() + (w * 7 + d) * 864e5);
    if (day < start || day > end) continue;
    const iso = isoD(day), v = byDay[iso] || 0, x = 30 + w * (cell + gap), y = 18 + d * (cell + gap);
    if (day.getDate() <= 7 && d === 0 && day.getMonth() !== lastMonth) { lastMonth = day.getMonth(); svg += `<text class="c-ax" x="${x}" y="11">${MON[day.getMonth()]}</text>`; }
    svg += `<rect class="cal-d" x="${x}" y="${y}" width="${cell}" height="${cell}" rx="2" data-day="${iso}" data-x="${iso.slice(0, 7)}" style="fill:${v ? `color-mix(in srgb, var(--s1) ${Math.round(15 + 70 * Math.min(1, v / cap))}%, var(--surface-2))` : 'var(--surface-2)'}" data-tip="${esc(fdate(iso) + ': ' + (v ? fmtV(v, '€') : 'nothing spent'))}"/>`;
  }
  const H = 18 + 7 * (cell + gap) + 4;
  box.innerHTML = `<svg viewBox="0 0 ${30 + weeks * (cell + gap)} ${H}" class="c-svg cal" style="max-width:${30 + weeks * (cell + gap)}px">${['Mon', '', 'Wed', '', 'Fri', '', ''].map((l, d) => l ? `<text class="c-ax" x="0" y="${18 + d * (cell + gap) + cell - 2}">${l}</text>` : '').join('')}${svg}</svg>
    <div class="cal-legend muted small">Less ${[0, 25, 50, 75, 100].map(p => `<i style="background:${p ? `color-mix(in srgb, var(--s1) ${Math.round(15 + 70 * p / 100)}%, var(--surface-2))` : 'var(--surface-2)'}"></i>`).join('')} More</div>`;
  box.onclick = e => { const d = e.target.closest('[data-day]'); if (d) payPop(fdate(d.dataset.day), {day: d.dataset.day, kind: 'expense'}, e); };
}

/* this month against the usual month */
function thisMonthCards() {
  return `<section class="card"><div class="card-head"><h2>This month against your average</h2><span class="muted small" id="tmWhen"></span></div><div id="bullets"></div></section>
    <section class="card"><h2>Spending through the month</h2><div id="cum"></div></section>`;
}
function drawThisMonth() {
  const rows = SP.rows.filter(inAcct);
  const lastDate = rows.length ? rows.reduce((m, t) => t.date > m ? t.date : m, '') : today();
  const ref = new Date(Math.min(Date.now(), Date.parse(lastDate + 'T12:00'))), m0 = isoD(ref).slice(0, 7), day = ref.getDate();
  const prevMonths = [...new Set(rows.map(t => t.date.slice(0, 7)))].filter(m => m < m0).sort().slice(-6);
  const exp = rows.filter(t => kindOf(t) === 'expense');
  if ($('#tmWhen')) $('#tmWhen').textContent = `${fdate(m0)}, day ${day}`;
  // bullets: per group, this month so far against the average for the same days
  const g = {}, avg = {};
  for (const t of exp) {
    const k = groupOf(t), m = t.date.slice(0, 7), d = +t.date.slice(8);
    if (m === m0) g[k] = (g[k] || 0) - t.amount;
    else if (prevMonths.includes(m) && d <= day) avg[k] = (avg[k] || 0) - t.amount / prevMonths.length;
  }
  const keys = [...new Set([...Object.keys(g), ...Object.keys(avg)])].filter(k => (g[k] || 0) + (avg[k] || 0) > 5).sort((a, b) => Math.max(g[b] || 0, avg[b] || 0) - Math.max(g[a] || 0, avg[a] || 0)).slice(0, 8);
  const mx = Math.max(1, ...keys.map(k => Math.max(g[k] || 0, avg[k] || 0)));
  if ($('#bullets')) $('#bullets').innerHTML = keys.length ? `<div class="bullets">${keys.map(k => {
    const v = g[k] || 0, a = avg[k] || 0, d = v - a;
    return `<button type="button" class="bullet" data-bullet="${esc(k)}"><span class="bl-name">${esc(k)}</span><span class="bl-track"><i style="width:${v / mx * 100}%"></i><b style="left:${a / mx * 100}%" title="Average"></b></span>
      <span class="bl-v"><span class="amt">${fmtV(v, '€')}</span><span class="small ${Math.abs(d) < 5 ? 'muted' : d > 0 ? 'neg' : 'pos'}">${Math.abs(d) < 5 ? 'as usual' : (d > 0 ? '+' : '−') + fmtV(Math.abs(d), '€')}</span></span></button>`;
  }).join('')}</div><div class="muted small" style="margin-top:8px">The tick is your average for the first ${day} days of a month.</div>` : '<div class="empty">Not enough data yet.</div>';
  $$('[data-bullet]').forEach(b => b.onclick = e => payPop(`${b.dataset.bullet}, ${fdate(m0)}`, {group: b.dataset.bullet, month: m0, kind: 'expense'}, e));
  // cumulative lines: this month, last month, and the average month
  const cum = m => { const by = Array(32).fill(0); for (const t of exp) if (t.date.startsWith(m)) by[+t.date.slice(8)] -= t.amount; let s = 0; return by.map((v, d) => d ? (s += v) : 0); };
  const dim = m => new Date(+m.slice(0, 4), +m.slice(5, 7), 0).getDate();
  const cur = cum(m0), last = prevMonths.length ? cum(prevMonths[prevMonths.length - 1]) : null;
  const av = Array(32).fill(0); prevMonths.forEach(m => { const c = cum(m); for (let d = 1; d <= 31; d++) av[d] += (d <= dim(m) ? c[d] : c[dim(m)]) / prevMonths.length; });
  const series = [{name: 'This month', pts: Array.from({length: day}, (_, i) => [i + 1, cur[i + 1]]), color: 'var(--s1)', width: 2.5}];
  if (last) series.push({name: fdate(prevMonths[prevMonths.length - 1]), pts: Array.from({length: dim(prevMonths[prevMonths.length - 1])}, (_, i) => [i + 1, last[i + 1]]), color: 'var(--muted)'});
  if (prevMonths.length > 1) series.push({name: 'Average month', pts: Array.from({length: 31}, (_, i) => [i + 1, av[i + 1]]), color: 'var(--line-strong)', dash: true});
  if ($('#cum')) timeChart($('#cum'), {series, xfmt: 'day', xticks: [1, 5, 10, 15, 20, 25, 31], xname: d => `Day ${d}`, height: 220, zero: true, label: 'Spending through the month'});
}

/* bubbles: merchants by how often and how much */
function drawBubbles(exp, W) {
  const box = $('#bubbles'); if (!box) return;
  const m = {};
  for (const t of exp) { const x = m[t.merchant] = m[t.merchant] || {n: 0, v: 0}; x.n++; x.v -= t.amount; }
  const pts = Object.entries(m).filter(([, x]) => x.v > 5).sort((a, b) => b[1].v - a[1].v).slice(0, 40)
    .map(([label, x]) => ({label, x: x.n, y: x.v / x.n, r: x.v, open: label, tip: `${label}: ${x.n} payment${x.n === 1 ? '' : 's'}, average ${fmtV(x.v / x.n, '€')}, ${fmtV(x.v, '€')} in total`}));
  box.innerHTML = bubbles(pts, W, 300);
  box.onclick = e => { const c = e.target.closest('[data-merchant-pick]'); if (c) payPop(c.dataset.merchantPick, {merchant: c.dataset.merchantPick, from: spRange().from, to: spRange().to, kind: 'expense'}, e); };
}

/* when: weekday by hour when the bank says the time, otherwise by weekday */
function drawWhen(exp, W) {
  const box = $('#when'); if (!box) return;
  const timed = exp.filter(t => t.hour != null);
  const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const wd = t => (new Date(t.date + 'T12:00').getDay() + 6) % 7;
  if (timed.length >= 30 && timed.length / exp.length > 0.25) {
    const hours = [6, 8, 10, 12, 14, 16, 18, 20, 22];
    const slot = h => hours.reduce((b, x) => h >= x ? x : b, hours[0]);
    const grid = {};
    for (const t of timed) { const k = wd(t) + '|' + slot(t.hour); grid[k] = (grid[k] || 0) - t.amount; }
    box.innerHTML = `<p class="sub">Card payments by day and time of day</p>` + heatTable(DAYS, hours.map(h => `${h}:00`), (r, c) => grid[r + '|' + hours[c]] || null, {fmt: v => fmtV(v, '€', true), pick: true});
    box.onclick = e => { const c = e.target.closest('[data-heat]'); if (!c) return; const [r, k] = c.dataset.heat.split('|').map(Number);
      const R = spRange(); openPop(() => ({title: `${DAYS[r]}s around ${hours[k]}:00`, list: timed.filter(t => wd(t) === r && slot(t.hour) === hours[k])}), e); };
  } else {
    const daily = ['Food and drink', 'Shopping', 'Leisure', 'Transport', 'Health and care'];
    const list = exp.filter(t => daily.includes(groupOf(t)));
    const v = [0, 0, 0, 0, 0, 0, 0];
    for (const t of list) v[wd(t)] -= t.amount;
    const weeks = Math.max(1, new Set(list.map(t => isoD(new Date(Date.parse(t.date) - wd(t) * 864e5)))).size);
    PICKS.weekday = i => ({title: `${['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][i]}s, day to day`, list: list.filter(t => wd(t) === i)});
    box.innerHTML = `<p class="sub">Average per week on food, shopping, leisure, transport and care</p><div data-pick="weekday">${chartHtml({type: 'bar', unit: '€', pick: true, labels: DAYS, series: [{name: 'Per week', values: v.map(x => x / weeks)}]}, W)}</div>`;
  }
}
function recurringCard() {
  const subs = detectSubs().filter(s => s.status !== 'not' && s.status !== 'cancelled');
  PICKS.rec = key => { const s = subs.find(x => x.key === key); return s ? {title: s.name, filter: {q: s.name}, list: s.list} : null; };
  const total = subs.reduce((s, r) => s + r.yearly, 0);
  return `<section class="card"><div class="card-head"><div><h2>Recurring payments</h2><p class="sub">About ${eur(total)} a year</p></div><button type="button" class="btn ghost" id="toSubs">All</button></div>
    ${subs.slice(0, 8).map(r => `<button class="list-row row-btn" data-rec="${esc(r.key)}"><div><div style="font-weight:600">${esc(r.name)}</div><div class="muted small">${esc(r.freqLabel)}, next ${fdate(r.next)}</div></div><div class="num">${eur(r.last, r.last < 100 ? 2 : 0)}<div class="small muted">${eur(r.yearly)} a year</div></div></button>`).join('') || '<div class="empty">Needs a few months of data.</div>'}</section>`;
}
document.addEventListener('click', e => { if (e.target.id === 'toSubs') { SP.tab = 'subscriptions'; spendingPage(); } });
function yearTable() {
  const years = [...new Set(SP.rows.map(t => t.date.slice(0, 4)))].sort();
  if (!years.length) return '';
  const rows = {}, tot = {}, inc = {};
  for (const t of SP.rows) {
    if (!inAcct(t)) continue;
    const y = t.date.slice(0, 4), k = kindOf(t);
    if (k === 'income') inc[y] = (inc[y] || 0) + t.amount;
    if (k !== 'expense') continue;
    const g = groupOf(t);
    rows[g] = rows[g] || {}; rows[g][y] = (rows[g][y] || 0) - t.amount; tot[y] = (tot[y] || 0) - t.amount;
  }
  const ys = years.slice(-5), cy = String(new Date().getFullYear());
  return `<section class="card"><h2>Year over year</h2><p class="sub">Spending per group${ys.includes(cy) ? `; ${cy} so far` : ''}</p><div class="table-wrap"><table>
    <thead><tr><th>Group</th>${ys.map(y => `<th class="num">${y}</th>`).join('')}</tr></thead>
    <tbody>${Object.keys(rows).sort((a, b) => (rows[b][ys[ys.length - 1]] || 0) - (rows[a][ys[ys.length - 1]] || 0)).map(g => `<tr><td>${esc(g)}</td>${ys.map(y => `<td class="num">${rows[g][y] ? eur(rows[g][y]) : ''}</td>`).join('')}</tr>`).join('')}</tbody>
    <tfoot><tr><td>Spent</td>${ys.map(y => `<td class="num">${eur(tot[y] || 0)}</td>`).join('')}</tr>
      <tr><td>Income</td>${ys.map(y => `<td class="num">${eur(inc[y] || 0)}</td>`).join('')}</tr>
      <tr><td>Saved</td>${ys.map(y => `<td class="num">${sgn((inc[y] || 0) - (tot[y] || 0))}</td>`).join('')}</tr></tfoot></table></div></section>`;
}
function tagsCard(list) {
  const t = {};
  for (const x of list) for (const tag of x.tags || []) { const o = t[tag] = t[tag] || {n: 0, v: 0}; o.n++; o.v += x.amount; }
  const rows = Object.entries(t).sort((a, b) => Math.abs(b[1].v) - Math.abs(a[1].v));
  return `<section class="card"><h2>Tags</h2>${rows.length ? `<p class="sub">From the #tags in your messages about payments</p>${rows.map(([k, o]) => `<button class="list-row row-btn" data-tagpick="${esc(k)}"><div><div style="font-weight:600">#${esc(k)}</div><div class="muted small">${o.n} payment${o.n === 1 ? '' : 's'}</div></div><div class="num">${sgn(o.v)}</div></button>`).join('')}`
    : '<p class="sub" style="margin:0">Write a #tag when you tell Claude about a payment (for example #wedding or #holiday-spain) and its total shows up here.</p>'}</section>`;
}

/* ---------- transactions ---------- */
function catOptions(sel, withNone) {
  const groups = {};
  for (const c of SP.d.categories) (groups[c.group] = groups[c.group] || []).push(c);
  return (withNone ? `<option value="" ${!sel ? 'selected' : ''}>Choose a category</option>` : '') +
    Object.entries(groups).map(([g, cs]) => `<optgroup label="${esc(g)}">${cs.map(c => `<option value="${c.id}" ${c.id === sel ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}</optgroup>`).join('');
}
function countryOptions(sel, codes) {
  const all = codes || Object.keys(GEO.countries);
  return all.map(c => [c, ctyName(c)]).sort((a, b) => a[1].localeCompare(b[1])).map(([c, n]) => `<option value="${c}" ${c === sel ? 'selected' : ''}>${esc(n)}</option>`).join('');
}
function linkNote(t) {
  // a payment and the money that came back for it, booked together
  if (!t.linked_to) return '';
  if (t.linked_to === t.id) {
    const back = SP.d.transactions.filter(o => o.linked_to === t.id && o.id !== t.id);
    if (!back.length) return '';
    const sum = back.reduce((s, o) => s + o.amount, 0);
    return `<div class="meta link">↔ ${eur(sum, 2)} paid back, your share ${eur(Math.abs(t.amount + sum), 2)}</div>`;
  }
  const parent = SP.d.transactions.find(o => o.id === t.linked_to);
  return `<div class="meta link">↔ paid back for ${esc(parent ? parent.merchant : 'another payment')}${parent ? ', ' + fdate(parent.date) : ''}</div>`;
}
function periodLabel(from, to) {
  if (to.startsWith('9999')) return from === '0000-01-01' ? 'All time' : `Since ${fdate(from)}`;
  if (from === to) return fdate(from);
  if (from.endsWith('-01-01') && to === from.slice(0, 4) + '-12-31') return from.slice(0, 4);
  if (from.endsWith('-01') && to.slice(0, 7) === from.slice(0, 7) && to.endsWith('-31')) return fdate(from.slice(0, 7));
  return `${fdate(from)} to ${fdate(to)}`;
}
function noteChip(t) {
  const mine = (t.thread || []).filter(m => m.role === 'you');
  const last = mine.length ? mine[mine.length - 1].text : '';
  return `<button class="note-btn ${last ? 'has' : ''}" data-open-tx="${t.id}" title="${last ? esc(last) : 'Ask Claude about this'}">${last ? '✎ ' + esc(last) : '✎'}</button>`;
}
/* filters that take several values: a button that opens a list of checkboxes */
const asList = v => Array.isArray(v) ? v : !v || v === 'all' ? [] : [v];
const catOpts = () => [['none', 'Uncategorised'], ...[...SP.d.categories].sort((a, b) => a.group.localeCompare(b.group) || a.name.localeCompare(b.name)).map(c => [c.id, `${c.name}`, c.group])];
function mselBtn(id, label, opts, sel) {
  const one = sel.length === 1 && opts.find(o => o[0] === sel[0]);
  const text = !sel.length ? label : one ? one[1] : `${sel.length} ${label.replace(/^All /, '')}`;
  return `<button type="button" class="msel ${sel.length ? 'on' : ''}" id="${id}" aria-haspopup="true">${esc(text)}<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg></button>`;
}
function wireMsel(id, opts, key) {
  const b = $('#' + id); if (!b) return;
  b.onclick = e => {
    e.stopPropagation();
    let group = '';
    const menu = openMenu(b, `<div class="menu-sec msel-list">${opts.map(([v, l, g]) => (g && g !== group ? `<div class="menu-h">${esc(group = g)}</div>` : '') +
      `<label class="menu-row msel-row"><input type="checkbox" value="${esc(v)}" ${asList(SP.tx[key]).includes(v) ? 'checked' : ''}><span>${esc(l)}</span></label>`).join('')}</div>
      <div class="menu-sec msel-foot"><button type="button" class="linkish small" data-mclear>Clear</button><button type="button" class="btn" data-mdone>Done</button></div>`, 'msel-menu');
    const apply = () => { SP.tx[key] = $$('input:checked', menu).map(x => x.value); SP.tx.limit = 150; spTransactions(); };
    menu.onchange = apply;
    $('[data-mclear]', menu).onclick = () => { $$('input', menu).forEach(x => x.checked = false); apply(); };
    $('[data-mdone]', menu).onclick = closeMenus;
  };
}
function spTransactions() {
  const f = SP.tx;
  const mine = SP.d.transactions.filter(inAcct);
  const months = [...new Set(mine.map(t => t.date.slice(0, 7)))].sort().reverse();
  const ctys = [...new Set(mine.map(t => t.country).filter(Boolean))];
  const tags = [...new Set(mine.flatMap(t => t.tags || []))].sort();
  let list = mine;
  if (f.from) list = list.filter(t => t.date >= f.from && t.date <= f.to);
  if (f.month !== 'all') list = list.filter(t => t.date.startsWith(f.month));
  const cats = asList(f.cat), ctySel = asList(f.country), tagSel = asList(f.tag);
  if (cats.length) list = list.filter(t => cats.some(c => c === 'none' ? needsReview(t) : t.category === c || (t.splits || []).some(p => p.category === c)));
  if (f.group && f.group !== 'all') list = list.filter(t => groupOf(t) === f.group);
  if (ctySel.length) list = list.filter(t => ctySel.includes(t.country || 'none'));
  if (tagSel.length) list = list.filter(t => tagSel.some(x => (t.tags || []).includes(x)));
  if (f.status === 'excluded') list = list.filter(t => t.excluded); else if (f.status !== 'all') list = list.filter(t => !!t.checked === (f.status === 'checked'));
  if (f.q) { const q = f.q.toLowerCase(); list = list.filter(t => (t.merchant + ' ' + t.description + ' ' + (t.note || '') + ' ' + Math.abs(t.amount).toFixed(2)).toLowerCase().includes(q)); }
  const sum = list.filter(t => !t.excluded).reduce((s, t) => s + t.amount, 0);
  const open = list.filter(t => !t.checked && t.category);
  $('#spBody').innerHTML = `<section class="card">
    <div class="controls">
      <input type="search" id="txq" placeholder="Search merchant, description, note or amount" value="${esc(f.q)}" aria-label="Search">
      ${mselBtn('txcat', 'All categories', catOpts(), cats)}
      <select id="txmonth" aria-label="Month"><option value="all">All months</option>${months.map(m => `<option value="${m}" ${f.month === m ? 'selected' : ''}>${mLabel(m)}</option>`).join('')}</select>
      ${mselBtn('txcty', 'All countries', [...ctys.map(c => [c, ctyName(c)]).sort((a, b) => a[1].localeCompare(b[1])), ['none', 'Not known']], ctySel)}
      ${tags.length ? mselBtn('txtag', 'All tags', tags.map(t => [t, '#' + t]), tagSel) : ''}
      <select id="txstat" aria-label="Checked"><option value="all">Checked or not</option><option value="open" ${f.status === 'open' ? 'selected' : ''}>Not checked</option><option value="checked" ${f.status === 'checked' ? 'selected' : ''}>Checked</option><option value="excluded" ${f.status === 'excluded' ? 'selected' : ''}>Left out of totals</option></select>
      ${f.from ? `<button class="btn ghost" id="txclear">${esc(periodLabel(f.from, f.to))} ×</button>` : ''}
      ${f.group && f.group !== 'all' ? `<button class="btn ghost" id="txgroup">${esc(f.group)} ×</button>` : ''}
    </div>
    <div class="controls" style="justify-content:space-between"><span class="muted small">${list.length} transactions, net ${sgn(sum, 2)}${open.length ? ` · <button class="linkish" id="txcheckall">Mark ${open.length === list.length ? 'all' : 'the ' + open.length} as checked</button>` : ''}</span>
      <label class="check"><input type="checkbox" id="txlearn" ${SP.learn ? 'checked' : ''}> When I change a category, do the same for this merchant</label></div>
    <div class="table-wrap" data-cap="tall" id="txbox"><table class="txt">
      <thead><tr><th class="tick-col"><span class="sr">Checked</span></th><th>Date</th><th>Transaction</th><th>Category</th><th class="num">Amount</th></tr></thead>
      <tbody>${list.slice(0, f.limit).map(t => `<tr class="${t.checked ? 'is-checked' : ''} ${t.excluded ? 'is-excluded' : ''}" data-ctx="tx:${t.id}">
        <td class="tick-col"><button class="tick ${t.checked ? 'on' : ''}" data-tick="${t.id}" ${t.category ? '' : 'disabled'} title="${t.checked ? 'Checked. Click to undo' : t.category ? 'Mark as checked' : 'Choose a category first'}" aria-pressed="${!!t.checked}">${TICK}</button></td>
        <td class="muted small" style="white-space:nowrap">${fdate(t.date)}</td>
        <td><button class="nm linkish" data-open-tx="${t.id}">${esc(t.merchant)}</button>${t.excluded ? '<span class="tag">left out</span>' : ''}${t.splits ? '<span class="tag">split</span>' : ''}${(t.tags || []).map(x => `<span class="tag">#${esc(x)}</span>`).join('')}
          <div class="meta desc">${esc(t.description)}</div><div class="meta">${where(t)}</div>
          ${SP.d.status.note_tx === t.id ? '<div class="meta working-note"><span class="spinner"></span> Claude is answering</div>' : ''}${linkNote(t)}</td>
        <td>${t.splits ? `<div class="small">${t.splits.map(p => `${esc(catName(p.category))} ${eur(Math.abs(p.amount), 2)}`).join('<br>')}</div>` : `<select data-tx="${t.id}" class="${t.category ? '' : 'unset'}">${catOptions(t.category, true)}</select>`}<div class="meta src-line"><span>${t.category_source ? SRC[t.category_source] || '' : ''}</span>${noteChip(t)}</div></td>
        <td class="num">${amt(t)}</td></tr>`).join('') || '<tr><td colspan="5" class="empty">No transactions match.</td></tr>'}</tbody></table></div>
    ${list.length > f.limit ? `<button class="btn" id="txmore" style="margin-top:12px">Show more (${list.length - f.limit} left)</button>` : ''}
  </section>`;
  $('#txq').oninput = e => { f.q = e.target.value; f.limit = 150; const pos = e.target.selectionStart; spTransactions(); $('#txq').focus(); $('#txq').setSelectionRange(pos, pos); };
  wireMsel('txcat', catOpts(), 'cat');
  $('#txmonth').onchange = e => { f.month = e.target.value; f.limit = 150; spTransactions(); };
  wireMsel('txcty', [...ctys.map(c => [c, ctyName(c)]).sort((a, b) => a[1].localeCompare(b[1])), ['none', 'Not known']], 'country');
  wireMsel('txtag', tags.map(t => [t, '#' + t]), 'tag');
  $('#txstat').onchange = e => { f.status = e.target.value; f.limit = 150; spTransactions(); };
  if ($('#txclear')) $('#txclear').onclick = () => { f.from = f.to = null; spTransactions(); };
  if ($('#txgroup')) $('#txgroup').onclick = () => { f.group = 'all'; spTransactions(); };
  $('#txlearn').onchange = e => { SP.learn = e.target.checked; store.set('sp.learn', SP.learn); };
  if ($('#txmore')) $('#txmore').onclick = () => { f.limit += 300; spTransactions(); };
  // scrolling to the end of the list loads the next ones
  $('#txbox').addEventListener('scroll', e => { const b = e.target; if (list.length > f.limit && b.scrollTop + b.clientHeight > b.scrollHeight - 200) { f.limit += 300; spTransactions(); } }, {passive: true});
  if ($('#txcheckall')) $('#txcheckall').onclick = () => setChecked(open.map(t => t.id), true);
  $$('[data-tx]').forEach(s => s.onchange = () => setCat([s.dataset.tx], s.value || null, SP.learn));
  $$('[data-tick]').forEach(b => b.onclick = () => setChecked([b.dataset.tick], !txById(b.dataset.tick).checked));
}
async function setChecked(ids, on, quiet) {
  // show it right away, save in the background
  for (const id of ids) { const t = txById(id); if (t && (t.category || !on)) on ? t.checked = true : delete t.checked; }
  if (!quiet && view === 'spending') { const y = scrollY; spendingPage(); scrollTo(0, y); }
  try { await post('/api/spending/edit', {action: 'check', ids, checked: on}); if (ids.length > 1) toast(`${ids.length} marked as checked`); }
  catch (e) { toast(e.message); await loadSpending(); spendingPage(); }
}
async function setCat(ids, category, learn) {
  try {
    await post('/api/spending/categorize', {ids, category, learn});
    const y = scrollY; await loadSpending(); if (view === 'spending') spendingPage(); scrollTo(0, y);
    toast(learn && category ? 'Saved, and remembered for this merchant' : 'Saved');
  } catch (e) { toast(e.message); }
}
async function spEdit(body, msg) {
  try { await post('/api/spending/edit', body); toast(msg); await loadSpending(); if (view === 'spending') spendingPage(); if (SP.sheet) drawSheet(); } catch (e) { toast(e.message); }
}

/* ---------- one transaction: details, a conversation with Claude, splitting ---------- */
function txSheet(id, focus) {
  const dlg = $('#dlg'), f = $('#dlgForm');
  dlg.classList.add('wide');
  dlg.addEventListener('close', () => { dlg.classList.remove('wide'); SP.sheet = null; SP.splitting = false; }, {once: true});
  SP.sheet = id; SP.splitting = focus === 'split';
  drawSheet();
  if (!dlg.open) dlg.showModal();
  setTimeout(() => { const el = focus === 'category' ? $('#shCat') : $('#shMsg'); if (el && !SP.d.status.note_tx) el.focus(); });
  f.onsubmit = async e => {
    e.preventDefault();
    if (SP.splitting) return;
    const q = $('#shMsg'), text = q.value.trim();
    if (!text || SP.d.status.note_tx === id) return;
    const t = txById(id);
    (t.thread = t.thread || []).push({role: 'you', text});
    q.value = '';
    SP.d.status.note_tx = id; drawSheet();
    try { await post('/api/spending/edit', {action: 'note', id, text}); } catch (err) { toast(err.message); }
    waitForReply(id);
  };
}
function drawSheet() {
  const id = SP.sheet, t = id && txById(id);
  if (!t) return;
  const thinking = SP.d.status.note_tx === id, thread = t.thread || [];
  const f = $('#dlgForm'), keep = $('#shMsg') ? $('#shMsg').value : '';
  f.innerHTML = `<div class="sh-head"><div style="min-width:0"><h3>${esc(t.merchant)}</h3>
      <div class="muted small">${fdate(t.date)} · ${esc(acctName(t.account))}${t.country ? ' · ' + esc(ctyName(t.country)) : ''}</div></div>
      <div class="sh-amt num">${amt(t)}</div></div>
    <div class="sh-desc">${esc(t.description)}</div>
    ${SP.splitting ? splitEditor(t) : `<div class="sh-fields">
      ${t.splits ? `<div class="sh-split small">${t.splits.map(p => `${esc(catName(p.category))} <b class="amt">${eur(Math.abs(p.amount), 2)}</b>`).join(' · ')}</div>` : `<select id="shCat" class="${t.category ? '' : 'unset'}" aria-label="Category">${catOptions(t.category, true)}</select>`}
      <select id="shCty" aria-label="Country"><option value="">Country not known</option>${countryOptions(t.country)}</select>
      <button type="button" class="tick-pill ${t.checked ? 'on' : ''}" id="shTick" ${t.category ? '' : 'disabled'}>${TICK}${t.checked ? 'Checked' : 'Mark as checked'}</button>
    </div>
    <div class="sh-more"><button type="button" class="linkish small" id="shSplit">${t.splits ? 'Change the split' : 'Split over categories'}</button>
      ${t.excluded_by === 'merchant' ? '' : `<button type="button" class="linkish small" id="shExcl">${t.excluded ? 'Count it again' : 'Leave out of totals'}</button>`}
      <button type="button" class="linkish small" id="shExclM">${(SP.d.excluded_keys || []).includes(t.key) ? `Count ${esc(t.merchant)} again` : `Always leave out ${esc(t.merchant)}`}</button>
      ${(t.tags || []).map(x => `<span class="tag">#${esc(x)} <button type="button" class="x-btn" data-untag="${esc(x)}" aria-label="Remove tag">×</button></span>`).join('')}</div>`}
    <div class="sh-link">${linkNote(t)}</div>
    <div class="thread" id="shThread">${thread.length || thinking ? thread.map(m => `<div class="bubble ${m.role === 'you' ? 'you' : 'claude'}">${esc(m.text)}</div>`).join('') +
      (thinking ? '<div class="bubble claude typing" aria-label="Claude is answering"><i></i><i></i><i></i></div>' : '')
      : '<div class="thread-empty">Tell Claude what this was. For example: shared this dinner, a friend paid me back half. Add #tags to group payments.</div>'}</div>
    <div class="reply"><textarea id="shMsg" rows="1" placeholder="${thread.length ? 'Reply to Claude' : 'Message Claude about this payment'}" aria-label="Message">${esc(keep)}</textarea>
      <button class="send" aria-label="Send" ${thinking ? 'disabled' : ''}>${ICON.up}</button></div>
    <div class="dialog-actions">${thread.length ? '<button type="button" class="btn ghost" id="shClear" style="margin-right:auto">Clear conversation</button>' : ''}<button type="button" class="btn" id="shDone">Done</button></div>`;
  const box = $('#shThread'); box.scrollTop = box.scrollHeight;
  const q = $('#shMsg');
  const fit = () => { q.style.height = 'auto'; q.style.height = Math.min(q.scrollHeight, 140) + 'px'; };
  q.oninput = fit;
  q.onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); SP.splitting = false; $('#dlgForm').requestSubmit(); } };
  $('#shDone').onclick = () => $('#dlg').close();
  if (SP.splitting) return wireSplit(t);
  if ($('#shCat')) $('#shCat').onchange = async e => { await setCat([id], e.target.value || null, SP.learn); drawSheet(); };
  $('#shCty').onchange = async e => {
    try { await post('/api/spending/edit', {action: 'country', id, country: e.target.value}); await loadSpending(); if (view === 'spending') spendingPage(); drawSheet(); } catch (err) { toast(err.message); }
  };
  $('#shTick').onclick = async () => { await setChecked([id], !t.checked); drawSheet(); };
  $('#shSplit').onclick = () => { SP.splitting = true; drawSheet(); };
  if ($('#shExcl')) $('#shExcl').onclick = () => spEdit({action: 'exclude', ids: [id], excluded: !t.excluded}, t.excluded ? 'Counted again' : 'Left out of totals');
  $('#shExclM').onclick = () => { const on = !(SP.d.excluded_keys || []).includes(t.key);
    spEdit({action: 'exclude-merchant', key: t.key, excluded: on}, on ? `Every payment from ${t.merchant} is left out, also future ones` : `${t.merchant} counts again`); };
  $$('[data-untag]').forEach(b => b.onclick = () => spEdit({action: 'tags', id, tags: (t.tags || []).filter(x => x !== b.dataset.untag)}, 'Tag removed'));
  if ($('#shClear')) $('#shClear').onclick = e => {
    if (!e.target.dataset.armed) { e.target.dataset.armed = 1; e.target.textContent = 'Click again to clear'; return; }
    post('/api/spending/edit', {action: 'note-clear', id}).then(async () => { await loadSpending(); if (view === 'spending') spendingPage(); drawSheet(); }).catch(err => toast(err.message));
  };
}
function splitEditor(t) {
  const parts = SP.splitParts && SP.splitParts.id === t.id ? SP.splitParts.parts : (t.splits || [{category: t.category || '', amount: t.amount}, {category: '', amount: 0}]).map(p => ({...p}));
  SP.splitParts = {id: t.id, parts};
  const rest = +(t.amount - parts.reduce((s, p) => s + (+p.amount || 0), 0)).toFixed(2);
  return `<div class="split">${parts.map((p, i) => `<div class="split-row"><select data-sp-cat="${i}" aria-label="Category">${catOptions(p.category, true)}</select>
      <input type="number" step="0.01" data-sp-amt="${i}" value="${Math.abs(p.amount) || ''}" aria-label="Amount"><button type="button" class="x-btn" data-sp-rm="${i}" aria-label="Remove">×</button></div>`).join('')}
    <div class="split-foot"><button type="button" class="linkish small" id="spAdd">Add a part</button><span class="small ${Math.abs(rest) > 0.004 ? 'neg' : 'muted'}">${Math.abs(rest) > 0.004 ? `${eur(Math.abs(rest), 2)} left to divide` : 'Adds up'}</span></div>
    <div class="split-act">${t.splits ? '<button type="button" class="btn ghost" id="spUndo">Remove the split</button>' : ''}<button type="button" class="btn ghost" id="spCancel">Cancel</button><button type="button" class="btn primary" id="spSave" ${Math.abs(rest) > 0.004 ? 'disabled' : ''}>Save split</button></div></div>`;
}
function wireSplit(t) {
  const P = SP.splitParts.parts, sign = t.amount < 0 ? -1 : 1;
  const redraw = () => { const y = $('#dlgForm').scrollTop; drawSheet(); $('#dlgForm').scrollTop = y; };
  $$('[data-sp-cat]').forEach(s => s.onchange = () => { P[+s.dataset.spCat].category = s.value; });
  $$('[data-sp-amt]').forEach(s => s.onchange = () => { P[+s.dataset.spAmt].amount = sign * Math.abs(+s.value || 0); redraw(); });
  $$('[data-sp-rm]').forEach(b => b.onclick = () => { P.splice(+b.dataset.spRm, 1); redraw(); });
  $('#spAdd').onclick = () => { const rest = t.amount - P.reduce((s, p) => s + (+p.amount || 0), 0); P.push({category: '', amount: +rest.toFixed(2)}); redraw(); };
  $('#spCancel').onclick = () => { SP.splitting = false; SP.splitParts = null; drawSheet(); };
  if ($('#spUndo')) $('#spUndo').onclick = async () => { SP.splitting = false; SP.splitParts = null; await spEdit({action: 'split', id: t.id, parts: []}, 'Split removed'); };
  $('#spSave').onclick = async () => {
    if (P.some(p => !p.category)) return toast('Choose a category for every part');
    SP.splitting = false; SP.splitParts = null;
    await spEdit({action: 'split', id: t.id, parts: P.map(p => ({category: p.category, amount: sign * Math.abs(+p.amount)}))}, 'Split saved');
  };
}
async function waitForReply(id) {
  for (let i = 0; i < 120; i++) {
    await new Promise(r => setTimeout(r, i < 10 ? 1000 : 2000));
    await loadSpending();
    const t = txById(id), last = t && t.thread && t.thread[t.thread.length - 1];
    if (SP.d.status.note_tx !== id && (!last || last.role === 'claude')) break;
  }
  if (view === 'spending' && !(document.activeElement && /SELECT|INPUT/.test(document.activeElement.tagName))) { const y = scrollY; spendingPage(); scrollTo(0, y); }
  if (SP.sheet === id) { drawSheet(); const q = $('#shMsg'); if (q) q.focus(); }
}

/* ---------- subscriptions ---------- */
function detectSubs() {
  // the same merchant at a regular interval: weekly, monthly, quarterly or yearly
  const cut = isoD(new Date(Date.now() - 800 * 864e5)), by = {};
  for (const t of SP.d.transactions) if (t.date >= cut && t.amount < 0 && !t.excluded && kindOf(t) === 'expense' && inAcct(t)) (by[t.key] = by[t.key] || []).push(t);
  const out = [];
  for (const [key, list] of Object.entries(by)) {
    list.sort((a, b) => a.date.localeCompare(b.date));
    if (list.length < 2) continue;
    const gaps = list.slice(1).map((t, i) => (Date.parse(t.date) - Date.parse(list[i].date)) / 864e5).sort((a, b) => a - b), gap = gaps[Math.floor(gaps.length / 2)];
    const freq = gap >= 5 && gap <= 9 ? ['weekly', 'every week', 52, 7] : gap >= 25 && gap <= 36 ? ['monthly', 'every month', 12, 30.44] : gap >= 80 && gap <= 100 ? ['quarterly', 'every quarter', 4, 91.3] : gap >= 340 && gap <= 390 ? ['yearly', 'every year', 1, 365.25] : null;
    if (!freq || (freq[0] !== 'yearly' && list.length < 3)) continue;
    const regular = gaps.filter(g => Math.abs(g - gap) <= Math.max(4, gap * 0.25)).length / gaps.length;
    if (regular < 0.6) continue;
    const amts = list.map(t => -t.amount), last = amts[amts.length - 1], med = [...amts].sort((a, b) => a - b)[Math.floor(amts.length / 2)];
    // a subscription charges the same, or nearly; shopping at the same shop every week does not
    const recent = amts.slice(-6), rmed = [...recent].sort((a, b) => a - b)[Math.floor(recent.length / 2)];
    if (freq[0] !== 'yearly' && recent.filter(a => Math.abs(a - rmed) <= Math.max(1.5, rmed * 0.15)).length / recent.length < 0.75) continue;
    if (list.length / Math.max(1, new Set(list.map(t => t.date.slice(0, 7))).size) > 2.5 && freq[0] !== 'weekly') continue;
    const lastDate = list[list.length - 1].date, next = isoD(new Date(Date.parse(lastDate + 'T12:00') + freq[3] * 864e5));
    const yearAgo = isoD(new Date(Date.now() - 400 * 864e5)), firstYear = list.find(t => t.date >= yearAgo) || list[0];
    const change = last - (-firstYear.amount);
    const st = SP.d.subscriptions[key] || {};
    const stale = (Date.now() - Date.parse(lastDate)) / 864e5 > freq[3] * 2.2;
    out.push({key, name: list[0].merchant, cat: list[list.length - 1].category, list, last, med, freq: freq[0], freqLabel: freq[1], next, lastDate, yearly: last * freq[2],
      change: Math.abs(change) >= 0.5 ? change : 0, since: firstYear.date, status: st.status || (stale ? 'stopped' : ''), statusDate: st.date,
      chargedAfter: st.status === 'cancelled' && list.some(t => t.date > st.date)});
  }
  return out.sort((a, b) => b.yearly - a.yearly);
}
function spSubs() {
  const subs = detectSubs(), active = subs.filter(s => !s.status), cancelled = subs.filter(s => s.status === 'cancelled' || s.status === 'stopped'), notSubs = subs.filter(s => s.status === 'not');
  const yearly = active.reduce((s, x) => s + x.yearly, 0), ups = active.filter(s => s.change > 0);
  const row = s => `<div class="sub-row ${SP.subOpen === s.key ? 'open' : ''}" data-subkey="${esc(s.key)}">
      <button type="button" class="sub-main" data-subopen="${esc(s.key)}"><span class="sub-name"><b>${esc(s.name)}</b><span class="muted small">${esc(catName(s.cat))}, ${esc(s.freqLabel)}${s.status === 'stopped' ? ', no payment lately' : ''}</span></span>
        <span class="sub-next small">${s.status ? (s.status === 'cancelled' ? `cancelled ${fdate(s.statusDate)}` : 'stopped') : `next ${fdate(s.next)}`}${s.chargedAfter ? '<br><span class="neg">charged after you cancelled</span>' : ''}</span>
        <span class="sub-chg small">${s.change ? `<span class="${s.change > 0 ? 'neg' : 'pos'}">${s.change > 0 ? '+' : '−'}${eur(Math.abs(s.change), 2)}</span> <span class="muted">since ${fdate(s.since.slice(0, 7))}</span>` : ''}</span>
        <span class="num"><b>${eur(s.last, 2)}</b><span class="muted small">${eur(s.yearly)} a year</span></span></button>
      <button type="button" class="icon-btn sm" data-submenu="${esc(s.key)}" aria-label="Options for ${esc(s.name)}">⋯</button>
      ${SP.subOpen === s.key ? `<div class="sub-detail"><div class="sub-chart" id="subChart"></div></div>` : ''}</div>`;
  $('#spBody').innerHTML = `<div class="stack-y">
    <div class="grid g4">
      <div class="card tile"><div class="k">Per year</div><div class="v">${eur(yearly)}</div><div class="n">${active.length} subscription${active.length === 1 ? '' : 's'}</div></div>
      <div class="card tile"><div class="k">Per month</div><div class="v">${eur(yearly / 12)}</div></div>
      <div class="card tile"><div class="k">Got more expensive</div><div class="v">${ups.length}</div><div class="n">${ups.length ? `${eur(ups.reduce((s, x) => s + x.change * ({weekly: 52, monthly: 12, quarterly: 4, yearly: 1}[x.freq]), 0))} a year more` : 'in the last year'}</div></div>
      <div class="card tile"><div class="k">Next up</div><div class="v small-v">${active.length ? esc([...active].sort((a, b) => a.next.localeCompare(b.next))[0].name) : '–'}</div><div class="n">${active.length ? fdate([...active].sort((a, b) => a.next.localeCompare(b.next))[0].next) : ''}</div></div>
    </div>
    <section class="card"><h2>Subscriptions and regular payments</h2><p class="sub">Found from payments to the same merchant at a regular interval. Click one for its price history.</p>
      ${active.map(row).join('') || '<div class="empty">Nothing regular found yet.</div>'}</section>
    ${cancelled.length ? `<section class="card"><h2>Cancelled or stopped</h2>${cancelled.map(row).join('')}</section>` : ''}
    ${notSubs.length ? `<details class="card"><summary class="muted">Marked as not a subscription (${notSubs.length})</summary>${notSubs.map(row).join('')}</details>` : ''}
  </div>`;
  $$('[data-subopen]').forEach(b => b.onclick = () => { SP.subOpen = SP.subOpen === b.dataset.subopen ? null : b.dataset.subopen; spSubs(); });
  $$('[data-submenu]').forEach(b => b.onclick = e => {
    e.stopPropagation();
    const s = subs.find(x => x.key === b.dataset.submenu);
    const m = openMenu(b, `<div class="menu-sec">${s.status === 'cancelled' ? '<button type="button" class="menu-row" data-ss=""><span class="ck"></span>Still running</button>' : '<button type="button" class="menu-row" data-ss="cancelled"><span class="ck"></span>Mark as cancelled</button>'}
      ${s.status === 'not' ? '<button type="button" class="menu-row" data-ss=""><span class="ck"></span>It is a subscription</button>' : '<button type="button" class="menu-row" data-ss="not"><span class="ck"></span>Not a subscription</button>'}
      <button type="button" class="menu-row" data-sspay><span class="ck"></span>Show the payments</button></div>`);
    $$('[data-ss]', m).forEach(x => x.onclick = () => { closeMenus(); spEdit({action: 'subscription', key: s.key, status: x.dataset.ss || null}, x.dataset.ss === 'cancelled' ? 'Marked as cancelled. You will see it if it is charged again.' : 'Saved'); });
    $('[data-sspay]', m).onclick = ev => { closeMenus(); openPop(() => ({title: s.name, list: s.list, filter: {q: s.name}}), ev); };
  });
  if (SP.subOpen && $('#subChart')) {
    const s = subs.find(x => x.key === SP.subOpen);
    if (s) timeChart($('#subChart'), {series: [{name: 'Price', pts: s.list.map(t => [tOf(t.date), -t.amount]), step: true, color: 'var(--s1)'}], height: 170, dots: s.list.map(t => ({t: tOf(t.date), v: -t.amount, label: `${fdate(t.date)}: ${fmtV(-t.amount, '€')}`, color: 'var(--s1)'})), label: 'Price history'});
  }
}

/* ---------- trips ---------- */
function detectTrips(list) {
  // payments abroad, grouped while no more than four days pass between them
  const abroad = list.filter(t => t.country && t.country !== SP.home && kindOf(t) === 'expense').sort((a, b) => a.date.localeCompare(b.date));
  const trips = [];
  for (const t of abroad) {
    const cur = trips[trips.length - 1];
    if (cur && (Date.parse(t.date) - Date.parse(cur.to)) / 864e5 <= 4) { cur.list.push(t); cur.to = t.date; cur.countries.add(t.country); }
    else trips.push({from: t.date, to: t.date, list: [t], countries: new Set([t.country])});
  }
  return trips.map(x => { const days = Math.round((Date.parse(x.to) - Date.parse(x.from)) / 864e5) + 1, total = -x.list.reduce((s, t) => s + t.amount, 0);
    const cats = {}; for (const t of x.list) cats[t.category || ''] = (cats[t.category || ''] || 0) - t.amount;
    return {...x, countries: [...x.countries], days, total, perDay: total / days, cats: Object.entries(cats).sort((a, b) => b[1] - a[1])}; })
    .filter(x => x.list.length >= 2 || x.total >= 50).reverse();
}
function spTrips() {
  const R = spRange(), list = txs(R.from, R.to), trips = detectTrips(list);
  const total = trips.reduce((s, x) => s + x.total, 0), days = trips.reduce((s, x) => s + x.days, 0), countries = new Set(trips.flatMap(x => x.countries));
  const names = cs => cs.map(ctyName).join(cs.length === 2 ? ' and ' : ', ');
  $('#spBody').innerHTML = `<div class="stack-y">
    <div class="grid g4">
      <div class="card tile"><div class="k">Trips</div><div class="v">${trips.length}</div><div class="n">${esc(R.label.toLowerCase())}</div></div>
      <div class="card tile"><div class="k">Spent abroad</div><div class="v">${eur(total)}</div></div>
      <div class="card tile"><div class="k">Per day away</div><div class="v">${days ? eur(total / days) : '–'}</div><div class="n">${days} day${days === 1 ? '' : 's'} with payments abroad</div></div>
      <div class="card tile"><div class="k">Countries</div><div class="v">${countries.size}</div><div class="n">${esc([...countries].slice(0, 4).map(ctyName).join(', '))}</div></div>
    </div>
    ${trips.length ? `<div class="grid trips">${trips.map((x, i) => `<button type="button" class="card trip" data-trip="${i}">
      <div class="trip-map">${miniMap(x.countries, 320, 120)}</div>
      <div class="trip-body"><b>${esc(names(x.countries))}</b><span class="muted small">${x.from === x.to ? fdate(x.from) : `${fdate(x.from).replace(/ \d{4}$/, '')} to ${fdate(x.to)}`} · ${x.days} day${x.days === 1 ? '' : 's'}</span>
        <div class="trip-nums"><span><b class="amt">${eur(x.total)}</b><span class="muted small">spent</span></span><span><b class="amt">${eur(x.perDay)}</b><span class="muted small">per day</span></span><span><b>${x.list.length}</b><span class="muted small">payments</span></span></div>
        <div class="trip-cats">${x.cats.slice(0, 3).map(([c, v]) => `<span class="tag">${esc(catName(c))} ${fmtV(v, '€', true)}</span>`).join('')}</div></div></button>`).join('')}</div>`
      : '<section class="card"><div class="empty">No payments abroad in this period. Trips appear here from the country of each payment.</div></section>'}
    <p class="muted small">A trip is a run of payments in other countries with at most four days between them. Bookings made from home, like flights, count at home.</p>
  </div>`;
  $$('[data-trip]').forEach(b => b.onclick = e => { const x = trips[+b.dataset.trip]; openPop(() => ({title: `${names(x.countries)}, ${fdate(x.from)}`, list: x.list, filter: {from: x.from, to: x.to}}), e); });
}

/* ---------- quick check, and the monthly review ---------- */
function spCheck() {
  const c = SP.check, pool = SP.d.transactions.filter(inAcct);
  const months = [...new Set(pool.map(t => t.date.slice(0, 7)))].sort().reverse();
  if (c.review === 'last') c.review = months.find(m => m < isoD(new Date()).slice(0, 7)) || months[0];
  const scope = c.review ? pool.filter(t => t.date.startsWith(c.review)) : pool;
  const key = SP.accts.join() + '|' + c.order + '|' + (c.review || '');
  if (!c.queue || c.key !== key) {
    // the order is fixed when the round starts, so checking one doesn't reshuffle the rest
    let open = scope.filter(t => !t.checked);
    if (c.order === 'big') open.sort((a, b) => Math.abs(b.amount) - Math.abs(a.amount));
    else if (c.order === 'merchant') { const n = {}; for (const t of open) n[t.key] = (n[t.key] || 0) + 1; open.sort((a, b) => n[b.key] - n[a.key] || a.key.localeCompare(b.key) || b.date.localeCompare(a.date)); }
    c.queue = open.map(t => t.id); c.pos = 0; c.key = key; c.log = [];
  }
  const done = scope.filter(t => t.checked).length, share = scope.length ? done / scope.length * 100 : 0;
  const t = c.pos < c.queue.length ? txById(c.queue[c.pos]) : null;
  const same = t ? pool.filter(o => o.key === t.key && !o.checked && o.category && o.category === t.category) : [];
  $('#spBody').innerHTML = `<div class="qc">
    <div class="qc-top"><div><b>${done.toLocaleString('en-GB')}</b> <span class="muted">of ${scope.length.toLocaleString('en-GB')} checked${c.review ? ` in ${fdate(c.review)}` : ''}</span></div>
      <div class="controls" style="margin:0">${seg('qcorder', [['big', 'Biggest first'], ['new', 'Newest first'], ['merchant', 'By merchant']], c.order)}
      <select id="qcMonth" aria-label="Review a month"><option value="">All months</option>${months.map(m => `<option value="${m}" ${c.review === m ? 'selected' : ''}>Review ${fdate(m)}</option>`).join('')}</select></div></div>
    <div class="qc-bar"><i style="width:${share}%"></i></div>
    ${t ? `<section class="card qc-card ${c.dir < 0 ? 'back' : ''} no-tools" id="qcCard" data-ctx="tx:${t.id}">
      <div class="qc-meta muted small"><span>${new Date(t.date + 'T12:00').toLocaleDateString('en-GB', {weekday: 'short', day: 'numeric', month: 'short', year: 'numeric'})}</span><span>${c.pos + 1} of ${c.queue.length}</span></div>
      <div class="qc-amt num">${amt(t)}</div>
      <div class="qc-m">${esc(t.merchant)}</div>
      <div class="muted small">${where(t) || '&nbsp;'}</div>
      <div class="qc-desc">${esc(t.description)}</div>
      ${linkNote(t)}
      <div class="qc-cat"><select id="qcCat" class="${t.category ? '' : 'unset'}" aria-label="Category">${catOptions(t.category, true)}</select>
        <span class="muted small">${t.checked ? 'checked' : t.category_source ? SRC[t.category_source] || '' : ''}</span>${noteChip(t)}</div>
      <div class="qc-act">
        <button type="button" class="btn ghost" id="qcBack" ${c.pos ? '' : 'disabled'} aria-label="Previous">←</button>
        <button type="button" class="btn" id="qcSkip">Skip</button>
        <button type="button" class="btn primary" id="qcOk" ${t.category ? '' : 'disabled'}>${TICK}Looks right</button>
      </div>
      ${same.length > 1 ? `<button type="button" class="linkish qc-all" id="qcAll">All ${same.length} unchecked from ${esc(t.merchant)} are ${esc(catName(t.category))}</button>` : ''}
    </section>
    <div class="qc-keys muted small"><kbd>Enter</kbd> looks right <kbd>S</kbd> skip <kbd>←</kbd> back${same.length > 1 ? ' <kbd>A</kbd> all from this merchant' : ''}${c.review ? ' · <button type="button" class="linkish small" id="qcFinish">Finish the review</button>' : ''}</div>`
    : c.review ? reviewSummary(scope) : `<section class="card qc-card no-tools"><div class="empty">${c.queue.length ? 'That was the last one in this round.' : 'Everything here is checked.'}</div>
      ${pool.some(o => !o.checked) ? '<div style="text-align:center"><button class="btn" id="qcAgain">Go through the skipped ones</button></div>' : ''}</section>`}
  </div>`;
  onSeg('qcorder', v => { c.order = v; store.set('sp.checkOrder', v); spCheck(); });
  $('#qcMonth').onchange = e => { c.review = e.target.value || null; c.queue = null; spCheck(); };
  if (!t) {
    if ($('#qcAgain')) $('#qcAgain').onclick = () => { c.queue = null; spCheck(); };
    if ($('#qcDone')) $('#qcDone').onclick = () => { c.review = null; c.queue = null; spCheck(); };
    return;
  }
  const next = () => { c.pos++; c.dir = 1; spCheck(); };
  $('#qcOk').onclick = () => { c.log.push({id: t.id, act: 'checked'}); setChecked([t.id], true, true); next(); };
  $('#qcSkip').onclick = next;
  $('#qcBack').onclick = () => { if (c.pos) { c.pos--; c.dir = -1; spCheck(); } };
  $('#qcCat').onchange = async e => { if (!e.target.value) return; c.log.push({id: t.id, act: 'category', from: t.category, to: e.target.value}); c.pos++; c.dir = 1; await setCat([t.id], e.target.value, SP.learn); };
  if ($('#qcFinish')) $('#qcFinish').onclick = () => { c.pos = c.queue.length; spCheck(); };
  if ($('#qcAll')) $('#qcAll').onclick = () => {
    const ids = new Set(same.map(o => o.id));
    ids.forEach(id => c.log.push({id, act: 'checked'}));
    setChecked([...ids], true, true);
    c.queue = c.queue.filter((q, i) => i <= c.pos || !ids.has(q));
    next();
  };
}
function reviewSummary(scope) {
  // what changed in this review, and the month in numbers
  const c = SP.check, checked = c.log.filter(x => x.act === 'checked').length, moved = c.log.filter(x => x.act === 'category');
  const T = totals(SP.rows.filter(t => inAcct(t) && t.date.startsWith(c.review)));
  const g = {};
  for (const t of SP.rows) if (inAcct(t) && t.date.startsWith(c.review) && kindOf(t) === 'expense') g[groupOf(t)] = (g[groupOf(t)] || 0) - t.amount;
  return `<section class="card qc-card no-tools review-sum"><h2>${fdate(c.review)} reviewed</h2>
    <div class="kv"><span>Checked in this review</span><span>${checked}</span><span>Categories changed</span><span>${moved.length}</span>
      <span>Still unchecked</span><span>${scope.filter(t => !t.checked).length}</span><span>Spent</span><span>${eur(T.spent)}</span><span>Income</span><span>${eur(T.income)}</span><span>Saved</span><span>${sgn(T.saved)}</span></div>
    ${moved.length ? `<h4 class="grp">Changed</h4>${moved.map(x => { const t = txById(x.id); return `<div class="list-row small"><span>${esc(t ? t.merchant : '')}</span><span class="muted">${esc(catName(x.from))} → <b>${esc(catName(x.to))}</b></span></div>`; }).join('')}` : ''}
    <h4 class="grp">Where it went</h4>${Object.entries(g).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<div class="list-row small"><span>${esc(k)}</span><span class="num">${eur(v)}</span></div>`).join('')}
    <div style="margin-top:14px;text-align:right"><button type="button" class="btn primary" id="qcDone">Done</button></div></section>`;
}
document.addEventListener('keydown', e => {
  if (view !== 'spending' || SP.tab !== 'check' || $('#dlg').open || e.metaKey || e.ctrlKey || e.altKey) return;
  if (document.activeElement && /SELECT|INPUT|TEXTAREA/.test(document.activeElement.tagName)) return;
  const click = id => { const b = $(id); if (b && !b.disabled) { e.preventDefault(); b.click(); } };
  if (e.key === 'Enter' || e.key === 'ArrowRight') click('#qcOk');
  else if (e.key === 's' || e.key === 'S') click('#qcSkip');
  else if (e.key === 'ArrowLeft' || e.key === 'Backspace') click('#qcBack');
  else if (e.key === 'a' || e.key === 'A') click('#qcAll');
});

/* ---------- countries ---------- */
function spCountries() {
  const R = spRange(), {from, to} = R;
  const exp = txs(from, to).filter(t => kindOf(t) === 'expense');
  const by = {};
  for (const t of exp) { const b = by[t.country || ''] = by[t.country || ''] || {v: 0, n: 0, cats: {}}; b.v -= t.amount; b.n++; b.cats[t.category || ''] = (b.cats[t.category || ''] || 0) - t.amount; }
  const cb = {};
  if (R.cmp) for (const t of txs(R.cmp.from, R.cmp.to)) if (kindOf(t) === 'expense') cb[t.country || ''] = (cb[t.country || ''] || 0) - t.amount;
  const rows = Object.entries(by).filter(([, b]) => b.v > 0.5).sort((a, b) => b[1].v - a[1].v);
  const total = rows.reduce((s, [, b]) => s + b.v, 0) || 1, max = Math.max(1, ...rows.filter(([c]) => c).map(([, b]) => b.v));
  const unplaced = SP.d.transactions.filter(t => inAcct(t) && !t.country && !t.country_source).length;
  // asked about already, and the text held no clue; worth offering once more after a later import
  const blank = SP.d.transactions.filter(t => inAcct(t) && !t.country && t.country_source === 'ai').length;
  PICKS.cty = c => ({title: ctyName(c), filter: {from, to, country: c || 'none'}, list: exp.filter(t => (t.country || '') === c)});
  const G = GEO;
  const fill = v => v ? `color-mix(in srgb, var(--accent) ${Math.round(18 + 82 * Math.log1p(v) / Math.log1p(max))}%, var(--surface-2))` : '';
  $('#spBody').innerHTML = `<div class="stack-y">
    ${unplaced ? `<div class="banner">${unplaced.toLocaleString('en-GB')} payment${unplaced === 1 ? ' has' : 's have'} no country yet.
      ${SP.d.status.ai ? '' : '<button class="linkish" id="ctyAi">Let Claude work them out</button>'}</div>`
      : blank ? `<div class="banner">${blank.toLocaleString('en-GB')} payment${blank === 1 ? '' : 's'} could not be placed from the text.
      ${SP.d.status.ai ? '' : '<button class="linkish" id="ctyAgain">Try those again</button>'}</div>` : ''}
    <section class="card map-card no-tools">
      <div class="map" id="map"><svg viewBox="0 0 ${G.w} ${G.h}" aria-label="Map of spending per country">
        <g id="mapG">${Object.entries(G.countries).filter(([, c]) => c.p).map(([k, c]) => {
          const b = by[k];
          return `<path d="${c.p}" data-cty="${k}" class="${b && b.v > 0.5 ? 'has' : ''}" ${b && b.v > 0.5 ? `style="fill:${fill(b.v)}" data-tip="${esc(c.n)}: €${fmtN(b.v)}, ${b.n} payment${b.n === 1 ? '' : 's'}"` : ''}/>`;
        }).join('')}</g></svg>
        <div class="map-zoom"><button type="button" data-z="1.6" aria-label="Zoom in">+</button><button type="button" data-z="0.625" aria-label="Zoom out">−</button><button type="button" data-z="fit" aria-label="Fit">⤢</button></div>
      </div>
    </section>
    <section class="card"><div class="card-head"><h2>Spending per country</h2><span class="muted small">${eur(total)} in ${rows.filter(([c]) => c).length} countr${rows.filter(([c]) => c).length === 1 ? 'y' : 'ies'}</span></div>
      ${rows.map(([c, b]) => { const top = Object.entries(b.cats).sort((x, y) => y[1] - x[1])[0];
        return `<button class="barrow cty-row" data-cty="${c}"><span class="bl"><b><span class="cc">${c || '?'}</span>${esc(ctyName(c))}</b><span class="muted small">${b.n} payment${b.n === 1 ? '' : 's'}${top ? ', mostly ' + esc(catName(top[0]).toLowerCase()) : ''}${R.cmp ? `, vs ${fmtV(cb[c] || 0, '€')}` : ''}</span></span>
          <span class="bb"><i style="width:${b.v / rows[0][1].v * 100}%"></i></span><span class="bv">${eur(b.v)}<span class="muted small">${(b.v / total * 100).toFixed(b.v / total < 0.01 ? 1 : 0)}%</span></span></button>`; }).join('') || '<div class="empty">Nothing spent in this period.</div>'}
    </section>
  </div>`;
  if ($('#ctyAi')) $('#ctyAi').onclick = async () => {
    try { await post('/api/spending/places', {}); toast('Claude is working out where you spent money'); await loadSpending(); spendingPage(); } catch (e) { toast(e.message); }
  };
  if ($('#ctyAgain')) $('#ctyAgain').onclick = async () => {
    try { await post('/api/spending/places', {again: true}); toast('Claude is looking at those again'); await loadSpending(); spendingPage(); } catch (e) { toast(e.message); }
  };
  $$('.cty-row').forEach(b => b.onclick = e => openPop(() => PICKS.cty(b.dataset.cty), e));
  wireMap(rows.map(([c]) => c).filter(c => c && G.countries[c] && G.countries[c].b), by);
}
function wireMap(codes) {
  const G = GEO, svg = $('#map svg'), g = $('#mapG');
  const key = SP.accts.join() + '|' + RANGE.p + '|' + codes.join();
  const fit = () => {
    // frame the countries with spending; the whole world when there are none
    let b = [0, 0, G.w, G.h];
    if (codes.length) {
      b = codes.map(c => G.countries[c].b).reduce((a, x) => [Math.min(a[0], x[0]), Math.min(a[1], x[1]), Math.max(a[2], x[2]), Math.max(a[3], x[3])]);
      const padX = Math.max(25, (b[2] - b[0]) * 0.15), padY = Math.max(18, (b[3] - b[1]) * 0.15);
      b = [b[0] - padX, b[1] - padY, b[2] + padX, b[3] + padY];
    }
    const k = Math.min(30, Math.max(1, Math.min(G.w / (b[2] - b[0]), G.h / (b[3] - b[1]))));
    return {k, x: G.w / 2 - k * (b[0] + b[2]) / 2, y: G.h / 2 - k * (b[1] + b[3]) / 2};
  };
  if (!SP.map || SP.map.key !== key) SP.map = {key, ...fit()};
  const m = SP.map;
  const clamp = () => { m.k = Math.min(60, Math.max(1, m.k)); m.x = Math.min(0, Math.max(G.w - G.w * m.k, m.x)); m.y = Math.min(0, Math.max(G.h - G.h * m.k, m.y)); };
  const draw = () => { clamp(); g.setAttribute('transform', `translate(${m.x} ${m.y}) scale(${m.k})`); };
  const toSvg = (cx, cy) => { const r = svg.getBoundingClientRect(); return [(cx - r.left) / r.width * G.w, (cy - r.top) / r.height * G.h]; };
  const zoomAt = (f, px, py) => { const nk = Math.min(60, Math.max(1, m.k * f)); m.x = px - (px - m.x) * nk / m.k; m.y = py - (py - m.y) * nk / m.k; m.k = nk; draw(); };
  draw();
  svg.addEventListener('wheel', e => { e.preventDefault(); const [px, py] = toSvg(e.clientX, e.clientY); zoomAt(Math.exp(-e.deltaY * 0.0015), px, py); }, {passive: false});
  let drag = null, moved = 0;
  const pts = new Map();
  svg.addEventListener('pointerdown', e => {
    pts.set(e.pointerId, [e.clientX, e.clientY]);
    drag = {x: e.clientX, y: e.clientY, mx: m.x, my: m.y, d: null}; moved = 0;
    if (pts.size === 2) { const [a, b] = [...pts.values()]; drag.d = Math.hypot(a[0] - b[0], a[1] - b[1]); drag.k = m.k; }
  });
  svg.addEventListener('pointermove', e => {
    if (!drag || !pts.has(e.pointerId)) return;
    pts.set(e.pointerId, [e.clientX, e.clientY]);
    const r = svg.getBoundingClientRect(), s = G.w / r.width;
    if (pts.size === 2 && drag.d) { const [a, b] = [...pts.values()], [px, py] = toSvg((a[0] + b[0]) / 2, (a[1] + b[1]) / 2); zoomAt(drag.k * Math.hypot(a[0] - b[0], a[1] - b[1]) / drag.d / m.k, px, py); moved = 99; return; }
    moved = Math.max(moved, Math.hypot(e.clientX - drag.x, e.clientY - drag.y));
    if (moved > 4) { svg.setPointerCapture(e.pointerId); svg.classList.add('dragging'); m.x = drag.mx + (e.clientX - drag.x) * s; m.y = drag.my + (e.clientY - drag.y) * s; draw(); }
  });
  const up = e => { pts.delete(e.pointerId); if (!pts.size) { drag = null; svg.classList.remove('dragging'); } };
  svg.addEventListener('pointerup', up); svg.addEventListener('pointercancel', up);
  svg.addEventListener('click', e => { if (moved > 4) return; const p = e.target.closest('path.has'); if (p) openPop(() => PICKS.cty(p.dataset.cty), e); });
  $$('[data-z]').forEach(b => b.onclick = () => { if (b.dataset.z === 'fit') { Object.assign(m, fit()); draw(); return; } zoomAt(+b.dataset.z, G.w / 2, G.h / 2); });
}

/* ---------- review ---------- */
function spReview() {
  const groups = {};
  for (const t of SP.d.transactions) if (needsReview(t) && inAcct(t)) (groups[t.key] = groups[t.key] || []).push(t);
  const list = Object.values(groups).sort((a, b) => b.length - a.length || Math.abs(b.reduce((s, t) => s + t.amount, 0)) - Math.abs(a.reduce((s, t) => s + t.amount, 0)));
  $('#spBody').innerHTML = `<section class="card">
    <div class="card-head"><div><h2>Needs a category</h2><p class="sub">Grouped by merchant. Your choice is remembered, so future transactions from the same merchant are categorised automatically.</p></div>
      ${list.length && !SP.d.status.ai ? '<button class="btn" id="aiAgain">Let the AI try again</button>' : ''}</div>
    ${list.map((ts, i) => `<div class="rev"><div><div class="nm">${esc(ts[0].merchant)}</div>
        <div class="muted small">${ts.length} transaction${ts.length > 1 ? 's' : ''}, ${sgn(ts.reduce((s, t) => s + t.amount, 0), 2)}, ${fdate(ts[ts.length - 1].date)}${ts.length > 1 ? ' to ' + fdate(ts[0].date) : ''}</div>
        <div class="meta desc">${esc(ts[0].description)}</div></div>
      <div class="rev-act"><select data-rev="${i}">${catOptions(null, true)}</select></div></div>`).join('') || '<div class="empty">Everything is categorised.</div>'}
  </section>`;
  $$('[data-rev]').forEach(s => s.onchange = () => { if (s.value) setCat(list[+s.dataset.rev].map(t => t.id), s.value, true); });
  if ($('#aiAgain')) $('#aiAgain').onclick = async () => { await post('/api/spending/recategorize', {}); toast('The AI is having another look'); await loadSpending(); spendingPage(); };
}

/* ---------- categories, rules, accounts, imports ---------- */
/* ---------- income ---------- */
function spIncome() {
  const r = spRange(), list = txs(r.from, r.to).filter(t => kindOf(t) === 'income');
  const months = monthsIn(txs(r.from, r.to));
  const W = Math.max(320, $('#view').clientWidth - 42), half = innerWidth > 900 ? (W - 58) / 2 : W;
  const by = {};
  for (const t of list) by[inName(t)] = (by[inName(t)] || 0) + t.amount;
  const rows = Object.entries(by).sort((a, b) => b[1] - a[1]);
  const total = rows.reduce((s, x) => s + x[1], 0), max = rows.length ? rows[0][1] : 1;
  // what you earn yourself, apart from gifts and money that only came back to you
  const back = by[BACK] || 0;
  const own = rows.filter(([n]) => !/gift/i.test(n) && n !== BACK).reduce((s, x) => s + x[1], 0);
  const spent = totals(txs(r.from, r.to)).spent;
  const keep = rows.slice(0, SERIES.length - 1).map(([n]) => n);
  const series = [...keep.map(n => ({name: n})), ...(rows.length > keep.length ? [{name: 'Other'}] : [])];
  const member = (t, k) => k < keep.length ? inName(t) === keep[k] : !keep.includes(inName(t));
  const stack = {type: 'stacked', unit: '€', labels: months.map(mLabel), pick: 'incMonth', xkeys: months, series: series.map(s => ({name: s.name,
    values: months.map(m => list.filter(t => t.date.startsWith(m) && (s.name === 'Other' ? !keep.includes(inName(t)) : inName(t) === s.name))
      .reduce((a, t) => a + t.amount, 0))}))};
  PICKS.incMonth = (i, k) => ({title: `${mLabel(months[i])} · ${stack.series[k].name}`, filter: {from: `${months[i]}-01`, to: `${months[i]}-31`},
    list: list.filter(t => t.date.startsWith(months[i]) && member(t, k))});
  PICKS.incCat = c => ({title: c, filter: {from: r.from, to: r.to}, list: list.filter(t => inName(t) === c)});
  PICKS.incWho = m => ({title: m, filter: {from: r.from, to: r.to, q: m}, list: list.filter(t => t.merchant === m)});
  const payers = {};
  for (const t of list) payers[t.merchant] = (payers[t.merchant] || 0) + t.amount;
  const top = Object.entries(payers).sort((a, b) => b[1] - a[1]).slice(0, 10), pmax = top.length ? top[0][1] : 1;
  const n = Math.max(1, months.length);
  $('#spBody').innerHTML = `<div class="stack-y">
    <div class="grid g4">
      <div class="card tile"><div class="k">Money in</div><div class="v">${eur(total)}</div><div class="n">${n} month${n > 1 ? 's' : ''}</div></div>
      <div class="card tile"><div class="k">Per month</div><div class="v">${eur(total / n)}</div><div class="n">on average</div></div>
      <div class="card tile"><div class="k">Earned yourself</div><div class="v">${eur(own)}</div><div class="n">${total ? (own / total * 100).toFixed(0) : 0}% of money in, gifts and money back left out</div></div>
      <div class="card tile"><div class="k">Left after spending</div><div class="v">${sgn(own - (spent - back))}</div><div class="n">on what you earned yourself</div></div>
    </div>
    <section class="card" data-pick="incMonth"><h2>Income per month</h2>
      ${months.length ? chartHtml(stack, W) : '<div class="empty">Nothing in this period.</div>'}</section>
    <div class="grid g2">
      <section class="card"><h2>Where it comes from</h2>
        ${rows.map(([n2, v]) => `<button class="barrow" data-inccat="${esc(n2)}"><span class="bl"><b>${esc(n2)}</b></span>
          <span class="bb"><i style="width:${v / max * 100}%"></i></span><span class="bv">${eur(v)}<span class="muted small">${(v / total * 100).toFixed(0)}%</span></span></button>`).join('') || '<div class="empty">Nothing yet.</div>'}
      </section>
      <section class="card"><h2>Who pays you</h2>
        ${top.map(([m, v]) => `<button class="barrow" data-incwho="${esc(m)}"><span class="bl"><b>${esc(m)}</b></span><span class="bb"><i style="width:${v / pmax * 100}%"></i></span><span class="bv">${eur(v)}</span></button>`).join('') || '<div class="empty">Nothing yet.</div>'}
      </section>
    </div>
    <section class="card"><h2>All money in</h2>
      <div class="table-wrap"><table><thead><tr><th>Date</th><th>From</th><th>Category</th><th class="num">Amount</th></tr></thead>
      <tbody>${list.slice().sort((a, b) => b.date.localeCompare(a.date) || b.amount - a.amount).slice(0, 120).map(t => `<tr data-open="${t.id}">
        <td class="muted small" style="white-space:nowrap">${fdate(t.date)}</td><td><div class="nm">${esc(t.merchant)}</div><div class="meta">${esc(where(t))}</div></td>
        <td>${esc(inName(t))}</td><td class="num">${amt(t)}</td></tr>`).join('') || '<tr><td colspan="4" class="empty">Nothing yet.</td></tr>'}</tbody></table></div>
    </section>
  </div>`;
  $$('[data-inccat]').forEach(b => b.onclick = e => openPop(() => PICKS.incCat(b.dataset.inccat), e));
  $$('[data-incwho]').forEach(b => b.onclick = e => openPop(() => PICKS.incWho(b.dataset.incwho), e));
  $$('#spBody tr[data-open]').forEach(tr => tr.onclick = () => txSheet(tr.dataset.open));
}

function spCategories() {
  const since = new Date(); since.setFullYear(since.getFullYear() - 1);
  const cut = since.toISOString().slice(0, 10), stats = {};
  for (const t of SP.rows) if (t.category && t.date >= cut) { const s = stats[t.category] = stats[t.category] || {n: 0, v: 0}; s.n++; s.v += t.amount; }
  const groups = {};
  for (const c of SP.d.categories) (groups[c.group] = groups[c.group] || []).push(c);
  const kinds = {expense: 'spending', income: 'income', transfer: 'transfer, not counted'};
  $('#spBody').innerHTML = `<div class="grid g2">
    <section class="card"><div class="card-head"><div><h2>Categories</h2><p class="sub">Last 12 months</p></div><button class="btn" id="catAdd">Add category</button></div>
      ${Object.entries(groups).map(([g, cs]) => `<h4 class="grp">${esc(g)}</h4>${cs.map(c => `<div class="list-row"><div><div style="font-weight:600">${esc(c.name)}</div><div class="muted small">${kinds[c.kind]}${stats[c.id] ? `, ${stats[c.id].n} transactions` : ''}</div></div>
        <div class="num">${stats[c.id] ? eur(Math.abs(stats[c.id].v)) : ''} <button class="btn ghost" data-catedit="${c.id}">Edit</button></div></div>`).join('')}`).join('')}
    </section>
    <div class="stack-y">
      <section class="card"><h2>Accounts</h2><p class="sub">Investment accounts are left out of spending and income; what happens on them belongs to your portfolio.</p>
        ${Object.entries(SP.d.accounts).filter(([id]) => SP.allTx.some(t => t.account === id)).map(([id, a]) => {
          const inv = SP.invest.has(id), n = SP.allTx.filter(t => t.account === id).length;
          return `<div class="list-row"><div><div style="font-weight:600">${esc(a.name)}${inv ? ' <span class="tag">investment</span>' : ''}</div><div class="muted small">${esc(id)}, ${n} transactions</div></div>
            <div><button class="btn ghost" data-role="${esc(id)}" data-to="${inv ? 'payment' : 'investment'}">${inv ? 'Count as spending' : 'Mark as investment'}</button><button class="btn ghost" data-acct="${esc(id)}">Rename</button></div></div>`;
        }).join('') || '<div class="empty">None yet.</div>'}
      </section>
      <section class="card"><h2>Rules</h2>
        ${SP.d.rules.map((r, i) => `<div class="list-row small"><div><b>${esc(r.label || r.match)}</b> ${r.type === 'contains' ? '(text contains)' : ''} → ${esc(catName(r.category))}</div><button class="btn ghost" data-rule="${i}">Remove</button></div>`).join('') || '<div class="empty">No rules yet.</div>'}
      </section>
      <section class="card"><h2>Imports</h2>
        ${[...SP.d.imports].reverse().map(i => `<div class="list-row small"><div><b>${esc(i.file)}</b><div class="muted">${i.added} transactions, ${fdate(i.from)} to ${fdate(i.to)}, imported ${fdate(i.date)}</div></div><button class="btn ghost danger" data-imp="${i.id}">Remove</button></div>`).join('') || '<div class="empty">Nothing imported yet.</div>'}
      </section>
    </div></div>`;
  const groupNames = [...new Set(SP.d.categories.map(c => c.group))];
  const catForm = (title, c, done) => form(title, [
    {k: 'name', label: 'Name', type: 'text', value: c.name || ''},
    {k: 'group', label: `Group (for example ${groupNames.slice(0, 3).join(', ')})`, type: 'text', value: c.group || ''},
    {k: 'kind', label: 'Counts as: expense, income or transfer', type: 'text', value: c.kind || 'expense'}], done,
    c.id ? () => spEdit({action: 'category-delete', id: c.id}, 'Category removed') : null);
  $('#catAdd').onclick = () => catForm('Add category', {}, v => spEdit({action: 'category-add', ...v}, 'Category added'));
  $$('[data-catedit]').forEach(b => b.onclick = () => { const c = SP.cat[b.dataset.catedit]; catForm('Edit ' + c.name, c, v => spEdit({action: 'category-update', id: c.id, ...v}, 'Saved')); });
  $$('[data-acct]').forEach(b => b.onclick = () => form('Rename account', [{k: 'name', label: b.dataset.acct, type: 'text', value: acctName(b.dataset.acct)}],
    v => spEdit({action: 'account-rename', id: b.dataset.acct, name: v.name}, 'Renamed')));
  $$('[data-role]').forEach(b => b.onclick = () => spEdit({action: 'account-rename', id: b.dataset.role, role: b.dataset.to},
    b.dataset.to === 'investment' ? 'Left out of spending' : 'Counted as spending'));
  $$('[data-rule]').forEach(b => b.onclick = () => spEdit({action: 'rule-delete', index: +b.dataset.rule}, 'Rule removed'));
  $$('[data-imp]').forEach(b => b.onclick = () => { if (confirmTwice('imp' + b.dataset.imp, 'Click Remove again to delete the transactions of this import.')) spEdit({action: 'import-delete', id: b.dataset.imp}, 'Import removed'); });
}

function spEmpty() {
  $('#spBody').innerHTML = `<section class="card"><h2>No transactions yet</h2>
    <p class="sub">Drop your bank exports on the <a href="#import">Import</a> page (or attach them for Claude). Payment account files are recognised and end up here, categorised.</p>
    <p class="sub" style="margin:0">CSV or TXT exports from your bank or credit card work best. PDF statements and screenshots of payments work too.</p>
    <a class="btn primary" href="#import" style="margin-top:14px">Go to Import</a></section>`;
}
