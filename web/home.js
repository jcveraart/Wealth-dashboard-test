'use strict';
/* The home page: net worth with Claude's briefing, tiles, the ask box, the net worth charts, this month, pinned answers. */

const HOME = {brief: null, briefAt: 0, imports: null, nwView: store.get('nw.view', 'line'), nwPct: store.get('nw.pct', false), wfMonth: null};

function historyIn(from, to) {
  return (S.history || []).filter(h => h.date >= from && h.date <= to);
}
function pointBefore(iso) {
  // the last history row on or before a date
  let best = null;
  for (const h of S.history || []) if (h.date <= iso) best = h;
  return best;
}
function tileDelta(key, now, goodUp = true) {
  const a = pointBefore(isoD(new Date(Date.now() - 30 * 864e5)));
  if (!a || a[key] == null || a.date === today()) return '<div class="tile-delta muted">no change data yet</div>';
  const d = now - a[key], p = a[key] ? d / Math.abs(a[key]) * 100 : null, good = goodUp ? d >= 0 : d <= 0;
  if (Math.abs(d) < 0.5) return `<div class="tile-delta muted">no change since ${fdate(a.date).replace(/ \d{4}$/, '')}</div>`;
  return `<div class="tile-delta"><span class="${good ? 'pos' : 'neg'}">${d > 0 ? '↑' : '↓'} <span class="amt">€${fmtN(d)}</span>${p != null && Math.abs(p) < 1000 ? ` (${Math.abs(p).toFixed(1)}%)` : ''}</span> <span class="muted">since ${fdate(a.date).replace(/ \d{4}$/, '')}</span></div>`;
}
function trend(key) {
  const cut = isoD(new Date(Date.now() - 120 * 864e5));
  return spark((S.history || []).filter(h => h.date >= cut && h[key] != null).map(h => h[key]));
}
function overview() {
  const t = S.totals, m = S.managed, errs = S.status.errors.length;
  const briefOff = UIS.prefs && UIS.prefs.briefing === 'off';
  const movers = combined(allPositions()).filter(p => p.live).sort((a, b) => Math.abs(b.day_change) - Math.abs(a.day_change)).slice(0, 6);
  const mat = maturities().slice(0, 5);
  const alloc = allocation(ui.allocBy);
  $('#view').innerHTML = `<div class="stack-y home">
    <div class="home-top ${briefOff ? 'solo' : ''}">
      <section class="card hero" data-card="hero">
        <div class="label">Net worth</div>
        <div class="big" data-count="${t.net_worth}">${eur(t.net_worth)}</div>
        <div class="day">${dayc(t.day_change, allPositions().filter(p => p.live).reduce((x, p) => x + p.value, 0))} today on listed investments</div>
        ${tileDelta('net_worth', t.net_worth).replace('tile-delta', 'tile-delta hero-delta')}
        <div class="hero-foot muted small">${m.mode === 'positions' ? 'Managed portfolio priced live' : m.mode === 'proxy' ? `Managed portfolio estimated since ${fdate(m.last_real_date)}` : `Managed portfolio as of ${fdate(m.last_real_date)}`}${errs ? ` · <a href="#settings">${errs} pricing issue${errs > 1 ? 's' : ''}</a>` : ''}</div>
      </section>
      ${briefOff ? '' : `<section class="card brief no-tools" id="brief">${briefHtml()}</section>`}
    </div>
    <div class="grid g4">
      ${tile('Total assets', t.gross, 'gross', true, 'assets')}
      ${tile('Debt', t.debt, 'debt', false, 'debts')}
      ${tile('Investment profit', t.investing_profit, 'invest_profit', true, 'profit', 'sgn')}
      ${tile('Savings & cash', t.savings, 'savings', true, 'savings')}
    </div>
    <form class="askbar" id="askbar" role="search"><span class="claude-mark">${CLAUDE_ICON}</span>
      <input type="text" id="askIn" placeholder="Ask Claude anything about your money…" aria-label="Ask Claude anything about your money" autocomplete="off"><kbd>/</kbd></form>
    ${accountsCard()}
    <section class="card" data-card="networth" id="nwCard">
      <div class="card-head"><h2>Net worth</h2><div class="controls" style="margin:0">
        ${seg('nwview', [['line', 'Over time'], ['type', 'By type'], ['month', 'Per month']], HOME.nwView)}
        ${HOME.nwView !== 'month' ? seg('nwpct', [['eur', '€'], ['pct', '%']], HOME.nwPct ? 'pct' : 'eur') : ''}</div></div>
      <div id="nwBody"></div>
    </section>
    <div class="grid g3">
      <section class="card">
        <div class="card-head"><h2>Allocation</h2>${seg('alloc', [['type', 'By type'], ['account', 'By account']], ui.allocBy)}</div>
        <div class="alloc" data-pick="alloc">${alloc.map((p, i) => `<div data-pt="${i}|0" data-tip="${esc(p[0])}: ${fmtV(p[1], '€')}" style="flex:${Math.max(p[1], 0)};background:var(${SERIES[i]})"></div>`).join('')}</div>
        <div class="legend" data-pick="alloc">${alloc.map((p, i) => `<button type="button" class="row" data-pt="${i}|0"><span class="sw" style="background:var(${SERIES[i]})"></span><span>${esc(p[0])}</span><span class="num">${eur(p[1])}</span><span class="pct">${(p[1] / t.gross * 100).toFixed(0)}%</span></button>`).join('')}</div>
      </section>
      <section class="card">
        <div class="card-head"><h2>Biggest moves today</h2><a class="btn ghost" href="#holdings">All</a></div>
        ${movers.length ? movers.map(p => `<button type="button" class="list-row row-btn" data-open="holding:${esc(p.isin || 'n:' + p.name.trim().toLowerCase())}" data-ctx="holding:${esc(p.isin || 'n:' + p.name.trim().toLowerCase())}"><div><div style="font-weight:600">${esc(p.name)}</div><div class="muted small">${eur(p.value)}</div></div><div class="num">${sgn(p.day_change)}<div class="small">${pct(p.value - p.day_change ? p.day_change / (p.value - p.day_change) * 100 : 0, 1)}</div></div></button>`).join('') : '<div class="empty">No live prices yet.</div>'}
      </section>
      <section class="card">
        <div class="card-head"><h2>Coming up</h2><a class="btn ghost" href="#cash">All</a></div>
        ${mat.map(x => `<div class="list-row"><div><div style="font-weight:600">${esc(x.name)}</div><div class="muted small">${x.kind} matures ${fdate(x.date)}</div></div><div class="num">${eur(x.value)}<div class="small muted">${monthsUntil(x.date)}</div></div></div>`).join('') || '<div class="empty">No maturity dates recorded.</div>'}
      </section>
    </div>
    <section class="card month-card" id="monthStrip"><div class="card-head"><h2>This month</h2><span class="muted small" id="msWhen"></span></div><div class="mstrip">${'<div class="ms skel-line"></div>'.repeat(4)}</div></section>
    <div id="pinsSlot"></div>
  </div>`;
  onSeg('alloc', v => { ui.allocBy = v; store.set('allocBy', v); overview(); });
  onSeg('nwview', v => { HOME.nwView = v; store.set('nw.view', v); overview(); });
  onSeg('nwpct', v => { HOME.nwPct = v === 'pct'; store.set('nw.pct', HOME.nwPct); drawNetWorth(); });
  PICKS.alloc = i => allocRows(alloc[i][0]);
  PICKS.tile = i => tileRows(['assets', 'debts', 'profit', 'savings'][i]);
  $('#askbar').onsubmit = e => { e.preventDefault(); const v = $('#askIn').value.trim(); if (v) { $('#askIn').value = ''; openChat({text: v, send: true}); } else openChat(); };
  renderPins();
  attachTips($('.home'), $('.home'));
  drawNetWorth();
  fillAccountSparks();
  fillMonth();
  loadBrief();
  countUp();
}
/* ---------- every account at a glance: day to day money, savings, and what is invested ---------- */
function accountGroups() {
  const m = S.managed, rate = s => s.rate_pct ? `${(+s.rate_pct).toFixed(2)}%` : '';
  const asOf = d => d ? `as of ${fdate(d).replace(/ \d{4}$/, '')}` : '';
  const row = (name, value, sub, right, open, spark = name) => ({name, value, sub, right, open, spark});
  const day = [
    ...S.savings.filter(s => s.kind === 'payment' && !s.invest).map(s => row(s.name, s.value, s.bank || 'Payment account', `<span class="muted">${asOf(s.snapshot_date)}</span>`, 'account:' + s.name)),
    // the cash at a broker is spendable money too (Trade Republic has a card on it)
    ...S.accounts.filter(a => Math.abs(a.cash) >= 0.5).map(a => row(a.name, a.cash, 'Cash at the broker', '', 'account:' + a.name, null)),
  ];
  const save = S.savings.filter(s => s.kind !== 'payment' && !s.invest).map(s => row(s.name, s.value, [s.bank, s.maturity ? 'matures ' + fdate(s.maturity) : ''].filter(Boolean).join(' · '),
    `<span class="muted">${rate(s) || asOf(s.snapshot_date)}</span>`, 'account:' + s.name));
  const inv = [
    ...S.accounts.map(a => row(a.name, a.value, `${a.positions} investment${a.positions === 1 ? '' : 's'}`, a.positions ? dayc(a.day_change, a.value) : '', 'account:' + a.name)),
    row(m.name, m.value, m.mode === 'positions' ? 'Managed, priced live' : m.mode === 'proxy' ? 'Managed, estimated' : 'Managed', m.mode === 'positions' ? dayc(m.day_change, m.value) : '', 'account:' + m.name),
    ...S.savings.filter(s => s.invest).map(s => row(s.name, s.value, [s.kind === 'deposit' ? 'Deposit' : 'Savings', s.maturity ? 'matures ' + fdate(s.maturity) : ''].filter(Boolean).join(' · '), `<span class="muted">${rate(s)}</span>`, 'account:' + s.name)),
  ];
  const by = rows => rows.sort((a, b) => b.value - a.value);
  return [['Day to day', by(day)], ['Savings', by(save)], ['Investing', by(inv)]].filter(([, rows]) => rows.length);
}
function accountsCard() {
  const groups = accountGroups(), invDay = S.accounts.reduce((s, a) => s + a.day_change, 0) + (S.managed.day_change || 0);
  return `<section class="card" data-card="accounts" id="acctCard"><div class="card-head"><h2>Accounts</h2></div>
    <div class="acc-cols">${groups.map(([title, rows]) => { const tot = rows.reduce((s, r) => s + r.value, 0);
      return `<div class="acc-col"><div class="acc-h"><span>${title}</span><span class="num">${eur(tot)}${title === 'Investing' && Math.abs(invDay) >= 0.5 ? ` <span class="small">${dayc(invDay, tot)}</span>` : ''}</span></div>
        ${rows.map(r => `<button type="button" class="acc-row" data-open="${esc(r.open)}" data-ctx="${esc(r.open)}">
          <span class="acc-n"><b>${esc(r.name)}</b><span class="muted small">${esc(r.sub)}</span></span>
          <span class="acc-sp" ${r.spark ? `data-acc-spark="${esc(r.spark)}"` : ''}></span>
          <span class="acc-v num">${eur(r.value)}<span class="small">${r.right}</span></span></button>`).join('')}</div>`; }).join('')}</div></section>`;
}
async function fillAccountSparks() {
  const all = await loadAcctDaily();
  $$('[data-acc-spark]').forEach(el => { const rows = all[el.dataset.accSpark] || []; if (rows.length > 2) el.innerHTML = spark(rows.slice(-90).map(r => r.value), {w: 64, h: 22}); });
}
function tile(label, value, key, goodUp, rows, fmt = 'eur') {
  const i = ['assets', 'debts', 'profit', 'savings'].indexOf(rows);
  return `<div class="card tile" data-pick="tile"><button type="button" class="tile-btn" data-pt="${i}|0" aria-label="${esc(label)}: show what is in it">
    <div class="k">${esc(label)}</div><div class="tile-row"><div class="v" data-count="${value}" data-fmt="${fmt}">${fmt === 'sgn' ? sgn(value) : eur(value)}</div>${trend(key)}</div>
    ${tileDelta(key, value, goodUp)}</button></div>`;
}
function rowsPop(title, rows) { return {title, rows}; }
function tileRows(kind) {
  const t = S.totals;
  if (kind === 'assets') return rowsPop('Total assets', [
    ...S.accounts.map(a => ({t: a.name, s: `${a.positions} investments${a.cash ? ', cash ' + fmtV(a.cash, '€') : ''}`, v: a.value + a.cash, open: 'account:' + a.name})),
    {t: S.managed.name, s: 'Managed portfolio', v: S.managed.value, open: 'account:' + S.managed.name},
    ...S.savings.map(s => ({t: s.name, s: s.bank, v: s.value, open: 'page:cash'}))].sort((a, b) => b.v - a.v));
  if (kind === 'debts') return rowsPop('Debt', S.debts.map(d => ({t: d.name, s: d.expected_gift ? 'Expected to become a gift, not counted' : `${(d.rate_pct || 0).toFixed(2)}% interest`, v: d.balance, open: 'page:cash'})));
  if (kind === 'profit') return rowsPop('Investment profit', [...S.accounts.filter(a => a.profit != null).map(a => ({t: a.name, s: 'Since ' + (a.since || 'start'), v: a.profit, sign: true, open: 'account:' + a.name})),
    {t: S.managed.name, s: 'Since ' + fdate(S.managed.start_date), v: S.managed.profit, sign: true, open: 'account:' + S.managed.name}].sort((a, b) => b.v - a.v));
  return rowsPop('Savings & cash', S.savings.map(s => ({t: s.name, s: `${s.bank}${s.rate_pct ? ', ' + s.rate_pct.toFixed(2) + '%' : ''}`, v: s.value, open: 'page:cash'})).sort((a, b) => b.v - a.v));
}
function allocRows(name) {
  if (name === 'Savings & cash') return tileRows('savings');
  if (name === S.managed.name || name === 'Managed portfolio') return rowsPop(name, S.positions.filter(p => p.managed).map(p => ({t: p.name, s: p.category, v: p.value, open: 'holding:' + (p.isin || 'n:' + p.name.trim().toLowerCase())})).concat(S.positions.some(p => p.managed) ? [] : [{t: S.managed.name, s: 'Holdings not imported yet', v: S.managed.value, open: 'account:' + S.managed.name}]));
  const acct = S.accounts.find(a => a.name === name);
  const list = S.positions.filter(p => acct ? p.account === name : (!p.managed && TYPE_OF(p.category) === name));
  return rowsPop(name, list.map(p => ({t: p.name, s: `${p.category}, ${p.account}`, v: p.value, open: 'holding:' + (p.isin || 'n:' + p.name.trim().toLowerCase())})).sort((a, b) => b.v - a.v));
}

function renderPins() {
  // answers pinned from the chat, without their buttons
  const slot = $('#pinsSlot'); if (!slot) return;
  const pins = UIS.pins || [];
  slot.innerHTML = pins.length ? `<div class="pins"><div class="pins-h muted small">Pinned answers</div><div class="grid g2">${pins.map(p => `<section class="card pin"><div class="card-head"><h2>${esc(p.title)}</h2><button type="button" class="x-btn" data-unpin="${p.id}" title="Unpin" aria-label="Unpin">×</button></div><div class="msg-like">${md(p.content.replace(/```actions[\s\S]*?```/g, ''))}</div><div class="muted small">Pinned ${ago(p.created)}</div></section>`).join('')}</div></div>` : '';
  for (const card of $$('.pin', slot)) { const t = $('.c-title', card); if (t && t.textContent === $('h2', card).textContent) t.remove(); }
  $$('[data-unpin]', slot).forEach(b => b.onclick = () => uiPost({action: 'pin-delete', id: b.dataset.unpin}, 'Unpinned').then(renderPins));
}

/* ---------- Claude's briefing ---------- */
function briefHtml() {
  const b = HOME.brief;
  const head = `<div class="brief-head"><span class="claude-mark">${CLAUDE_ICON}</span><b>Claude</b>${b && b.time ? `<span class="ago">${b.updating ? 'thinking' : ago(b.time)}</span>` : ''}
    <button type="button" class="icon-btn sm" id="briefRefresh" title="Look again" aria-label="Look again"><svg viewBox="0 0 24 24"><path d="M20 11a8 8 0 10-2.3 5.7M20 4v7h-7"/></svg></button></div>`;
  if (!b) return head + '<div class="skel-line"></div><div class="skel-line short"></div>';
  if (!b.items || !b.items.length) return head + '<p class="brief-line muted">Nothing stands out right now. Ask me anything below.</p>';
  return head + `<ul class="brief-lines">${b.items.map(it => `<li><button type="button" class="brief-line" data-link="${esc(JSON.stringify(it.link))}">${esc(it.text)}</button></li>`).join('')}</ul>
    <button type="button" class="linkish brief-ask" id="briefAsk">Ask about this →</button>`;
}
async function loadBrief(force) {
  if (UIS.prefs && UIS.prefs.briefing === 'off') return;
  if (!force && HOME.brief && Date.now() - HOME.briefAt < 5 * 60e3 && !HOME.brief.updating) return wireBrief();
  try {
    HOME.brief = force ? await post('/api/briefing', {}) : await (await fetch('/api/briefing', {cache: 'no-store'})).json();
    HOME.briefAt = Date.now();
  } catch { HOME.brief = {items: []}; }
  if ($('#brief')) { $('#brief').innerHTML = briefHtml(); wireBrief(); }
  if (HOME.brief.updating) setTimeout(() => { HOME.brief.updating = false; HOME.briefAt = 0; if (view === 'overview') loadBrief(); }, 9000);
}
function wireBrief() {
  if (!$('#brief')) return;
  if (!$('#brief .brief-head')) $('#brief').innerHTML = briefHtml();
  $('#briefRefresh').onclick = () => { HOME.brief = null; $('#brief').innerHTML = briefHtml(); loadBrief(true); };
  if ($('#briefAsk')) $('#briefAsk').onclick = () => openChat({ctx: {title: "Claude's briefing", text: HOME.brief.items.map(i => i.text).join(' ')}});
}

/* ---------- this month ---------- */
async function fillMonth() {
  try { await ensureSpending(); } catch { return; }
  const box = $('#monthStrip');
  if (!box || !SP.d) return;
  if (!SP.d.transactions.length) { $('.mstrip', box).innerHTML = `<div class="empty" style="grid-column:1/-1">Import a bank export to see your month here. <a href="#import">Import</a></div>`; return; }
  const now = new Date(), m0 = isoD(now).slice(0, 7), day = now.getDate(), dim = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  const rows = spRows().filter(r => r.date.startsWith(m0));
  const T = totals(rows);
  const months = [...new Set(spRows().map(r => r.date.slice(0, 7)))].filter(x => x < m0).sort().slice(-6);
  const usual = months.length ? months.reduce((s, mm) => s + totals(spRows().filter(r => r.date.startsWith(mm) && +r.date.slice(8) <= day)).spent, 0) / months.length : null;
  const invested = rows.filter(r => r.category === 'saving-investing' && r.amount < 0).reduce((s, r) => s - r.amount, 0);
  const plans = (S.savings_plans || []).filter(p => p.active).reduce((s, p) => s + p.per_month, 0);
  const bar = (share, tone = '') => `<div class="ms-bar"><i class="${tone}" style="width:${Math.max(2, Math.min(100, share * 100)).toFixed(0)}%"></i></div>`;
  const pace = day / dim;
  const items = [
    {k: 'Spent', v: eur(T.spent), bar: bar(usual ? T.spent / (usual / pace || 1) : pace, usual && T.spent > usual * 1.1 ? 'warn' : ''),
     s: usual == null ? `${day} of ${dim} days` : Math.abs(T.spent - usual) < 25 ? 'about usual so far' : `${eur(Math.abs(T.spent - usual))} ${T.spent > usual ? 'more' : 'less'} than usual so far`,
     link: {kind: 'payments', title: 'Spent this month', filter: {month: m0, kind: 'expense'}}},
    {k: 'Income', v: eur(T.income), bar: bar(T.spent > 0 ? Math.min(1, T.income / T.spent) : T.income ? 1 : 0, 'good'),
     s: T.income ? `${eur(Math.abs(T.income - T.spent))} ${T.income >= T.spent ? 'more' : 'less'} than you spent` : 'nothing came in yet', link: {kind: 'payments', title: 'Income this month', filter: {month: m0, kind: 'income'}}},
    {k: 'Saved', v: sgn(T.saved), bar: bar(T.income > 0 ? Math.max(0, T.saved) / T.income : 0, T.saved < 0 ? 'bad' : 'good'),
     s: T.income > 0 ? `${Math.max(0, T.rate).toFixed(0)}% of income` : 'no income yet this month', link: {kind: 'payments', title: 'Income & spending this month', filter: {month: m0, kind: 'flow'}}},
    {k: 'Invested', v: eur(invested), bar: bar(plans ? invested / plans : invested ? 1 : 0, 'good'),
     s: plans ? `${eur(plans)} a month runs in savings plans` : 'moved to saving and investing', link: {kind: 'payments', title: 'Saving and investing this month', filter: {month: m0, category: 'saving-investing'}}},
  ];
  $('#msWhen').textContent = `${MONTHS[now.getMonth()]} ${now.getFullYear()}, day ${day} of ${dim}`;
  $('.mstrip', box).innerHTML = items.map(it => `<button type="button" class="ms" data-link="${esc(JSON.stringify(it.link))}"><span class="k">${it.k}</span><span class="v">${it.v}</span>${it.bar}<span class="muted small">${it.s}</span></button>`).join('');
}

/* ---------- net worth charts ---------- */
function nwEvents(from, to) {
  const ev = [];
  const h = S.history || [];
  for (let i = 1; i < h.length; i++) {
    const a = (h[i - 1].self_directed || 0) + (h[i - 1].managed || 0), b = (h[i].self_directed || 0) + (h[i].managed || 0);
    if (a > 1000 && (b / a - 1) <= -0.025) ev.push({t: tOf(h[i].date), label: `Markets down ${((1 - b / a) * 100).toFixed(1)}% that day`, w: (a - b)});
  }
  for (const im of HOME.imports || []) ev.push({t: tOf(im.date.slice(0, 10)), label: `Imported ${im.files.slice(0, 2).join(', ')}${im.files.length > 2 ? ' and more' : ''}`, w: 50});
  if (SP.d) {
    for (const im of SP.d.imports || []) ev.push({t: tOf(im.date), label: `Imported ${im.file}, ${im.added} payments`, w: 40});
    const exp = spRows().filter(r => kindOf(r) === 'expense' && r.amount <= -500).sort((a, b) => a.amount - b.amount).slice(0, 10);
    for (const r of exp) ev.push({t: tOf(r.date), label: `${r.merchant}, ${fmtV(-r.amount, '€')}`, w: -r.amount});
    const sal = {};
    for (const r of spRows()) if (r.category === 'salary') sal[r.date.slice(0, 7)] = (sal[r.date.slice(0, 7)] || 0) + r.amount;
    const ms = Object.keys(sal).sort();
    for (let i = 1; i < ms.length - 1; i++) {
      const a = sal[ms[i - 1]], b = sal[ms[i]], c = sal[ms[i + 1]];
      if (a > 500 && Math.abs(b / a - 1) > 0.03 && Math.abs(c / b - 1) < 0.03) ev.push({t: tOf(ms[i] + '-25'), label: `Salary ${b > a ? 'up' : 'down'} to ${fmtV(b, '€')} a month`, w: 1000});
    }
  }
  const lo = tOf(from), hi = tOf(to.startsWith('9999') ? today() : to);
  return ev.filter(e => e.t >= lo && e.t <= hi).sort((a, b) => b.w - a.w).slice(0, 14);
}
async function drawNetWorth(body = $('#nwBody')) {
  if (!body) return;
  const again = () => { if (view === 'overview' && document.body.contains(body)) drawNetWorth(body); };
  if (HOME.imports === null) { HOME.imports = []; fetch('/api/imports').then(r => r.json()).then(x => { HOME.imports = x; again(); }).catch(() => {}); }
  if (!SP.d) ensureSpending().then(again).catch(() => {});
  const r = rangeFor();
  const h = historyIn(r.from, r.to);
  if (HOME.nwView === 'month') return drawWaterfall(body);
  if (h.length < 2) {
    body.innerHTML = `<div class="empty">${h.length ? `Today: ${eur(h[0].net_worth)}. The chart fills in as the app runs each day.` : 'No history in this period yet.'}</div>`;
    return;
  }
  const P = d => tOf(d.date);
  if (HOME.nwView === 'line') {
    timeChart(body, {series: [{name: 'Net worth', pts: h.map(x => [P(x), x.net_worth]), area: !HOME.nwPct}], pct: HOME.nwPct ? 'index' : null,
      markers: HOME.nwPct ? [] : nwEvents(r.from, r.to), select: true, sync: true, height: 260, label: 'Net worth over time'});
  } else {
    // the split by type is recorded from the day this version first ran; before that, today's first known mix is used
    const firstSplit = h.find(x => x.etf != null);
    const mix = firstSplit ? (() => { const inv = (firstSplit.etf + firstSplit.stocks + firstSplit.bonds + firstSplit.other_inv) || 1; return {etf: firstSplit.etf / inv, stocks: firstSplit.stocks / inv, bonds: firstSplit.bonds / inv, other_inv: firstSplit.other_inv / inv}; })() : {etf: 1, stocks: 0, bonds: 0, other_inv: 0};
    const part = (x, k) => x.etf != null ? x[k] : x.self_directed * mix[k];
    const layers = [['Cash and savings', x => x.cash != null ? x.cash : x.savings], ['ETFs and funds', x => part(x, 'etf')], ['Stocks', x => part(x, 'stocks')],
      ['Bonds', x => part(x, 'bonds')], ['Other investments', x => part(x, 'other_inv')], ['Managed portfolio', x => x.managed], ['Debt', x => -(x.debt || 0)]];
    const series = layers.map(([name, f], i) => ({name, color: name === 'Debt' ? 'var(--loss)' : col(i), neg: name === 'Debt', pts: h.map(x => [P(x), f(x) || 0])}))
      .filter(s => s.pts.some(p => Math.abs(p[1]) > 1));
    const est = firstSplit ? h.filter(x => x.date < firstSplit.date).length : h.length;
    timeChart(body, {series, stacked: true, pct: HOME.nwPct ? 'share' : null, select: !HOME.nwPct, sync: true, height: 280, label: 'Net worth by type',
      legendExtra: est > 1 ? `<span class="muted">Split by type estimated before ${firstSplit ? fdate(firstSplit.date) : 'today'}</span>` : ''});
  }
  if ($('#nwCard')) $('#nwCard').renderFull = el => { const d = document.createElement('div'); el.appendChild(d); drawNetWorth(d); };
}
function monthWaterfall(m) {
  const h = S.history || [];
  const start = [...h].reverse().find(x => x.date < m + '-01') || h.find(x => x.date.startsWith(m));
  const inMonth = h.filter(x => x.date.startsWith(m)), end = inMonth[inMonth.length - 1];
  if (!start || !end || start === end) return null;
  const days = (tOf(end.date) - tOf(start.date)) / 864e5;
  const rows = SP.d ? spRows().filter(r => r.date > start.date && r.date <= end.date) : [];
  const T = totals(rows);
  const interest = S.savings.reduce((s, x) => s + x.value * (x.rate_pct || 0) / 100 * days / 365, 0);
  const debtInt = S.debts.filter(d => !d.expected_gift).reduce((s, d) => s + d.balance * (d.rate_pct || 0) / 100 * days / 365, 0);
  const change = end.net_worth - start.net_worth, markets = change - (T.income - T.spent + interest - debtInt);
  return {start, end, steps: [{label: `Start ${fdate(start.date).replace(/ \d{4}$/, '')}`, v: start.net_worth, total: true}, {label: 'Income', v: T.income},
    {label: 'Markets and other', v: markets}, {label: 'Interest earned', v: interest}, {label: 'Spending', v: -T.spent},
    {label: 'Debt interest', v: -debtInt}, {label: `End ${fdate(end.date).replace(/ \d{4}$/, '')}`, v: end.net_worth, total: true}]};
}
function drawWaterfall(body) {
  const months = [...new Set((S.history || []).map(x => x.date.slice(0, 7)))].sort();
  if (!HOME.wfMonth || !months.includes(HOME.wfMonth)) HOME.wfMonth = months[months.length - 1];
  const i = months.indexOf(HOME.wfMonth), w = HOME.wfMonth && monthWaterfall(HOME.wfMonth);
  const W = Math.max(320, body.clientWidth || 640);
  body.innerHTML = `<div class="wf-nav"><button type="button" class="icon-btn sm" id="wfPrev" ${i > 0 ? '' : 'disabled'} aria-label="Previous month">${ICON.back}</button>
      <b>${HOME.wfMonth ? fdate(HOME.wfMonth) : ''}</b><button type="button" class="icon-btn sm flip" id="wfNext" ${i < months.length - 1 ? '' : 'disabled'} aria-label="Next month">${ICON.back}</button>
      ${w ? `<span class="muted small">${sgn(w.end.net_worth - w.start.net_worth)} from ${fdate(w.start.date)} to ${fdate(w.end.date)}</span>` : ''}</div>
    ${w ? waterfall(w.steps, W) + '<p class="muted small" style="margin:6px 0 0">Markets and other is the rest of the change: price moves, and money moving in ways the app does not see.</p>' : '<div class="empty">Not enough history for this month yet. Each day the app runs adds a point.</div>'}`;
  $('#wfPrev', body).onclick = () => { HOME.wfMonth = months[i - 1]; drawWaterfall(body); };
  $('#wfNext', body).onclick = () => { HOME.wfMonth = months[i + 1]; drawWaterfall(body); };
}
