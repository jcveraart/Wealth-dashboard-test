'use strict';
/* Savings & debt, history, plan, taxes, advice, import and settings. Uses app.js, charts.js and shell.js. */

/* ---------- savings and debt ---------- */
const DEBT = {extra: {}};
function amortize(bal, ratePct, pay, extra = 0, max = 600) {
  // month by month: interest added, payment taken off
  const r = ratePct / 100 / 12, pts = [[Date.now(), bal]];
  let months = 0, interest = 0;
  while (bal > 0.5 && months < max) {
    const i = bal * r; interest += i; bal = Math.max(0, bal + i - pay - extra); months++;
    pts.push([Date.now() + months * 30.4375 * 864e5, bal]);
    if (pay + extra <= i + 0.01) return {months: Infinity, interest: Infinity, pts, never: true};
  }
  return {months, interest, pts, never: false};
}
const inMonths = n => n === Infinity ? 'never' : n < 12 ? `${n} month${n === 1 ? '' : 's'}` : `${(n / 12).toFixed(n % 12 ? 1 : 0)} years`;
function cash() {
  // money you can reach and money you owe: cash accounts, the buffer and pots, and debts with their payoff.
  // Savings you count as investments live on the Investments page; this page still lists them so you can switch.
  const t = S.totals;
  const cashAcc = S.savings.filter(s => !s.invest), invAcc = S.savings.filter(s => s.invest);
  const cashTotal = cashAcc.reduce((s, x) => s + x.value, 0);
  const earn = cashAcc.reduce((s, x) => s + x.value * (x.rate_pct || 0) / 100, 0);
  const real = S.debts.filter(d => !d.expected_gift);
  const pay = real.reduce((s, d) => s + d.balance * (d.rate_pct || 0) / 100, 0);
  const pots = S.pots || [], inPots = pots.reduce((s, p) => s + (p.saved_eur || 0), 0);
  const spend = S.spend_month, months = spend ? cashTotal / spend : null, want = (S.profile || {}).buffer_months || 4;
  const flex = cashAcc.filter(s => !s.maturity && s.rate_pct), best = flex.length ? flex.reduce((a, b) => b.rate_pct > a.rate_pct ? b : a) : null;
  const cmp = (S.profile || {}).compare_rate_pct, top = Math.max(best ? best.rate_pct : 0, cmp || 0);
  const lows = cashAcc.filter(s => !s.maturity && (s.rate_pct || 0) < top - 0.25 && s.value > 500);
  const row = (s, i) => `<tr data-ctx="account:${esc(s.name)}"><td><a class="nm h-link" href="#account/${encodeURIComponent(s.name)}">${esc(s.name)}</a><div class="meta">${esc(s.bank || '')}${s.maturity ? `, until ${fdate(s.maturity)}` : ''}</div></td>
    <td class="num">${s.rate_pct ? s.rate_pct.toFixed(2) + '%' : '<span class="muted">none</span>'}</td><td class="num"><b>${eur(s.value)}</b></td>
    <td class="num">${seg('cnt' + i, [['cash', 'Cash'], ['inv', 'Investment']], s.invest ? 'inv' : 'cash')}</td>
    <td class="num"><button class="btn ghost sm" data-sav="${i}">Edit</button></td></tr>`;
  $('#view').innerHTML = `<div class="stack-y">
    <div class="grid g4">
      <div class="card tile"><div class="k">Cash</div><div class="v" data-count="${cashTotal}">${eur(cashTotal)}</div><div class="n">${invAcc.length ? `${eur(t.invested_savings)} more counted as investments` : 'in savings and current accounts'}</div></div>
      <div class="card tile"><div class="k">Buffer</div><div class="v">${months == null ? '<span class="muted">n/a</span>' : months.toFixed(1) + ' months'}</div><div class="n">${spend ? `of spending (${eur(spend)} a month), aim ${want}` : 'Import bank exports to see this'}</div></div>
      <div class="card tile"><div class="k">Debt</div><div class="v" data-count="${t.debt}">${eur(t.debt)}</div><div class="n">${real.length} counted</div></div>
      <div class="card tile"><div class="k">Interest a year</div><div class="v">${sgn(earn - pay)}</div><div class="n">${eur(earn)} in, ${eur(pay)} out</div></div>
    </div>
    <section class="card" data-card="cash-accounts">
      <div class="card-head"><div><h2>Accounts</h2><p class="sub">Choose per account whether it is cash or an investment. Investments show on the <a href="#holdings">Investments</a> page.</p></div><button class="btn" id="addSav">Add account</button></div>
      <div class="table-wrap"><table class="compact">
        <thead><tr><th>Account</th><th class="num">Rate</th><th class="num">Balance</th><th class="num">Counts as</th><th></th></tr></thead>
        <tbody>${S.savings.map((s, i) => row(s, i)).join('')}</tbody></table></div>
      <div class="muted small market-line" id="marketLine"></div>
      ${lows.length ? `<div class="hint">${lows.map(s => `<b>${esc(s.name)}</b> earns ${(s.rate_pct || 0).toFixed(2)}%. At ${top.toFixed(2)}% it would bring <span class="amt">${eur(s.value * (top - (s.rate_pct || 0)) / 100)}</span> a year more.`).join(' ')}</div>` : ''}
    </section>
    <div class="grid g2">
      <section class="card" data-card="cash-buffer"><div class="card-head"><div><h2>Buffer and pots</h2><p class="sub">${pots.length ? `${eur(inPots)} set aside, ${eur(Math.max(0, cashTotal - inPots))} free` : 'Set money aside for a holiday, a car or a rainy day'}</p></div><button class="btn ghost" id="potAdd">Add pot</button></div>
        ${spend ? `<div class="pot"><div class="pot-top"><span><b>Emergency buffer</b> <span class="muted small">${want} months of spending</span></span><span class="num"><b class="amt">${eur(Math.min(cashTotal, spend * want))}</b> <span class="muted">of ${eur(spend * want)}</span></span></div>
          <div class="bud-bar"><i class="${cashTotal >= spend * want ? 'good' : ''}" style="width:${Math.min(100, cashTotal / (spend * want) * 100)}%"></i></div></div>` : ''}
        ${pots.map((p, i) => { const share = p.target_eur ? (p.saved_eur || 0) / p.target_eur : 1; return `<div class="pot"><div class="pot-top"><button type="button" class="linkish pot-name" data-pot="${i}">${esc(p.name)}</button><span class="num"><b class="amt">${eur(p.saved_eur || 0)}</b>${p.target_eur ? ` <span class="muted">of ${eur(p.target_eur)}</span>` : ''}</span></div>
          ${p.target_eur ? `<div class="bud-bar"><i class="${share >= 1 ? 'good' : ''}" style="width:${Math.min(100, share * 100)}%"></i></div>` : ''}</div>`; }).join('')}
      </section>
      <section class="card" data-card="cash-debts"><div class="card-head"><h2>Debts</h2><button class="btn ghost" id="addDebt">Add debt</button></div>
        ${S.debts.map((d, i) => `<div class="list-row"><div><b>${esc(d.name)}</b><div class="muted small">${(d.rate_pct || 0).toFixed(2)}%${d.monthly_payment_eur ? `, ${eur(d.monthly_payment_eur)} a month` : ''}${d.expected_gift ? ', expected to become a gift, not counted' : ''}</div></div>
          <div class="num"><b class="${d.expected_gift ? 'muted' : ''}">${eur(d.balance)}</b> <button class="linkish small" data-debt="${i}">Edit</button></div></div>`).join('') || '<div class="empty">No debts. Nice.</div>'}
      </section>
    </div>
    ${real.map((d, i) => `<section class="card" data-card="debt${i}"><div class="card-head"><h2>Paying off ${esc(d.name)}</h2><span class="muted small" id="dsum${i}"></span></div>
      ${d.monthly_payment_eur ? `<div class="debt-ctl"><span class="muted small">Pay extra per month</span><input type="range" min="0" max="${Math.max(200, Math.round(d.monthly_payment_eur * 3 / 50) * 50)}" step="10" value="${DEBT.extra[d.name] || 0}" data-extra="${i}" aria-label="Extra per month"><b data-extrav="${i}"></b></div><div id="dchart${i}"></div>`
        : `<div class="empty" style="padding:14px 0">Set the monthly payment to see when it is paid off. <button class="linkish" data-debt="${S.debts.indexOf(d)}">Set it</button></div>`}</section>`).join('')}
  </div>`;
  loadEcon().then(E => {
    const box = $('#marketLine'); if (!box || !E) return;
    const bits = [E.ecb_rate != null ? `ECB rate ${E.ecb_rate.toFixed(2)}%` : '', E.savings_nl != null ? `${E.savings_nl_area === 'Netherlands' ? 'Dutch banks' : 'Banks in the euro area'} pay ${E.savings_nl.toFixed(2)}% on average` : '',
      E.inflation_nl != null ? `inflation ${E.inflation_nl.toFixed(1)}%` : '', E.bond2 != null ? `2 year euro government bonds ${E.bond2.toFixed(2)}%` : ''].filter(Boolean);
    if (bits.length) box.textContent = bits.join(' · ') + '. Source: ECB.';
    // an account that earns less than prices rise loses value; a quiet marker says so
    if (E.inflation_nl != null) cashAcc.forEach(x => { if (x.rate_pct && x.rate_pct < E.inflation_nl && x.value > 1000) { const r = $(`tr[data-ctx="account:${CSS.escape(x.name)}"] .meta`); if (r) r.insertAdjacentHTML('beforeend', ' <span class="tag warn-tag" title="Earns less than prices rise">below inflation</span>'); } });
  });
  S.savings.forEach((s, i) => onSeg('cnt' + i, v => edit({section: 'savings', index: i, fields: {invest: v === 'inv'}}, v === 'inv' ? `${s.name} now counts as an investment` : `${s.name} counts as cash`)));
  const savFields = s => [
    {k: 'name', label: 'Name', type: 'text', value: s.name}, {k: 'bank', label: 'Bank', type: 'text', value: s.bank},
    {k: 'principal_eur', label: 'Balance (€)', type: 'number', value: s.principal_eur}, {k: 'snapshot_date', label: 'Balance date', type: 'date', value: s.snapshot_date || today()},
    {k: 'accrued_at_snapshot_eur', label: 'Interest built up on that date (€)', type: 'number', value: s.accrued_at_snapshot_eur || 0},
    {k: 'rate_pct', label: 'Interest rate (%)', type: 'number', value: s.rate_pct ?? ''},
    {k: 'maturity', label: 'Matures on (leave empty if flexible)', type: 'date', value: s.maturity && s.maturity.length === 10 ? s.maturity : ''},
    {k: 'kind', label: 'What kind of account', type: 'select', value: (S.savings.find(x => x.name === s.name) || {}).kind || '',
     options: [['', 'Let the app decide'], ['payment', 'Payment account, day to day money'], ['savings', 'Savings account'], ['deposit', 'Fixed deposit']]}];
  $('#addSav').onclick = () => form('Add savings account', savFields({}), v => edit({section: 'savings', action: 'add', fields: v}, 'Account added'));
  $$('[data-sav]').forEach(b => b.onclick = () => { const i = +b.dataset.sav; form('Edit ' + S.savings[i].name, savFields(S.savings[i]), v => edit({section: 'savings', index: i, fields: v}), () => edit({section: 'savings', action: 'delete', index: i}, 'Account removed')); });
  const debtFields = d => [
    {k: 'name', label: 'Name', type: 'text', value: d.name}, {k: 'balance_eur', label: 'Balance including interest (€)', type: 'number', value: d.balance_eur},
    {k: 'snapshot_date', label: 'Balance date', type: 'date', value: d.snapshot_date || today()}, {k: 'rate_pct', label: 'Interest rate (%)', type: 'number', value: d.rate_pct ?? 0},
    {k: 'monthly_payment_eur', label: 'Monthly payment (€), if you are repaying', type: 'number', value: d.monthly_payment_eur ?? ''},
    {k: 'expected_gift', label: 'Expected to become a gift (not counted)', type: 'checkbox', value: !!d.expected_gift}];
  $('#addDebt').onclick = () => form('Add debt', debtFields({}), v => edit({section: 'debts', action: 'add', fields: v}, 'Debt added'));
  $$('[data-debt]').forEach(b => b.onclick = () => { const i = +b.dataset.debt; form('Edit ' + S.debts[i].name, debtFields(S.debts[i]), v => edit({section: 'debts', index: i, fields: v}), () => edit({section: 'debts', action: 'delete', index: i}, 'Debt removed')); });
  const potFields = p => [{k: 'name', label: 'Name, for example Holiday or Buffer', type: 'text', value: p.name || ''}, {k: 'saved_eur', label: 'Set aside now (€)', type: 'number', value: p.saved_eur ?? 0},
    {k: 'target_eur', label: 'Target (€), optional', type: 'number', value: p.target_eur ?? ''}, {k: 'account', label: 'Which account it sits in (optional)', type: 'text', value: p.account || ''}];
  $('#potAdd').onclick = () => form('Add pot', potFields({}), v => edit({section: 'pots', action: 'add', fields: v}, 'Pot added'));
  $$('[data-pot]').forEach(b => b.onclick = () => { const i = +b.dataset.pot; form('Edit ' + pots[i].name, potFields(pots[i]), v => edit({section: 'pots', index: i, fields: v}), () => edit({section: 'pots', action: 'delete', index: i}, 'Pot removed')); });
  real.forEach((d, i) => { if (d.monthly_payment_eur) drawDebt(d, i); });
  $$('[data-extra]').forEach(r => r.oninput = () => { const d = real[+r.dataset.extra]; DEBT.extra[d.name] = +r.value; drawDebt(d, +r.dataset.extra); });
  countUp();
}
function drawDebt(d, i) {
  const extra = DEBT.extra[d.name] || 0, base = amortize(d.balance, d.rate_pct || 0, d.monthly_payment_eur), fast = amortize(d.balance, d.rate_pct || 0, d.monthly_payment_eur, extra);
  const when = n => n === Infinity ? 'never' : fdate(isoD(new Date(Date.now() + n * 30.4375 * 864e5)).slice(0, 7));
  $(`[data-extrav="${i}"]`).innerHTML = `<span class="amt">€${extra}</span>`;
  $(`#dsum${i}`).innerHTML = base.never ? '<span class="neg">The payment does not cover the interest</span>' : extra
    ? `Paid off ${when(fast.months)} instead of ${when(base.months)}: ${inMonths(base.months - fast.months)} sooner, <span class="pos amt">${eur(base.interest - fast.interest)}</span> less interest`
    : `Paid off ${when(base.months)}, <span class="amt">${eur(base.interest)}</span> interest to go`;
  timeChart($(`#dchart${i}`), {series: [{name: 'As planned', pts: base.pts.filter((_, k) => k % 3 === 0 || k === base.pts.length - 1), color: 'var(--muted)'},
    ...(extra ? [{name: `With €${extra} extra`, pts: fast.pts.filter((_, k) => k % 3 === 0 || k === fast.pts.length - 1), color: 'var(--s1)', area: true}] : [])], height: 200, zero: true, label: 'Debt balance', xfmt: 'date'});
}

/* ---------- history ---------- */
function liveValueOf(name) {
  const a = S.accounts.find(x => x.name === name); if (a) return a.value + a.cash;
  if (name === S.managed.name) return S.managed.value;
  const s = S.savings.find(x => x.name === name); if (s) return s.value;
  return null;
}
function yearFacts(y) {
  const Y = String(y), h = (S.history || []).filter(x => x.date.startsWith(Y));
  const ah = (S.account_history || []).filter(r => r.date.startsWith(Y));
  const prevEnd = (S.account_history || []).filter(r => r.date.startsWith(String(y - 1)));
  // from the daily history when the app ran that year; otherwise year end statements, comparing the same accounts only
  const lastBy = rows => { const m = {}; for (const r of [...rows].sort((a, b) => a.date.localeCompare(b.date))) m[r.account] = r.value_eur; return m; };
  const A = lastBy(prevEnd), B = lastBy(ah), both = Object.keys(B).filter(k => k in A);
  const sum = (m, ks) => ks.reduce((s, k) => s + m[k], 0);
  let start = null, end = null;
  if (h.length) { start = h[0].net_worth; end = h[h.length - 1].net_worth; }
  else if (both.length) { start = sum(A, both); end = sum(B, both); }
  else if (Object.keys(B).length) end = sum(B, Object.keys(B));
  const f = {year: y, start, end, partial: h.length && h[0].date > `${Y}-01-07`};
  if (SP.d) {
    const rows = SP.rows.filter(t => t.date.startsWith(Y)), T = totals(rows);
    Object.assign(f, {income: T.income, spent: T.spent, saved: T.saved, rate: T.rate, n: rows.length});
    const exp = rows.filter(t => kindOf(t) === 'expense');
    f.biggest = exp.sort((a, b) => a.amount - b.amount)[0] || null;
    f.countries = [...new Set(rows.map(t => t.country).filter(c => c && c !== SP.home))];
    const g = {}; for (const t of exp) g[t.category || ''] = (g[t.category || ''] || 0) - t.amount;
    f.cats = Object.entries(g).sort((a, b) => b[1] - a[1]);
    const mo = {}; for (const t of exp) mo[t.date.slice(0, 7)] = (mo[t.date.slice(0, 7)] || 0) - t.amount;
    f.busiest = Object.entries(mo).sort((a, b) => b[1] - a[1])[0] || null;
  }
  const flows = (S.yearly_flows || []).filter(r => r.year === y);
  f.result = flows.some(r => r.profit_eur != null) ? flows.reduce((s, r) => s + (r.profit_eur || 0), 0) : null;
  f.byAccount = flows.filter(r => r.profit_eur != null).map(r => [r.account, r.profit_eur]);
  return f;
}
function historyPage() {
  // how your wealth developed: the big line first, then each year in plain numbers, then every trade
  const AH = S.account_history || [], YF = S.yearly_flows || [], H = (S.history || []).map(h => ({...h, nw: +h.net_worth}));
  const nowYear = new Date().getFullYear();
  // year end totals from statements, for the years before the daily record
  const yearEnds = {};
  for (const r of AH) { const y = r.date.slice(0, 4); (yearEnds[y] = yearEnds[y] || {})[r.account] = r.value_eur; }
  const firstDaily = H.length ? H[0].date : '9999';
  const early = Object.entries(yearEnds).filter(([y]) => `${y}-12-31` < firstDaily).map(([y, m]) => [tOf(`${y}-12-31`), Object.values(m).reduce((s, v) => s + v, 0)]);
  const line = [...early, ...H.map(h => [tOf(h.date), h.nw])].sort((a, b) => a[0] - b[0]);
  const years = [...new Set([...Object.keys(yearEnds).map(Number), ...H.map(h => +h.date.slice(0, 4)), ...YF.map(r => r.year)])].filter(y => y <= nowYear).sort((a, b) => b - a);
  const facts = years.map(yearFacts);
  const now = S.totals.net_worth, first = line[0];
  const since = first ? now - first[1] : null;
  const spanY = first ? (Date.now() - first[0]) / 31557600000 : 0;
  const cagr = first && first[1] > 0 && spanY >= 1 ? (Math.pow(now / first[1], 1 / spanY) - 1) * 100 : null;
  const changes = facts.filter(f => f.start != null && f.end != null).map(f => [f.year, f.end - f.start]);
  const best = changes.length ? changes.reduce((a, b) => b[1] > a[1] ? b : a) : null;
  const trades = S.positions.flatMap(p => (p.trades || []).map(t => ({...t, name: p.name, account: p.managed ? S.managed.name : p.account, id: posId(p)})))
    .sort((a, b) => b.date.localeCompare(a.date));
  HIS.view = HIS.view || 'net';
  $('#view').innerHTML = `<div class="stack-y" id="hist">
    <div class="grid g4">
      <div class="card tile"><div class="k">Net worth now</div><div class="v" data-count="${now}">${eur(now)}</div><div class="n">${first ? `from ${eur(first[1])} on ${fdate(isoD(new Date(first[0])))}` : ''}</div></div>
      <div class="card tile"><div class="k">Grown since</div><div class="v">${since == null ? '<span class="muted">n/a</span>' : sgn(since)}</div><div class="n">${since != null && first[1] > 0 ? pct(since / first[1] * 100) + ' in total' : ''}</div></div>
      <div class="card tile"><div class="k">Per year on average</div><div class="v">${cagr == null ? '<span class="muted">n/a</span>' : pct(cagr, 1)}</div><div class="n" id="realGrowth">${cagr == null ? 'needs a year of history' : 'growth of net worth, everything included'}</div></div>
      <div class="card tile"><div class="k">Best year</div><div class="v">${best ? best[0] : '<span class="muted">n/a</span>'}</div><div class="n">${best ? sgn(best[1]) + ' net worth' : ''}</div></div>
    </div>
    <section class="card" data-card="hist-main"><div class="card-head"><h2>${HIS.view === 'net' ? 'Net worth over time' : 'What it is made of'}</h2>
      ${seg('hisView', [['net', 'Net worth'], ['parts', 'By part']], HIS.view)}</div><div id="hisMain"></div><div class="muted small" id="hisNote"></div></section>
    <div class="grid g2">
      <section class="card" data-card="hist-change"><div class="card-head"><h2>Change per year</h2><span class="muted small">Split into investment result and the rest</span></div><div id="hisChange"></div></section>
      <section class="card" data-card="hist-accounts"><div class="card-head"><h2>Per account, at year end</h2></div><div id="hisAccts"></div></section>
    </div>
    <section class="card" data-card="hist-years"><div class="card-head"><div><h2>Year by year</h2><p class="sub">Net worth at the start and end of each year, and where the change came from</p></div></div>
      <div class="table-wrap"><table class="compact year-table"><thead><tr><th>Year</th>
        <th class="num" title="Net worth on the first day of the year">Start</th><th class="num" title="Net worth on the last day of the year, or today">End</th>
        <th class="num" title="End minus start">Change</th><th class="num" title="What your investments earned, from statements">Investment result</th>
        <th class="num" title="Income minus spending on your payment accounts">Saved from income</th><th></th></tr></thead>
      <tbody>${facts.map(f => { const ch = f.start != null && f.end != null ? f.end - f.start : null; return `<tr>
        <td><b>${f.year}</b>${f.year === nowYear ? ' <span class="tag">so far</span>' : ''}</td>
        <td class="num">${f.start == null ? '<span class="muted">·</span>' : eur(f.start)}</td><td class="num">${f.end == null ? '<span class="muted">·</span>' : eur(f.end)}</td>
        <td class="num">${ch == null ? '<span class="muted">·</span>' : `${sgn(ch)}${f.start > 0 ? ` <span class="dpct ${ch < 0 ? 'neg' : 'pos'}">(${ch < 0 ? '−' : '+'}${Math.abs(ch / f.start * 100).toFixed(1)}%)</span>` : ''}`}</td>
        <td class="num">${f.result == null ? '<span class="muted">·</span>' : sgn(f.result)}</td>
        <td class="num">${f.saved != null && f.n ? sgn(f.saved) : '<span class="muted">·</span>'}</td>
        <td class="num"><button type="button" class="linkish small" data-story="${f.year}">Review</button></td></tr>`; }).join('') || '<tr><td colspan="7" class="empty">No history yet.</td></tr>'}</tbody></table></div>
      <p class="muted small" style="margin:8px 0 0">A dot means it is not known for that year. Yearly statements and bank exports fill these in on the Import page.</p></section>
    <section class="card" data-card="hist-trades"><div class="card-head"><div><h2>Trades</h2><p class="sub" id="trSum"></p></div>
      <div class="controls" style="margin:0"><input type="search" id="trQ" placeholder="Search" value="${esc(HIS.q || '')}" aria-label="Search trades">
        <select id="trAcct" aria-label="Account"><option value="">All accounts</option>${[...new Set(trades.map(t => t.account))].map(a => `<option ${HIS.acct === a ? 'selected' : ''}>${esc(a)}</option>`).join('')}</select>
        <select id="trYear" aria-label="Year"><option value="">All years</option>${[...new Set(trades.map(t => t.date.slice(0, 4)))].map(y => `<option ${HIS.year === y ? 'selected' : ''}>${y}</option>`).join('')}</select>
        <span class="fchips">${[['', 'All'], ['buy', 'Buys'], ['sell', 'Sells'], ['dividend', 'Dividends']].map(([v, l]) => `<button type="button" data-trt="${v}" aria-pressed="${(HIS.type || '') === v}">${l}</button>`).join('')}</span></div></div>
      <div id="trChart"></div><div id="trList"></div></section>
    <div class="grid g2">
      <section class="card" data-card="hist-flows"><h2>Income & costs per year</h2><div id="hisFlows"></div></section>
      <section class="card" data-card="hist-recorded"><h2>Recorded values</h2><p class="sub">Values from statements and screenshots, the basis of the years before the daily record.</p>
        <div class="table-wrap capped-sm"><table class="compact"><tbody>${[...AH].sort((a, b) => b.date.localeCompare(a.date)).map(r => `<tr><td>${fdate(r.date)}</td><td>${esc(r.account)}<div class="meta">${esc(r.source || '')}</div></td><td class="num">${eur(r.value_eur)}</td></tr>`).join('') || '<tr><td class="empty">Nothing recorded yet.</td></tr>'}</tbody></table></div></section>
    </div>
  </div>`;
  onSeg('hisView', v => { HIS.view = v; historyPage(); });
  if (cagr != null) loadEcon().then(E => {
    // the same growth with rising prices taken off, from Dutch inflation over the same years
    const hist = (E && E.inflation_nl_history) || [], from = isoD(new Date(first[0])).slice(0, 7), months = hist.filter(([m]) => m >= from).map(([, v]) => v);
    if (months.length < 12 || !$('#realGrowth')) return;
    const infl = months.reduce((f, v) => f * Math.pow(1 + v / 100, 1 / 12), 1), perYear = Math.pow(infl, 1 / spanY) - 1;
    $('#realGrowth').innerHTML = `${pct(((1 + cagr / 100) / (1 + perYear) - 1) * 100, 1)} after inflation of ${(perYear * 100).toFixed(1)}% a year`;
  });
  $$('[data-story]').forEach(b => b.onclick = () => yearStory(+b.dataset.story));
  const W = Math.max(320, $('#hisMain').clientWidth || 900), half = Math.max(280, ($('#hisChange').clientWidth || 440));
  // the big chart
  if (line.length > 1) {
    if (HIS.view === 'net') timeChart($('#hisMain'), {series: [{name: 'Net worth', pts: line, color: 'var(--s1)', area: true}], select: true, height: 260, label: 'Net worth over time'});
    else {
      const share = S.totals.savings ? S.totals.invested_savings / S.totals.savings : 0;
      const parts = H.map(h => ({t: tOf(h.date), inv: (+h.self_directed || 0) + (+h.managed || 0) + (+h.savings || 0) * share, cash: (+h.savings || 0) * (1 - share), debt: -(+h.debt || 0)}));
      timeChart($('#hisMain'), {stacked: true, series: [{name: 'Investments', pts: parts.map(p => [p.t, p.inv]), color: 'var(--s1)'}, {name: 'Cash', pts: parts.map(p => [p.t, p.cash]), color: 'var(--s3)'},
        {name: 'Debt', pts: parts.map(p => [p.t, p.debt]), color: 'var(--s2)'}], height: 260, label: 'Net worth by part'});
    }
    $('#hisNote').textContent = first ? `${early.length ? 'Year end statements until ' + fdate(firstDaily) + ', then every day the app ran.' : 'Every day the app ran.'} Drag across the chart to read any stretch.` : '';
  } else $('#hisMain').innerHTML = '<div class="empty">Your net worth is recorded every day the app runs. Import yearly statements to fill in the years before.</div>';
  // change per year, split
  const cy = facts.filter(f => f.start != null && f.end != null).reverse();
  $('#hisChange').innerHTML = cy.length ? chartHtml({type: 'stacked', unit: '€', labels: cy.map(f => String(f.year)), series: [
    {name: 'Investment result', values: cy.map(f => Math.round(f.result || 0))}, {name: 'Saved and other', values: cy.map(f => Math.round(f.end - f.start - (f.result || 0)))}]}, half)
    : '<div class="empty">Needs a start and end value for at least one year.</div>';
  // per account, year ends
  const accts = [...new Set(AH.map(r => r.account))];
  const ys = Object.keys(yearEnds).sort(), cols = [...ys, 'Now'];
  const live = a => liveValueOf(a) ?? 0;
  let order = accts.sort((a, b) => live(b) - live(a));
  const fold = order.length > SERIES.length ? order.slice(SERIES.length - 1) : []; if (fold.length) order = order.slice(0, SERIES.length - 1);
  const at = (a, y) => y === 'Now' ? live(a) : (yearEnds[y] || {})[a] || 0;
  $('#hisAccts').innerHTML = accts.length ? chartHtml({type: 'stacked', unit: '€', labels: cols, series: [...order.map(a => ({name: a, values: cols.map(y => at(a, y))})),
    ...(fold.length ? [{name: 'Other', values: cols.map(y => fold.reduce((s, a) => s + at(a, y), 0))}] : [])]}, half) : '<div class="empty">Import yearly statements to see this.</div>';
  // income and costs
  const fy = [...new Set(YF.map(r => r.year))].sort(), sum = (y, keys) => YF.filter(r => r.year === y).reduce((s, r) => s + keys.reduce((t, k) => t + (r[k] || 0), 0), 0);
  $('#hisFlows').innerHTML = fy.length ? chartHtml({type: 'bar', unit: '€', labels: fy.map(String), series: [
    {name: 'Dividends and interest', values: fy.map(y => sum(y, ['dividends_eur', 'interest_received_eur']))}, {name: 'Interest, fees and taxes paid', values: fy.map(y => sum(y, ['interest_paid_eur', 'fees_eur', 'taxes_eur']))}]}, half) : '<div class="empty">Nothing recorded yet.</div>';
  drawTrades(trades);
  $('#trQ').oninput = e => { HIS.q = e.target.value; drawTrades(trades); };
  $('#trAcct').onchange = e => { HIS.acct = e.target.value; drawTrades(trades); };
  $('#trYear').onchange = e => { HIS.year = e.target.value; drawTrades(trades); };
  $$('[data-trt]').forEach(b => b.onclick = () => { HIS.type = b.dataset.trt; $$('[data-trt]').forEach(x => x.setAttribute('aria-pressed', x === b)); drawTrades(trades); });
  if (!SP.d) ensureSpending().then(() => { if (view === 'history') historyPage(); }).catch(() => {});
}
const HIS = {view: 'net', q: '', acct: '', year: '', type: '', all: false};
function drawTrades(all) {
  const box = $('#trList'); if (!box) return;
  const q = (HIS.q || '').toLowerCase();
  const isType = (t, k) => k === 'dividend' ? /divid|distrib/.test(t.type) : t.type === k;
  const list = all.filter(t => (!HIS.acct || t.account === HIS.acct) && (!HIS.year || t.date.startsWith(HIS.year)) && (!HIS.type || isType(t, HIS.type)) && (!q || t.name.toLowerCase().includes(q)));
  const sum = k => list.filter(t => isType(t, k)).reduce((s, t) => s + Math.abs(t.amount || 0), 0);
  $('#trSum').innerHTML = all.length ? `${list.length} trades · bought ${eur(sum('buy'))} · sold ${eur(sum('sell'))} · dividends ${eur(sum('dividend'))}` : '';
  if (!all.length) { box.innerHTML = '<div class="empty">No trades recorded yet. A Trade Republic export brings in every buy, sale and dividend; broker statements can too.</div>'; $('#trChart').innerHTML = ''; return; }
  // money put to work per month: buys minus sales
  const by = {};
  for (const t of list) { const m = t.date.slice(0, 7); if (isType(t, 'buy')) by[m] = (by[m] || 0) + Math.abs(t.amount); else if (isType(t, 'sell')) by[m] = (by[m] || 0) - Math.abs(t.amount); }
  const ms = Object.keys(by).sort().slice(-24);
  $('#trChart').innerHTML = ms.length > 1 ? chartHtml({type: 'bar', unit: '€', labels: ms.map(mLabel), series: [{name: 'Bought minus sold', values: ms.map(m => Math.round(by[m]))}]}, Math.max(320, box.clientWidth || 900)) : '';
  const shown = HIS.all ? list : list.slice(0, 12);
  box.innerHTML = `<div class="table-wrap"><table class="compact"><thead><tr><th>Date</th><th>Investment</th><th>What</th><th class="num">Units</th><th class="num">Price</th><th class="num">Amount</th></tr></thead>
    <tbody>${shown.map(t => `<tr><td class="muted small" style="white-space:nowrap">${fdate(t.date)}</td><td><button type="button" class="nm linkish" data-open="holding:${esc(t.id)}">${esc(t.name)}</button><div class="meta">${esc(t.account)}</div></td>
      <td>${esc(t.type[0].toUpperCase() + t.type.slice(1))}</td><td class="num">${t.units ? Math.abs(t.units).toLocaleString('en-GB', {maximumFractionDigits: 4}) : ''}</td>
      <td class="num">${t.price ? eur(t.price, 2) : ''}</td><td class="num">${sgn(t.amount, 2)}</td></tr>`).join('') || '<tr><td colspan="6" class="empty">No trades match.</td></tr>'}</tbody></table></div>
    ${list.length > 12 ? `<button type="button" class="btn ghost" id="trAll">${HIS.all ? 'Show less' : `Show all ${list.length}`}</button>` : ''}`;
  if ($('#trAll')) $('#trAll').onclick = () => { HIS.all = !HIS.all; drawTrades(all); };
}
function yearCard(f) {
  const ch = f.start != null && f.end != null ? f.end - f.start : null;
  return `<button type="button" class="card year-card" data-story="${f.year}">
    <div class="yc-head"><b>${f.year}</b>${f.year === new Date().getFullYear() ? '<span class="tag">so far</span>' : ''}<span class="muted small yc-open">Year in review →</span></div>
    ${ch != null ? `<div class="yc-nw"><span class="amt">${fmtV(f.start, '€', true)}</span> → <b class="amt">${fmtV(f.end, '€', true)}</b> <span class="${ch < 0 ? 'neg' : 'pos'} small">${ch < 0 ? '−' : '+'}${fmtV(Math.abs(ch), '€', true)}</span></div>`
      : f.end != null ? `<div class="yc-nw"><b class="amt">${fmtV(f.end, '€', true)}</b> <span class="muted small">recorded at year end</span></div>` : '<div class="yc-nw muted small">No values recorded</div>'}
    <div class="kv small">${f.saved != null && f.n ? `<span>Saved</span><span>${sgn(f.saved)}${f.rate != null ? ` <span class="muted">(${Math.max(0, f.rate).toFixed(0)}%)</span>` : ''}</span>` : ''}
      ${f.result != null ? `<span>Investment result</span><span>${sgn(f.result)}</span>` : ''}
      ${f.biggest ? `<span>Biggest expense</span><span>${esc(f.biggest.merchant.slice(0, 18))} ${eur(-f.biggest.amount)}</span>` : ''}
      ${f.countries && f.countries.length ? `<span>Countries</span><span>${esc(f.countries.slice(0, 3).map(ctyName).join(', '))}${f.countries.length > 3 ? ` +${f.countries.length - 3}` : ''}</span>` : ''}</div></button>`;
}
function yearStory(y) {
  const f = yearFacts(y), ch = f.start != null && f.end != null ? f.end - f.start : null;
  const slides = [
    `<div class="st-k">Your</div><div class="st-big">${y}</div>${ch != null ? `<div class="st-line">Net worth went from <b class="amt">${eur(f.start)}</b> to <b class="amt">${eur(f.end)}</b></div><div class="st-delta ${ch < 0 ? 'neg' : 'pos'} amt">${ch < 0 ? '−' : '+'}${eur(Math.abs(ch))}</div>` : '<div class="st-line muted">Scroll to see your year</div>'}`,
    f.n ? `<div class="st-k">Money in and out</div><div class="st-row"><div><span class="st-mid amt">${eur(f.income)}</span><span class="muted">came in</span></div><div><span class="st-mid amt">${eur(f.spent)}</span><span class="muted">went out</span></div></div>
      <div class="st-line">You kept <b class="amt">${eur(Math.max(0, f.saved))}</b>${f.rate != null ? `, <b>${Math.max(0, f.rate).toFixed(0)}%</b> of what you earned` : ''}</div>` : '',
    f.cats && f.cats.length ? `<div class="st-k">Where it went</div><div class="st-bars">${f.cats.slice(0, 6).map(([c, v]) => `<div class="st-bar"><span>${esc(catName(c))}</span><i style="width:${v / f.cats[0][1] * 100}%"></i><b class="amt">${eur(v)}</b></div>`).join('')}</div>` : '',
    f.biggest ? `<div class="st-k">The biggest expense</div><div class="st-mid">${esc(f.biggest.merchant)}</div><div class="st-delta amt">${eur(-f.biggest.amount)}</div><div class="st-line muted">${fdate(f.biggest.date)}, ${esc(catName(f.biggest.category))}</div>` : '',
    f.busiest ? `<div class="st-k">The busiest month</div><div class="st-big">${MONTHS[+f.busiest[0].slice(5) - 1]}</div><div class="st-line">with <b class="amt">${eur(f.busiest[1])}</b> spent</div>` : '',
    f.countries && f.countries.length ? `<div class="st-k">Places</div><div class="st-map">${miniMap(f.countries, 520, 260)}</div><div class="st-line">${esc(f.countries.map(ctyName).join(', '))}</div>` : '',
    f.result != null ? `<div class="st-k">Your investments</div><div class="st-delta ${f.result < 0 ? 'neg' : 'pos'} amt">${f.result < 0 ? '−' : '+'}${eur(Math.abs(f.result))}</div>${f.byAccount.map(([a, v]) => `<div class="st-line">${esc(a)}: <b class="amt">${sgn(v)}</b></div>`).join('')}` : '',
    `<div class="st-k">That was ${y}</div><div class="st-big">${y === new Date().getFullYear() ? 'So far' : `On to ${y + 1}`}</div><button type="button" class="btn primary" id="stAsk">Talk about ${y} with Claude</button>`,
  ].filter(Boolean);
  const ov = document.createElement('div');
  ov.className = 'story';
  ov.innerHTML = `<button type="button" class="icon-btn st-close" aria-label="Close">${ICON.x}</button><div class="st-dots">${slides.map((_, i) => `<i data-sd="${i}"></i>`).join('')}</div>
    <div class="st-scroll">${slides.map((s, i) => `<section class="st-slide" data-si="${i}"><div class="st-in">${s}</div></section>`).join('')}</div>`;
  document.body.appendChild(ov);
  const sc = $('.st-scroll', ov);
  const close = () => { ov.remove(); document.removeEventListener('keydown', key); };
  const key = e => { if (e.key === 'Escape') close(); if (e.key === 'ArrowDown' || e.key === 'ArrowRight' || e.key === ' ') { e.preventDefault(); sc.scrollBy({top: innerHeight, behavior: 'smooth'}); } if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') { e.preventDefault(); sc.scrollBy({top: -innerHeight, behavior: 'smooth'}); } };
  document.addEventListener('keydown', key);
  $('.st-close', ov).onclick = close;
  const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); $$('[data-sd]', ov).forEach(d => d.classList.toggle('on', d.dataset.sd === e.target.dataset.si)); } }), {root: sc, threshold: 0.6});
  $$('.st-slide', ov).forEach(s => io.observe(s));
  $$('[data-sd]', ov).forEach(d => d.onclick = () => $(`[data-si="${d.dataset.sd}"]`, ov).scrollIntoView({behavior: 'smooth'}));
  if ($('#stAsk', ov)) $('#stAsk', ov).onclick = () => { close(); openChat({ctx: {title: `${y} in review`, text: slides.map(s => s.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ')).join(' | ')}}); };
}

/* ---------- plan ---------- */
const PLAN = {save: null, ret: store.get('plan.ret', 5), vol: store.get('plan.vol', 'mid'), spend: null, wr: store.get('plan.wr', 4), real: store.get('plan.real', true), loan: {}, home: {}};
function mulberry(a) { return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
function avgSaved() {
  if (!SP.d) return null;
  const cur = isoD(new Date()).slice(0, 7), months = [...new Set(SP.rows.map(t => t.date.slice(0, 7)))].filter(m => m < cur).sort().slice(-6);
  if (!months.length) return null;
  const T = totals(SP.rows.filter(t => months.includes(t.date.slice(0, 7))));
  return {saved: T.saved / months.length, spent: T.spent / months.length};
}
function planPage() {
  if (!SP.d) { ensureSpending().then(() => { if (view === 'plan') planPage(); }).catch(() => {}); }
  const av = avgSaved();
  if (PLAN.save == null) PLAN.save = Math.max(0, Math.round((av ? av.saved : 500) / 50) * 50);
  if (PLAN.spend == null) PLAN.spend = Math.round((av ? av.spent : 2000) / 50) * 50;
  const prof = S.profile || {}, age = prof.birth_year ? new Date().getFullYear() - prof.birth_year : null;
  const goals = S.goals || [];
  const monthsTo = d => d ? Math.max(1, Math.round((Date.parse(d.length === 7 ? d + '-01' : d) - Date.now()) / (30.4375 * 864e5))) : null;
  $('#view').innerHTML = `<div class="stack-y">
    <section class="card"><div class="card-head"><div><h2>Goals</h2><p class="sub">${av ? `You save about ${eur(av.saved)} a month (last six months)` : 'Import your bank exports to see how much you save each month'}</p></div><button class="btn" id="goalAdd">Add goal</button></div>
      ${goals.length ? `<div class="goals">${goals.map((g, i) => { const have = goalAmount(g), p = g.target_eur ? have / g.target_eur : 0, n = monthsTo(g.date), need = n ? Math.max(0, (g.target_eur - have) / n) : null;
        const state = p >= 1 ? '<span class="tag good">Reached</span>' : need == null ? '' : av && av.saved >= need ? '<span class="tag good">On track</span>' : `<span class="tag warn">Needs ${eur(need)} a month</span>`;
        return `<button type="button" class="goal" data-goal="${i}">${ring(p, 58, p >= 1 ? 'var(--gain)' : 'var(--s1)')}<div class="goal-t"><b>${esc(g.name)}</b><span class="muted small"><span class="amt">${eur(have)}</span> of <span class="amt">${eur(g.target_eur)}</span>${g.date ? ` by ${fdate(g.date)}` : ''}</span>${state}</div></button>`; }).join('')}</div>`
        : '<div class="empty">No goals yet. A house deposit, a sabbatical, being debt free: add one and see if you are on track.</div>'}
    </section>
    <section class="card" data-card="proj"><div class="card-head"><h2>Where your money could go</h2><span class="muted small" id="fireNote"></span></div>
      <div class="sliders">
        <label>Saving per month <b id="vSave"></b><input type="range" id="sSave" min="0" max="${Math.max(3000, PLAN.save * 2)}" step="50" value="${PLAN.save}"></label>
        <label>Expected return <b id="vRet"></b><input type="range" id="sRet" min="0" max="10" step="0.5" value="${PLAN.ret}"></label>
        <label>Spending per month later <b id="vSpend"></b><input type="range" id="sSpend" min="500" max="${Math.max(8000, PLAN.spend * 2)}" step="50" value="${PLAN.spend}"></label>
        <label>Safe withdrawal <b id="vWr"></b><input type="range" id="sWr" min="2.5" max="5" step="0.25" value="${PLAN.wr}"></label>
      </div>
      <div class="controls" style="margin:8px 0 0">${seg('vol', [['low', 'Steady mix'], ['mid', 'Mostly stocks'], ['high', 'All stocks']], PLAN.vol)}
        <label class="check"><input type="checkbox" id="sReal" ${PLAN.real ? 'checked' : ''}> In today's money (2% inflation taken off)</label>
        ${age == null ? '<a href="#settings" class="small">Add your birth year for ages</a>' : ''}</div>
      <div id="fan"></div>
    </section>
    <section class="card"><h2>Big decisions</h2><p class="sub">Simple models with the assumptions shown. Ask Claude to go deeper on your own situation.</p>
      <div class="grid g2 decide">${decideLoan()}${decideHome()}</div></section>
  </div>`;
  const goalFields = g => [{k: 'name', label: 'Goal', type: 'text', value: g.name || ''}, {k: 'target_eur', label: 'Amount (€)', type: 'number', value: g.target_eur ?? ''},
    {k: 'date', label: 'By when', type: 'date', value: g.date && g.date.length === 10 ? g.date : g.date ? g.date + '-01' : ''},
    {k: 'source', label: 'Counts: net_worth, savings, investments, pot or manual', type: 'text', value: g.source || 'savings'},
    {k: 'pot', label: 'Pot name (when it counts a pot)', type: 'text', value: g.pot || ''}, {k: 'saved_eur', label: 'Saved so far (€, when manual)', type: 'number', value: g.saved_eur ?? ''}];
  $('#goalAdd').onclick = () => form('Add goal', goalFields({}), v => edit({section: 'goals', action: 'add', fields: v}, 'Goal added'));
  $$('[data-goal]').forEach(b => b.onclick = () => { const i = +b.dataset.goal; form('Edit ' + goals[i].name, goalFields(goals[i]), v => edit({section: 'goals', index: i, fields: v}), () => edit({section: 'goals', action: 'delete', index: i}, 'Goal removed')); });
  const upd = () => {
    PLAN.save = +$('#sSave').value; PLAN.ret = +$('#sRet').value; PLAN.spend = +$('#sSpend').value; PLAN.wr = +$('#sWr').value; PLAN.real = $('#sReal').checked;
    store.set('plan.ret', PLAN.ret); store.set('plan.wr', PLAN.wr); store.set('plan.real', PLAN.real);
    $('#vSave').innerHTML = `<span class="amt">€${fmtN(PLAN.save)}</span>`; $('#vRet').textContent = PLAN.ret + '%'; $('#vSpend').innerHTML = `<span class="amt">€${fmtN(PLAN.spend)}</span>`; $('#vWr').textContent = PLAN.wr + '%';
    drawFan(age);
  };
  ['sSave', 'sRet', 'sSpend', 'sWr', 'sReal'].forEach(id => $('#' + id).oninput = upd);
  onSeg('vol', v => { PLAN.vol = v; store.set('plan.vol', v); $$('[data-seg="vol"] button').forEach(b => b.setAttribute('aria-pressed', b.dataset.v === v)); drawFan(age); });
  upd();
  wireDecide();
}
function drawFan(age) {
  // many possible futures with yearly ups and downs; the band shows the middle 80% and 50% of them
  const years = 40, paths = 700, rnd = mulberry(42);
  const vol = {low: 0.08, mid: 0.14, high: 0.18}[PLAN.vol], mu = PLAN.ret / 100 - (PLAN.real ? 0.02 : 0);
  const start = S.totals.net_worth, fire = PLAN.spend * 12 / (PLAN.wr / 100);
  const at = Array.from({length: years + 1}, () => []);
  const gauss = () => { let u = 0, v = 0; while (!u) u = rnd(); while (!v) v = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
  for (let p = 0; p < paths; p++) {
    let w = start; at[0].push(w);
    for (let y = 1; y <= years; y++) { const r = Math.exp(Math.log(1 + mu) - vol * vol / 2 + vol * gauss()) - 1; w = w * (1 + r) + PLAN.save * 12; at[y].push(w); }
  }
  const q = (a, f) => { const s = [...a].sort((x, y) => x - y); return s[Math.floor(f * (s.length - 1))]; };
  const y0 = new Date().getFullYear(), T = y => tOf(`${y0 + y}-01-01`);
  const pts = f => at.map((a, y) => [T(y), q(a, f)]);
  const med = pts(0.5), fireYear = med.findIndex(([, v]) => v >= fire);
  const chance = y => at[y].filter(v => v >= fire).length / paths;
  timeChart($('#fan'), {series: [{name: 'Most likely', pts: med, color: 'var(--s1)'}], bands: [{pts: at.map((a, y) => [T(y), q(a, 0.1), q(a, 0.9)]), color: 'var(--s1)', op: 0.1}, {pts: at.map((a, y) => [T(y), q(a, 0.25), q(a, 0.75)]), color: 'var(--s1)', op: 0.16}],
    hline: {v: fire, label: `Enough to stop working: ${fmtV(fire, '€', true)}`}, xfmt: 'year', height: 300, legend: false, label: 'Projection'});
  $('#fireNote').innerHTML = fireYear < 0 ? `Not within ${years} years at this pace` : `Likely enough by <b>${y0 + fireYear}</b>${age != null ? ` (age ${age + fireYear})` : ''} · ${Math.round(chance(Math.min(years, Math.max(fireYear, 1))) * 100)}% of futures by then`;
}
function decideLoan() {
  const d = S.debts.find(x => !x.expected_gift && x.rate_pct) || {name: 'a loan', balance: 10000, rate_pct: 2.5};
  const L = Object.assign({amount: Math.round(Math.min(d.balance, Math.max(1000, S.totals.savings / 3)) / 500) * 500, rate: d.rate_pct, ret: 5, years: 10}, PLAN.loan);
  PLAN.loan = L;
  return `<div class="decide-card" id="dLoan"><h3>Repay ${esc(d.name)} early, or invest?</h3>
    <div class="sliders small"><label>Amount <b data-dv="amount"></b><input type="range" data-dl="amount" min="500" max="${Math.max(2000, Math.round(d.balance))}" step="500" value="${L.amount}"></label>
      <label>Loan interest <b data-dv="rate"></b><input type="range" data-dl="rate" min="0" max="8" step="0.05" value="${L.rate}"></label>
      <label>Investment return <b data-dv="ret"></b><input type="range" data-dl="ret" min="0" max="10" step="0.5" value="${L.ret}"></label>
      <label>Years <b data-dv="years"></b><input type="range" data-dl="years" min="1" max="30" step="1" value="${L.years}"></label></div>
    <div id="dLoanOut"></div></div>`;
}
function decideHome() {
  const H = Object.assign({price: 400000, own: 60000, mrate: 3.8, rent: 1500, grow: 3, ret: 5, years: 10}, PLAN.home);
  PLAN.home = H;
  return `<div class="decide-card" id="dHome"><h3>Buy a home, or keep renting?</h3>
    <div class="sliders small"><label>Price <b data-hv="price"></b><input type="range" data-dh="price" min="150000" max="1000000" step="10000" value="${H.price}"></label>
      <label>Own money in <b data-hv="own"></b><input type="range" data-dh="own" min="0" max="300000" step="5000" value="${H.own}"></label>
      <label>Mortgage rate <b data-hv="mrate"></b><input type="range" data-dh="mrate" min="1" max="7" step="0.1" value="${H.mrate}"></label>
      <label>Rent now <b data-hv="rent"></b><input type="range" data-dh="rent" min="500" max="4000" step="50" value="${H.rent}"></label>
      <label>House prices per year <b data-hv="grow"></b><input type="range" data-dh="grow" min="-2" max="8" step="0.5" value="${H.grow}"></label>
      <label>Years <b data-hv="years"></b><input type="range" data-dh="years" min="3" max="30" step="1" value="${H.years}"></label></div>
    <div id="dHomeOut"></div></div>`;
}
function wireDecide() {
  const loanOut = () => {
    const L = PLAN.loan;
    for (const k of ['amount', 'rate', 'ret', 'years']) $(`[data-dv="${k}"]`).innerHTML = k === 'amount' ? `<span class="amt">€${fmtN(L.amount)}</span>` : k === 'years' ? L.years : L[k] + '%';
    const repay = L.amount * ((1 + L.rate / 100) ** L.years - 1), invest = L.amount * ((1 + L.ret / 100) ** L.years - 1);
    const mx = Math.max(repay, invest, 1);
    $('#dLoanOut').innerHTML = `<div class="dec-bars"><div><span>Repay: interest you never pay</span><i style="width:${repay / mx * 100}%"></i><b class="amt">${eur(repay)}</b></div>
      <div><span>Invest: expected growth</span><i class="alt" style="width:${invest / mx * 100}%"></i><b class="amt">${eur(invest)}</b></div></div>
      <p class="small ${invest > repay ? '' : 'pos'}">${invest > repay ? `Investing is expected to come out ${eur(invest - repay)} ahead, but it is not guaranteed; repaying is a certain ${L.rate}% return.` : `Repaying wins: a certain ${L.rate}% beats an expected ${L.ret}%.`}</p>`;
  };
  const homeOut = () => {
    const H = PLAN.home;
    for (const k of ['price', 'own', 'mrate', 'rent', 'grow', 'years']) $(`[data-hv="${k}"]`).innerHTML = ['price', 'own', 'rent'].includes(k) ? `<span class="amt">€${fmtN(H[k])}</span>` : k === 'years' ? H.years : H[k] + '%';
    // buying: annuity mortgage, 2% buying costs, 1% of the value a year in upkeep; renting: rent up 3% a year, the own money and the monthly difference invested
    const loan = Math.max(0, H.price * 1.02 - H.own), r = H.mrate / 100 / 12, n = 360, pay = loan ? loan * r / (1 - (1 + r) ** -n) : 0;
    let bal = loan, rentM = H.rent, inv = H.own, buyCost = 0, rentCost = 0;
    for (let m = 1; m <= H.years * 12; m++) {
      const value = H.price * (1 + H.grow / 100) ** (m / 12), upkeep = value * 0.01 / 12, own = pay + upkeep;
      bal = bal * (1 + r) - pay; buyCost += own; rentCost += rentM;
      inv = inv * (1 + 0.05 / 12) + Math.max(0, own - rentM);
      if (m % 12 === 0) rentM *= 1.03;
    }
    const value = H.price * (1 + H.grow / 100) ** H.years, buyNW = value - Math.max(0, bal), rentNW = inv;
    const mx = Math.max(buyNW, rentNW, 1);
    $('#dHomeOut').innerHTML = `<div class="dec-bars"><div><span>Buying: home value minus mortgage</span><i style="width:${Math.max(0, buyNW) / mx * 100}%"></i><b class="amt">${eur(buyNW)}</b></div>
      <div><span>Renting: own money invested at 5%</span><i class="alt" style="width:${Math.max(0, rentNW) / mx * 100}%"></i><b class="amt">${eur(rentNW)}</b></div></div>
      <p class="small">Mortgage about <span class="amt">${eur(pay)}</span> a month plus upkeep, against <span class="amt">${eur(H.rent)}</span> rent. After ${H.years} years, ${buyNW > rentNW ? 'buying' : 'renting'} leaves you about <span class="amt">${eur(Math.abs(buyNW - rentNW))}</span> ahead. Tax effects (mortgage interest deduction, box 3) are left out.</p>`;
  };
  $$('[data-dl]').forEach(i => i.oninput = () => { PLAN.loan[i.dataset.dl] = +i.value; loanOut(); });
  $$('[data-dh]').forEach(i => i.oninput = () => { PLAN.home[i.dataset.dh] = +i.value; homeOut(); });
  loanOut(); homeOut();
}

/* ---------- taxes ---------- */
// Box 3 rules per tax year. 2026 rates are provisional; check belastingdienst.nl and adjust in the table below.
const BOX3 = {
  2024: {bank: 1.03, other: 6.04, debt: 2.47, allowance: 57000, threshold: 3700, rate: 36},
  2025: {bank: 1.44, other: 5.88, debt: 2.62, allowance: 57684, threshold: 3800, rate: 36},
  2026: {bank: 1.28, other: 6.00, debt: 2.70, allowance: 51396, threshold: 3800, rate: 36, provisional: true},
};
const TAX = {year: new Date().getFullYear(), sim: {repay: 0, invest: 0, spend: 0}};
function box3Params(y) {
  const saved = ((S.tax || {}).params || {})[y];
  const known = Object.keys(BOX3).map(Number).sort();
  return {...(BOX3[y] || BOX3[known.filter(k => k <= y).pop() || known[0]]), ...(saved || {}), guessed: !BOX3[y] && !saved};
}
function box3(bank, other, debts, P, partner) {
  const allow = P.allowance * (partner ? 2 : 1), thr = P.threshold * (partner ? 2 : 1), d = Math.max(0, debts - thr);
  const ret = bank * P.bank / 100 + other * P.other / 100 - d * P.debt / 100, base = bank + other - d;
  const eff = base > 0 ? ret / base : 0, taxable = Math.max(0, base - allow), gain = taxable * eff;
  return {allow, thr, d, ret, base, eff, taxable, gain, tax: Math.max(0, gain * P.rate / 100)};
}
function peildatum(y) {
  // values on 1 January: from the daily history when the app ran then, else from year end statements, else today's
  const iso = `${y}-01-01`, h = (S.history || []).filter(x => x.date <= `${y}-01-07` && x.date >= `${y - 1}-12-20`).pop();
  if (h && h.cash != null) return {bank: h.cash, other: (h.etf + h.stocks + h.bonds + h.other_inv) + h.managed, debts: h.debt, src: `your recorded values on ${fdate(h.date)}`};
  if (h) return {bank: h.savings, other: h.self_directed + h.managed, debts: h.debt, src: `your recorded values on ${fdate(h.date)}`};
  const ah = (S.account_history || []).filter(r => r.date === `${y - 1}-12-31`);
  if (ah.length) {
    const sav = new Set(S.savings.map(s => s.name)), deb = new Set(S.debts.map(d => d.name));
    return {bank: ah.filter(r => sav.has(r.account)).reduce((s, r) => s + r.value_eur, 0), other: ah.filter(r => !sav.has(r.account) && !deb.has(r.account)).reduce((s, r) => s + r.value_eur, 0),
      debts: ah.filter(r => deb.has(r.account)).reduce((s, r) => s + Math.abs(r.value_eur), 0), src: `year end statements of ${y - 1}`};
  }
  const t = S.totals;
  return {bank: t.cash ?? t.savings, other: (t.etf + t.stocks + t.bonds + t.other_inv) + t.managed, debts: t.debt, src: iso > today() ? 'today\'s values, as an estimate' : 'today\'s values, because nothing was recorded on that date', estimate: true};
}
function taxesPage() {
  const y = TAX.year, P = box3Params(y), partner = !!(S.tax || {}).partner, v = peildatum(y), R = box3(v.bank, v.other, v.debts, P, partner);
  const sim = TAX.sim, sv = {bank: v.bank - sim.repay - sim.invest - sim.spend, other: v.other + sim.invest, debts: Math.max(0, v.debts - sim.repay)};
  const RS = box3(sv.bank, sv.other, sv.debts, P, partner);
  const flows = (S.yearly_flows || []).filter(r => r.year === y - 1);
  const actual = flows.length ? flows.reduce((s, r) => s + (r.dividends_eur || 0) + (r.interest_received_eur || 0) + (r.profit_eur || 0) - (r.interest_paid_eur || 0), 0) : null;
  const checks = ((S.tax || {}).checklist || {})[y] || {};
  const items = [
    ...S.savings.map(s => ({k: 'bank:' + s.name, t: `${s.name} (${s.bank}) on 1 January ${y}`, v: s.value})),
    ...S.accounts.map(a => ({k: 'inv:' + a.name, t: `${a.name} value on 1 January ${y}`, v: a.value + a.cash})),
    {k: 'inv:managed', t: `${S.managed.name} value on 1 January ${y}`, v: S.managed.value},
    ...S.debts.filter(d => !d.expected_gift).map(d => ({k: 'debt:' + d.name, t: `${d.name} balance on 1 January ${y}`, v: d.balance})),
    ...(flows.some(r => r.taxes_eur) ? [{k: 'divtax', t: `Dividend tax withheld in ${y - 1}`, v: flows.reduce((s, r) => s + (r.taxes_eur || 0), 0)}] : []),
    {k: 'prefill', t: 'Compare the pre-filled return with these numbers', v: null}];
  const now = new Date(), cal = [[`${y}-01-01`, 'Box 3 reference date: what you own and owe on this day counts for the whole year'], [`${y + 1}-03-01`, `Tax return over ${y} opens`],
    [`${y + 1}-05-01`, `Deadline for the return over ${y}, or ask for more time (until 1 September)`], [`${y + 1}-09-01`, 'Deadline when you asked for more time'],
    [`${y}-12-01`, `Ask for or adjust a provisional assessment for ${y + 1}, so you pay or get money back spread over the year`], [`${y + 1}-01-01`, `Next reference date: moves before this day count for ${y + 1}`]].sort((a, b) => a[0].localeCompare(b[0]));
  const nextIdx = cal.findIndex(c => c[0] >= isoD(now));
  const row = (l, val, cls = '') => `<tr class="${cls}"><td>${l}</td><td class="num">${val}</td></tr>`;
  $('#view').innerHTML = `<div class="stack-y">
    <div class="controls" style="margin:0">${seg('taxyear', [y - 1, y, y + 1].map(x => [String(x), String(x)]), String(y))}
      <label class="check"><input type="checkbox" id="partner" ${partner ? 'checked' : ''}> With a tax partner (allowance doubled)</label></div>
    ${P.guessed || P.provisional ? `<div class="banner warn">The rates for ${y} are ${P.provisional ? 'provisional' : 'copied from the latest year I know'}. Check belastingdienst.nl and adjust them under Rates below.</div>` : ''}
    <div class="grid g4">
      <div class="card tile"><div class="k">Box 3 tax for ${y}</div><div class="v" data-count="${R.tax}">${eur(R.tax)}</div><div class="n">${(R.tax / 12).toFixed(0) > 0 ? `about ${eur(R.tax / 12)} a month` : 'under the allowance'}</div></div>
      <div class="card tile"><div class="k">Counted wealth</div><div class="v">${eur(R.base)}</div><div class="n">on 1 January ${y}</div></div>
      <div class="card tile"><div class="k">Above the allowance</div><div class="v">${eur(R.taxable)}</div><div class="n">allowance ${eur(R.allow)}</div></div>
      <div class="card tile"><div class="k">Assumed return</div><div class="v">${(R.eff * 100).toFixed(2)}%</div><div class="n">taxed at ${P.rate}%</div></div>
    </div>
    <div class="grid g2">
      <section class="card"><h2>How it is worked out</h2><p class="sub">From ${esc(v.src)}${v.estimate ? '. Replace with your real 1 January balances when you have them.' : ''}</p>
        <div class="table-wrap"><table class="calc"><tbody>
          ${row('Bank and savings', eur(v.bank))}${row(`× ${P.bank}% assumed return`, eur(v.bank * P.bank / 100), 'sub')}
          ${row('Investments and other', eur(v.other))}${row(`× ${P.other}% assumed return`, eur(v.other * P.other / 100), 'sub')}
          ${row(`Debts above ${eur(R.thr)}`, eur(R.d))}${row(`× ${P.debt}% assumed cost`, '−' + eur(R.d * P.debt / 100), 'sub')}
          ${row('Counted wealth', eur(R.base), 'strong')}${row('Total assumed return', eur(R.ret))}${row('As a share of counted wealth', (R.eff * 100).toFixed(2) + '%')}
          ${row('Minus the tax free allowance', '−' + eur(R.allow))}${row('Taxed base', eur(R.taxable))}${row('Taxed income (base × share)', eur(R.gain))}${row(`Tax at ${P.rate}%`, eur(R.tax), 'strong')}
        </tbody></table></div>
        ${actual != null ? `<p class="small" style="margin-top:10px">Your recorded actual return in ${y - 1} was <b class="amt">${eur(actual)}</b>. When your real return is lower than the assumed one, you can ask to be taxed on the real return instead.</p>` : ''}
      </section>
      <section class="card"><h2>Before 1 January</h2><p class="sub">What moving money before the reference date of ${y + (y < now.getFullYear() ? 1 : 0)} would do, with these rates</p>
        <div class="sliders">
          <label>Repay debt from savings <b id="vRepay"></b><input type="range" id="sRepay" min="0" max="${Math.max(0, Math.min(v.bank, v.debts))}" step="500" value="${sim.repay}"></label>
          <label>Move savings into investments <b id="vInvest"></b><input type="range" id="sInvest" min="0" max="${Math.max(0, v.bank)}" step="500" value="${sim.invest}"></label>
          <label>Spend from savings (a planned purchase) <b id="vSpend2"></b><input type="range" id="sSpend2" min="0" max="${Math.max(0, v.bank)}" step="500" value="${sim.spend}"></label></div>
        <div class="sim-out" id="simOut"></div>
        <p class="muted small">Investments count at a higher assumed return than savings, so moving savings into investments raises box 3 tax even when it may pay off over time.</p>
      </section>
    </div>
    <div class="grid g2">
      <section class="card"><h2>For your tax return</h2><p class="sub">Click a number to copy it. Tick what you have entered.</p>
        ${items.map(it => `<div class="chk-row"><input type="checkbox" data-chk="${esc(it.k)}" ${checks[it.k] ? 'checked' : ''} aria-label="Done"><span>${esc(it.t)}</span>${it.v != null ? `<button type="button" class="linkish num amt" data-copy="${it.v.toFixed(0)}" title="Copy">${eur(it.v)}</button>` : ''}</div>`).join('')}
        <p class="muted small" style="margin:10px 0 0">Values shown are today's; use the 1 January figures from your banks' year overviews when they differ.</p></section>
      <section class="card"><h2>Tax calendar</h2>${cal.map((c, i) => `<div class="cal-row ${i === nextIdx ? 'next' : ''} ${c[0] < isoD(now) ? 'past' : ''}"><span class="cal-date">${fdate(c[0])}</span><span>${esc(c[1])}</span></div>`).join('')}</section>
    </div>
    <details class="card"><summary><b>Rates for ${y}</b> <span class="muted small">change them if the official numbers differ</span></summary>
      <form id="rates" class="rates">${[['bank', 'Bank savings return (%)'], ['other', 'Other assets return (%)'], ['debt', 'Debt cost (%)'], ['allowance', 'Tax free allowance (€)'], ['threshold', 'Debt threshold (€)'], ['rate', 'Tax rate (%)']].map(([k, l]) =>
        `<label class="field">${l}<input type="number" step="any" name="${k}" value="${P[k]}"></label>`).join('')}<div><button class="btn primary">Save rates</button></div></form></details>
  </div>`;
  onSeg('taxyear', v2 => { TAX.year = +v2; taxesPage(); });
  $('#partner').onchange = e => edit({section: 'tax', fields: {partner: e.target.checked}}, 'Saved');
  const simUpd = () => {
    sim.repay = +$('#sRepay').value; sim.invest = +$('#sInvest').value; sim.spend = +$('#sSpend2').value;
    $('#vRepay').innerHTML = `<span class="amt">€${fmtN(sim.repay)}</span>`; $('#vInvest').innerHTML = `<span class="amt">€${fmtN(sim.invest)}</span>`; $('#vSpend2').innerHTML = `<span class="amt">€${fmtN(sim.spend)}</span>`;
    const s2 = {bank: v.bank - sim.repay - sim.invest - sim.spend, other: v.other + sim.invest, debts: Math.max(0, v.debts - sim.repay)}, r2 = box3(s2.bank, s2.other, s2.debts, P, partner), d = r2.tax - R.tax;
    $('#simOut').innerHTML = `<span class="muted">Tax would be</span> <b class="amt">${eur(r2.tax)}</b> <span class="${Math.abs(d) < 1 ? 'muted' : d > 0 ? 'neg' : 'pos'}">${Math.abs(d) < 1 ? 'no change' : (d > 0 ? '+' : '−') + eur(Math.abs(d))}</span>`;
  };
  ['sRepay', 'sInvest', 'sSpend2'].forEach(id => $('#' + id).oninput = simUpd);
  simUpd();
  $$('[data-copy]').forEach(b => b.onclick = async () => { try { await navigator.clipboard.writeText(b.dataset.copy); toast('Copied ' + b.dataset.copy); } catch { toast(b.dataset.copy); } });
  $$('[data-chk]').forEach(c => c.onchange = () => { const all = {...((S.tax || {}).checklist || {})}; all[y] = {...(all[y] || {}), [c.dataset.chk]: c.checked}; edit({section: 'tax', fields: {checklist: all}}, c.checked ? 'Ticked' : 'Unticked'); });
  $('#rates').onsubmit = e => { e.preventDefault(); const f = Object.fromEntries([...new FormData(e.target)].map(([k, x]) => [k, +x])); const params = {...((S.tax || {}).params || {}), [y]: f}; edit({section: 'tax', fields: {params}}, 'Rates saved'); };
  countUp();
}

/* ---------- advice ---------- */
const EFFORT_RANK = {'2 minutes': 1, '5 minutes': 1, '10 minutes': 2, '15 minutes': 2, '30 minutes': 3, 'an hour': 4, 'a few months': 6};
const RISK = [['low', 'Careful'], ['medium', 'Balanced'], ['high', 'Adventurous']];
/* opportunities: what stands out in your numbers, Claude's ideas of the week, and the watchlist */
let OPP = null, OPP_T = null;
async function loadOpp(force) {
  try { OPP = force ? await post('/api/opportunities/refresh', {}) : await (await fetch('/api/opportunities', {cache: 'no-store'})).json(); }
  catch (e) { if (force) toast(e.message); OPP = OPP || {signals: [], ideas: {}, watchlist: []}; }
  clearTimeout(OPP_T);
  // keep checking while Claude writes the ideas or prices are being fetched
  if (OPP.ideas && OPP.ideas.updating) OPP_T = setTimeout(() => { if (view === 'advice') loadOpp().then(drawOpp); }, 12000);
  return OPP;
}
function oppCard() {
  return `<section class="card opp-card" data-card="adv-opps"><div class="card-head"><div><h2>Opportunities</h2><p class="sub">Found for you automatically: from your own numbers every day, and new ideas from Claude every week</p></div>
      <button type="button" class="btn ghost sm" id="oppRefresh" title="Ask Claude for new ideas now">New ideas</button></div>
    <div id="oppBody"><div class="skel-line"></div><div class="skel-line short"></div></div>
    <details class="opp-more" id="oppResearch" hidden><summary class="muted small">Research: your stocks against their industry, and what well known investors did</summary><div id="researchBody"></div></details>
    <details class="opp-more"><summary class="muted small">Your risk profile and more questions for Claude</summary>
      <div class="pref-row"><span>Your risk profile</span>${seg('ideaRisk', RISK, (S.profile || {}).risk || '')}</div>
      <div class="idea-qs">${IDEA_QS.map(q => `<button type="button" class="barrow idea-q" data-idea="${esc(q)}"><span class="bl"><b>${esc(q)}</b></span><span aria-hidden="true">→</span></button>`).join('')}</div>
    </details></section>`;
}
const IDEA_QS = ['Which of my investments look expensive, and which look cheap right now?', 'Given my risk profile, what would you change in my portfolio?',
  'Which companies look undervalued and would fit my portfolio?', 'What are the biggest risks in my portfolio right now?', 'What does the recent news mean for my investments?'];
function drawOpp() {
  const box = $('#oppBody'); if (!box || !OPP) return;
  const sig = OPP.signals || [], I = OPP.ideas || {}, ideas = I.ideas || [], watched = new Set((OPP.watchlist || []).map(w => w.symbol));
  box.innerHTML = `${sig.length ? `<div class="opp-h">In your numbers</div>${sig.map((s, i) => `<div class="opp">
      <div class="opp-t">${esc(s.title)}</div><div class="muted small">${esc(s.detail)}</div>
      <div class="adv-act"><button class="btn sm" data-osig="${i}"><span class="claude-mark sm">${CLAUDE_ICON}</span>Talk about it</button>${s.open ? (s.open.startsWith('page:') ? `<button class="linkish small" data-link="${esc(JSON.stringify({kind: 'page', page: s.open.slice(5)}))}">Open</button>` : `<button class="linkish small" data-open="${esc(s.open)}">Open</button>`) : ''}</div></div>`).join('')}` : ''}
    <div class="opp-h">Ideas from Claude${I.date ? `<span class="ago">${fdate(I.date)}</span>` : ''}</div>
    ${ideas.map((d, i) => `<div class="opp idea">
      <div class="opp-top"><div class="opp-t">${esc(d.title)}</div>${d.type ? `<span class="chip-v">${esc(d.type)}</span>` : ''}</div>
      <div class="small"><b>${esc(d.name || '')}</b>${d.ticker ? ` <span class="muted">${esc(d.ticker)}</span>` : ''}</div>
      <div class="small">${esc(d.why || '')}</div>
      ${d.fits ? `<div class="muted small">Fits: ${esc(d.fits)}</div>` : ''}${d.risk ? `<div class="muted small">Risk: ${esc(d.risk)}</div>` : ''}
      <div class="adv-act"><button class="btn sm" data-oidea="${i}"><span class="claude-mark sm">${CLAUDE_ICON}</span>Talk about it</button>
        ${d.ticker ? (watched.has(d.ticker.toUpperCase()) ? '<span class="tag">On your watchlist</span>' : `<button class="linkish small" data-owatch="${i}">Watch</button>`) : ''}
        ${d.link && /^https?:\/\//.test(d.link) ? `<a class="linkish small" href="${esc(d.link)}" target="_blank" rel="noopener noreferrer">Read more</a>` : ''}</div></div>`).join('')
      || `<div class="muted small" style="padding:6px 0 4px">${I.updating ? '<span class="spinner"></span> Claude is looking for ideas that fit you. This takes a minute.' : S.status.ai_mode ? 'No ideas yet. Press New ideas.' : 'Claude needs Claude Code or an API key for ideas.'}</div>`}
    ${I.updating && ideas.length ? '<div class="muted small"><span class="spinner"></span> Fresh ideas are on the way.</div>' : ''}
    <p class="muted small opp-note">Ideas, not instructions: check them yourself, and only invest what fits your plan.</p>`;
  $$('[data-osig]').forEach(b => b.onclick = () => { const s = sig[+b.dataset.osig]; openChat({conv: 'opp-' + s.id.replace(/[^a-z0-9-]/gi, '-').slice(0, 60), ctx: {title: s.title, text: s.detail}}); CP.loading.then(() => { if (!CP.conv.messages.length) sendChat(s.ask, 'normal'); }); });
  $$('[data-oidea]').forEach(b => b.onclick = () => { const d = ideas[+b.dataset.oidea]; openChat({conv: 'idea-' + String(d.ticker || d.name || 'idea').replace(/[^a-z0-9-]/gi, '-').slice(0, 50), ctx: {title: d.title, text: `${d.name} (${d.ticker || 'no ticker'}): ${d.why} Risk: ${d.risk} Fits: ${d.fits}`}}); });
  $$('[data-owatch]').forEach(b => b.onclick = () => { const d = ideas[+b.dataset.owatch]; edit({section: 'watchlist', action: 'add', fields: {name: d.name || d.ticker, symbol: d.ticker, note: d.title}}, `Watching ${d.name || d.ticker}`).then(() => loadOpp().then(() => { drawOpp(); drawWatch(); })); });
  drawWatch();
  drawResearch();
}
function drawResearch() {
  // quiet help: only there when there is something to show, folded away until opened
  const R = (OPP && OPP.research) || {}, st = (R.stocks || []).filter(x => x.industry_pe), funds = (R.funds || []).filter(f => f.moves && f.moves.length);
  const wrap = $('#oppResearch'), box = $('#researchBody'); if (!wrap || !box) return;
  wrap.hidden = !st.length && !funds.length;
  const word = (pe, ind) => !pe ? '' : pe < ind * 0.8 ? 'cheaper' : pe > ind * 1.25 ? 'pricier' : 'in line';
  box.innerHTML = `${st.length ? `<div class="opp-h">Against their industry</div><div class="table-wrap"><table class="compact"><thead><tr><th>Stock</th><th>Industry</th><th class="num">P/E</th><th class="num">Industry P/E</th><th></th></tr></thead><tbody>
      ${st.map(x => `<tr><td><button type="button" class="nm linkish" data-open="holding:${esc(x.id)}">${esc(x.name)}</button></td><td class="muted small">${esc(x.industry)}</td><td class="num">${x.pe ?? '<span class="muted">·</span>'}</td><td class="num">${x.industry_pe}</td><td class="muted small">${word(x.pe, x.industry_pe)}</td></tr>`).join('')}</tbody></table></div>
      <div class="muted small">Industry figures for US companies, by Aswath Damodaran (NYU Stern). A rough yardstick, not a verdict.</div>` : ''}
    ${funds.length ? `<div class="opp-h">Well known investors, last quarter</div>${funds.map(f => `<div class="fund"><b>${esc(f.name)}</b> <span class="muted small">to ${fdate(f.quarter || '')}</span>
      <div class="small">${f.moves.filter(m => m.move !== 'sold').slice(0, 5).map(m => `<span class="${m.yours ? 'fund-yours' : ''}">${esc(m.holding || m.name.replace(/\b(INC|CORP|CO|LTD|PLC|NV|SA|AG|COM|CL [AB]|NEW|DEL)\b\.?/gi, '').trim().toLowerCase().replace(/\b\w/g, c => c.toUpperCase()))} <span class="muted">${m.move === 'new' ? 'new' : m.move === 'added' ? `+${m.change_pct}%` : `${m.change_pct}%`}</span></span>`).join(' · ')}</div></div>`).join('')}
      <div class="muted small">From their quarterly SEC filings (13F), which come out about six weeks after each quarter.</div>` : ''}`;
}
function watchCard() {
  return `<section class="card" data-card="adv-watch"><div class="card-head"><div><h2>Watchlist</h2><p class="sub">Investments you follow before you buy. Set a price and Claude flags it when it gets there.</p></div><button type="button" class="btn ghost sm" id="watchAdd">Add</button></div>
    <div id="watchBody"></div></section>`;
}
function drawWatch() {
  const box = $('#watchBody'); if (!box || !OPP) return;
  const W = OPP.watchlist || [];
  box.innerHTML = W.map((w, i) => `<div class="list-row watch-row"><div><b>${esc(w.name)}</b> <span class="muted small">${esc(w.symbol)}</span>
      <div class="muted small">${w.price != null ? `${eur(w.price, 2)}${w.since_added_pct != null ? ` · ${w.since_added_pct > 0 ? '+' : ''}${w.since_added_pct}% since you added it` : ''}${w.from_high_pct != null && w.from_high_pct < -1 ? ` · ${Math.abs(w.from_high_pct)}% below its high` : ''}` : 'Fetching prices…'}${w.buy_below ? ` · waiting for ${eur(w.buy_below, 2)}` : ''}</div></div>
      <div class="num">${w.spark && w.spark.length > 2 ? spark(w.spark, {w: 80, h: 24}) : ''}<button class="linkish small" data-wedit="${i}">Edit</button></div></div>`).join('')
    || '<div class="empty" style="padding:10px 0">Nothing yet. Press Watch on an idea, or Add.</div>';
  const fields = w => [{k: 'name', label: 'Name', type: 'text', value: w.name || ''}, {k: 'symbol', label: 'Ticker on Yahoo Finance, for example ASML.AS or IWDA.AS', type: 'text', value: w.symbol || ''},
    {k: 'buy_below', label: 'Tell me when it is below (€), optional', type: 'number', value: w.buy_below ?? ''}, {k: 'note', label: 'Note', type: 'text', value: w.note || ''}];
  const after = () => loadOpp().then(() => { drawOpp(); });
  $('#watchAdd').onclick = () => form('Add to watchlist', fields({}), v => edit({section: 'watchlist', action: 'add', fields: v}, 'Added').then(after));
  $$('[data-wedit]').forEach(b => b.onclick = () => { const i = +b.dataset.wedit, w = (S.watchlist || [])[i] || W[i];
    form('Edit ' + w.name, fields(w), v => edit({section: 'watchlist', index: i, fields: v}, 'Saved').then(after), () => edit({section: 'watchlist', action: 'delete', index: i}, 'Removed').then(after)); });
}
function wireOpp() {
  onSeg('ideaRisk', v => edit({section: 'profile', fields: {risk: v}}, 'Risk profile saved'));
  $$('[data-idea]').forEach(b => b.onclick = () => { openChat(); sendChat(b.dataset.idea, chatEffort() === 'deep' ? 'deep' : 'normal'); });
  $('#oppRefresh').onclick = async e => { e.currentTarget.disabled = true; await loadOpp(true); drawOpp(); };
  (OPP ? Promise.resolve(OPP) : loadOpp()).then(drawOpp);
  if (OPP) loadOpp().then(drawOpp);
}

/* questions Claude has for you: answered with one click where it can, otherwise in a short chat */
function myQuestions() {
  const pr = S.profile || {}, qs = [];
  for (const s of S.savings.filter(x => x.invest_unknown)) qs.push({id: 'inv:' + s.name, q: `Does ${s.name} count as an investment for you?`, sub: `${fmtV(s.value, "€")} at ${s.bank || 'your bank'}${s.rate_pct ? `, ${s.rate_pct}%` : ''}. Investments show on the Investments page.`,
    opts: [['yes', 'Investment'], ['no', 'Cash']], save: v => edit({section: 'savings', index: S.savings.indexOf(s), fields: {invest: v === 'yes'}}, 'Saved')});
  if (!pr.risk) qs.push({id: 'risk', q: 'How would you describe yourself as an investor?', sub: 'Careful: a big fall would keep you awake. Adventurous: you can sit through a 40% drop for a better long run.',
    opts: RISK, save: v => edit({section: 'profile', fields: {risk: v}}, 'Saved')});
  if (pr.horizon_years == null) qs.push({id: 'horizon', q: 'When will you need most of your invested money?', sub: 'This decides how much risk makes sense.',
    opts: [['2', 'Within 3 years'], ['7', 'In 3 to 10 years'], ['15', 'After 10 years or more']], save: v => edit({section: 'profile', fields: {horizon_years: +v}}, 'Saved')});
  if (pr.buffer_months == null) qs.push({id: 'buffer', q: 'How big a buffer do you want to keep in cash?', sub: S.spend_month ? `You spend about ${fmtV(S.spend_month, '€')} a month.` : 'In months of spending.',
    opts: [['3', '3 months'], ['6', '6 months'], ['12', 'A year']], save: v => edit({section: 'profile', fields: {buffer_months: +v}}, 'Saved')});
  if (!(S.goals || []).length && !pr.goals_text) qs.push({id: 'goals', q: 'What are you saving or investing for?', sub: 'A house, freedom to stop working earlier, a sabbatical, your kids… In your own words.',
    input: 'text', save: v => edit({section: 'profile', fields: {goals_text: v}}, 'Saved. Claude takes it into account.')});
  if (pr.monthly_invest_eur == null) qs.push({id: 'monthly', q: 'How much would you like to put aside or invest each month?', sub: 'An amount you can keep up. It drives the Plan page too.',
    input: 'number', save: v => edit({section: 'profile', fields: {monthly_invest_eur: +v}}, 'Saved')});
  if (!pr.retire_age) qs.push({id: 'retire', q: 'At what age would you like to be able to stop working?', input: 'number', save: v => edit({section: 'profile', fields: {retire_age: +v}}, 'Saved')});
  return qs;
}
function questionsCard() {
  const qs = myQuestions(), shown = qs.slice(0, 3);
  return `<section class="card qs-card" data-card="adv-questions"><div class="card-head"><div><h2>Questions for you</h2><p class="sub">${qs.length ? 'So the advice fits your life. Answer what you like, skip the rest.' : 'Claude knows the basics. Tell it more whenever something changes.'}</p></div>
      <button type="button" class="btn ghost" id="qChat"><span class="claude-mark sm">${CLAUDE_ICON}</span>${qs.length ? 'Talk it through' : 'Ask me more'}</button></div>
    ${shown.map((x, i) => `<div class="q-item"><div class="q-t">${esc(x.q)}</div>${x.sub ? `<div class="muted small">${esc(x.sub)}</div>` : ''}
      <div class="q-a">${x.opts ? x.opts.map(([v, l]) => `<button type="button" class="btn sm" data-qa="${i}" data-v="${esc(v)}">${esc(l)}</button>`).join('')
        : `<form class="q-form" data-qf="${i}"><input type="${x.input}" aria-label="${esc(x.q)}" ${x.input === 'number' ? 'min="0" step="1"' : ''}><button class="btn sm">Save</button></form>`}</div></div>`).join('')}
    ${qs.length > 3 ? `<div class="muted small">${qs.length - 3} more after these</div>` : ''}</section>`;
}
function wireQuestions() {
  const qs = myQuestions().slice(0, 3);
  $$('[data-qa]').forEach(b => b.onclick = () => qs[+b.dataset.qa].save(b.dataset.v));
  $$('[data-qf]').forEach(f => f.onsubmit = e => { e.preventDefault(); const v = $('input', f).value.trim(); if (v) qs[+f.dataset.qf].save(v); });
  $('#qChat').onclick = async () => {
    openChat({conv: 'goals-talk', ctx: {title: 'Your goals and situation', text: 'Get to know the owner better so the advice fits him.'}});
    await CP.loading;
    if (!CP.conv.messages.length) sendChat('Ask me a few questions, one at a time, to understand my goals, my situation and how I feel about risk. Save what you learn with buttons where you can.', 'normal');
  };
}
const TOPIC_ICON = {investing: ICON.up, savings: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><path d="M12 8v8M9 11h6"/></svg>', debt: ICON.back, spending: ICON.list};
function advicePage() {
  const recs = [...(S.advice || [])].sort((a, b) => ((b.impact_eur || b.impact_once_eur / 5 || 0) / (EFFORT_RANK[b.effort] || 3)) - ((a.impact_eur || a.impact_once_eur / 5 || 0) / (EFFORT_RANK[a.effort] || 3)));
  const have = new Set(S.todos.map(x => x.text.toLowerCase()));
  const done = S.advice_done || [], yearsSince = d => Math.max(0, (Date.now() - Date.parse(d)) / 31557600000);
  const savedSoFar = done.reduce((s, d) => s + (d.impact_eur || 0) * yearsSince(d.date), 0), perYear = recs.reduce((s, r) => s + (r.impact_eur || 0), 0);
  const convId = r => 'rec-' + String(r.id).replace(/[^a-z0-9-]/gi, '-').slice(0, 60);
  $('#view').innerHTML = `<div class="stack-y adv">
    <div class="grid g2">
      <div class="stack-y">
        ${oppCard()}
        <section class="card" data-card="adv-recs"><div class="card-head"><div><h2>Recommendations</h2><p class="sub">${perYear ? `Together worth about <b class="amt">${eur(perYear)}</b> a year. Best value for the effort first.` : 'Sorted by what they are worth for the effort.'}</p></div></div>
          ${recs.map((r, i) => `<article class="rec-card">
            <div class="rec-ic">${TOPIC_ICON[r.topic] || CLAUDE_ICON}</div>
            <div class="rec-body">
              <div class="rec-top"><div class="rec-t">${esc(r.title)}${r.custom ? ' <span class="tag">from chat</span>' : ''}</div>
                <div class="adv-chips">${r.impact_eur ? `<span class="chip-v good amt">${eur(r.impact_eur)} a year</span>` : r.impact_once_eur ? `<span class="chip-v good amt">${eur(r.impact_once_eur)} once</span>` : ''}${r.effort ? `<span class="chip-v">${esc(r.effort)}</span>` : ''}</div></div>
              <div class="muted small">${esc(r.detail || '')}</div>
              ${r.why ? `<details class="adv-why"><summary class="small">Why it matters</summary><div class="small">${esc(r.why)}</div></details>` : ''}
              <div class="adv-act"><button class="btn sm" data-talk="${i}" id="talk-${esc(convId(r))}"><span class="claude-mark sm">${CLAUDE_ICON}</span>Talk about it</button>
                ${r.action ? `<button class="btn primary sm" data-do="${i}">Do it</button>` : ''}
                ${r.todo ? (have.has(r.todo.toLowerCase()) ? '<span class="tag">On your list</span>' : `<button class="linkish small" data-rec="${i}">Add to do</button>`) : ''}
                <span class="adv-more"><button class="linkish small" data-done="${i}">Done</button>${r.custom ? '' : `<button class="linkish small muted" data-dismiss="${i}">Not for me</button>`}</span></div>
            </div></article>`).join('') || '<div class="empty">Nothing to flag right now. Nice.</div>'}
          ${(S.advice_dismissed || []).length ? `<details class="dismissed"><summary class="muted small">${S.advice_dismissed.length} you said were not for you</summary>
            ${S.advice_dismissed.map((d, i) => `<div class="list-row small"><div>${esc(d.title || d.id)}${d.reason ? `<div class="muted">${esc(d.reason)}</div>` : ''}</div><button class="btn ghost" data-restore="${i}">Bring back</button></div>`).join('')}</details>` : ''}
        </section>
        <section class="card" data-card="adv-done"><h2>Done</h2>${done.length ? `<p class="sub">About <b class="amt">${eur(savedSoFar)}</b> saved so far by what you did</p>${[...done].reverse().map((d, i) => `<div class="list-row small"><div><b>${esc(d.title)}</b><div class="muted">${fdate(d.date)}${d.impact_eur ? `, worth ${eur(d.impact_eur)} a year` : ''}</div></div><button class="btn ghost" data-undone="${done.length - 1 - i}">Undo</button></div>`).join('')}`
          : '<div class="empty" style="padding:12px 0">Mark a recommendation as done and it lands here, with what it has saved you.</div>'}</section>
      </div>
      <div class="stack-y">
        ${questionsCard()}
        ${watchCard()}
        <section class="card" data-card="adv-todo"><h2>To do</h2>
          <div id="todos">${S.todos.map((x, i) => `<div class="todo ${x.done ? 'done' : ''}"><input type="checkbox" data-todo="${i}" ${x.done ? 'checked' : ''} aria-label="Done"><span>${esc(x.text)}</span><button class="btn ghost" data-del-todo="${i}" aria-label="Remove">×</button></div>`).join('') || '<div class="empty" style="padding:12px 0">Nothing on your list.</div>'}</div>
          <form id="addTodo" class="controls" style="margin:14px 0 0"><input type="text" id="todoText" placeholder="Add a to do" style="flex:1" aria-label="New to do"><button class="btn primary">Add</button></form>
        </section>
      </div>
    </div></div>`;
  wireOpp();
  wireQuestions();
  // recommendations already talked about say so
  fetch('/api/chats', {cache: 'no-store'}).then(r => r.json()).then(list => { for (const c of list || []) { const b = document.getElementById('talk-' + c.id); if (b) b.lastChild.textContent = `Continue (${c.count})`; } }).catch(() => {});
  $$('[data-talk]').forEach(b => b.onclick = () => talkAbout(recs[+b.dataset.talk]));
  $$('[data-do]').forEach(b => b.onclick = e => { const a = recs[+b.dataset.do].action; if (a.kind === 'chat') openChat({text: a.text, send: true}); else openThing(a, e); });
  $$('[data-rec]').forEach(b => b.onclick = () => edit({section: 'todos', action: 'add', fields: {text: recs[+b.dataset.rec].todo}}, 'Added to your list'));
  $$('[data-done]').forEach(b => b.onclick = () => { const r = recs[+b.dataset.done]; edit({section: 'advice_done', action: 'add', fields: {id: r.id, title: r.title, impact_eur: r.impact_eur, date: today()}}, 'Nice. Moved to done.'); });
  $$('[data-undone]').forEach(b => b.onclick = () => edit({section: 'advice_done', action: 'delete', index: +b.dataset.undone}, 'Moved back'));
  $$('[data-dismiss]').forEach(b => b.onclick = () => { const r = recs[+b.dataset.dismiss]; edit({section: 'advice_dismissed', action: 'add', fields: {id: r.id, title: r.title, reason: 'Not for me'}}, 'Okay, hidden'); });
  $$('[data-restore]').forEach(b => b.onclick = () => edit({section: 'advice_dismissed', action: 'delete', index: +b.dataset.restore}, 'Brought back'));
  $$('[data-todo]').forEach(c => c.onchange = () => edit({section: 'todos', index: +c.dataset.todo, fields: {done: c.checked}}, c.checked ? 'Marked done' : 'Reopened'));
  $$('[data-del-todo]').forEach(b => b.onclick = () => edit({section: 'todos', action: 'delete', index: +b.dataset.delTodo}, 'Removed'));
  $('#addTodo').onsubmit = e => { e.preventDefault(); const v = $('#todoText').value.trim(); if (v) edit({section: 'todos', action: 'add', fields: {text: v}}, 'Added'); };
}

/* ---------- import: coverage and log, around the existing upload ---------- */
const EXPORT_HOW = [
  [/abn|ABNA/i, 'ABN AMRO: Internet Banking on a computer, Download transactions, TXT or CSV, choose the period.'],
  [/ics|credit/i, 'Credit card (ICS): icscards.nl, Transactions, Download, choose the period.'],
  [/trade republic/i, 'Trade Republic: Profile, Transaction export. It covers everything, so one export fills every gap.'],
  [/paypal/i, 'PayPal: Activity, Download, CSV, choose the period.'],
  [/degiro/i, 'DEGIRO: Inbox, Account overview, choose the period, export CSV. A yearly overview PDF works too.'],
  [/ing|INGB/i, 'ING: Mijn ING, Af en bij, Download, CSV.'],
  [/revolut/i, 'Revolut: the account, Statement, Excel or CSV, choose the period.'],
];
const howToExport = name => (EXPORT_HOW.find(([re]) => re.test(name)) || [null, 'Download a statement or export for that period from the bank or broker, then drop it here.'])[1];
function importView() {
  importPage();
  const box = $('#importExtras'); if (!box) return;
  box.innerHTML = `<section class="card"><div class="card-head"><h2>What your data covers</h2><span class="muted small">Last 24 months. Click a gap to see what to export.</span></div><div id="coverage"><div class="skel-line"></div></div></section>
    <section class="card"><h2>Import log</h2><div id="ilog"><div class="skel-line"></div></div></section>`;
  drawCoverage(); drawLog();
}
async function drawCoverage() {
  await ensureSpending().catch(() => {});
  const daily = await loadAcctDaily();
  const months = []; for (let i = 23; i >= 0; i--) { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - i); months.push(isoD(d).slice(0, 7)); }
  const rows = [];
  if (SP.d) for (const id of Object.keys(SP.d.accounts)) { const have = new Set(SP.d.transactions.filter(t => t.account === id).map(t => t.date.slice(0, 7))); if (have.size) rows.push({name: acctName(id), id, have, kind: 'Payments'}); }
  for (const a of [...S.accounts.map(a => a.name), S.managed.name, ...S.savings.map(s => s.name)]) {
    const have = new Set([...(S.account_history || []).filter(r => r.account === a).map(r => r.date.slice(0, 7)), ...(daily[a] || []).map(r => r.date.slice(0, 7))]);
    rows.push({name: a, have, kind: S.savings.some(s => s.name === a) ? 'Savings' : 'Investments'});
  }
  const box = $('#coverage'); if (!box) return;
  box.innerHTML = `<div class="cov"><div class="cov-head"><span></span>${months.map((m, i) => `<span>${i % 3 === 0 ? mLabel(m) : ''}</span>`).join('')}</div>
    ${rows.map((r, ri) => { const first = months.find(m => r.have.has(m)), last = [...months].reverse().find(m => r.have.has(m));
      return `<div class="cov-row"><span class="cov-name"><b>${esc(r.name)}</b><span class="muted small">${r.kind}</span></span>${months.map(m => {
        // payments should cover every month; investments and savings need at least a year end value
        const has = r.have.has(m), gap = !has && first && m > first && (r.kind === 'Payments' ? true : m.endsWith('-12') && m < isoD(new Date()).slice(0, 7));
        return `<span class="cov-c ${has ? 'on' : gap ? 'gap' : ''}" ${gap ? `data-gap="${ri}|${m}" data-tip="${esc(`${r.name}: nothing for ${fdate(m)}`)}"` : has ? `data-tip="${esc(`${r.name}: ${fdate(m)}`)}"` : ''}></span>`; }).join('')}</div>`; }).join('')}</div>
    <div class="cov-legend muted small"><i class="on"></i> has data <i class="gap"></i> missing <i></i> before the first data</div>`;
  attachTips(box, box);
  box.onclick = e => { const g = e.target.closest('[data-gap]'); if (!g) return; const [ri, m] = g.dataset.gap.split('|'), r = rows[+ri];
    openMenu(null, `<div class="menu-sec" style="max-width:320px;padding:10px 12px"><b>${esc(r.name)}, ${fdate(m)}</b><p class="small" style="margin:6px 0">${esc(howToExport(r.name + ' ' + (r.id || '')))}</p><a class="btn sm" href="#import" onclick="closeMenus()">Drop the file above</a></div>`, '', {x: e.clientX, y: e.clientY}); };
}
async function drawLog() {
  const box = $('#ilog'); if (!box) return;
  let imps = [];
  try { imps = await (await fetch('/api/imports', {cache: 'no-store'})).json(); } catch {}
  const sp = SP.d ? SP.d.imports.map(i => ({date: i.date + 'T00:00', files: [i.file], summary: `${i.added} payments, ${fdate(i.from)} to ${fdate(i.to)}`, sid: i.id})) : [];
  const all = [...imps, ...sp].sort((a, b) => b.date.localeCompare(a.date));
  box.innerHTML = all.length ? all.slice(0, 60).map((i, k) => `<div class="list-row small"><div style="min-width:0"><b>${esc(i.files.join(', '))}</b><div class="muted log-sum">${fdate(i.date.slice(0, 10))}${i.kind === 'chat' ? ', from the chat' : ''}. ${esc(i.summary.slice(0, 220))}</div></div>
      ${i.sid ? `<button class="btn ghost danger sm" data-rmimp="${i.sid}">Remove</button>` : `<button class="btn ghost sm" data-undoimp="${esc(i.id)}" data-first="${k === all.findIndex(x => !x.sid) ? 1 : 0}">Undo</button>`}</div>`).join('')
    : '<div class="empty">Nothing imported yet.</div>';
  $$('[data-rmimp]', box).forEach(b => b.onclick = () => { if (confirmTwice('imp' + b.dataset.rmimp, 'Click Remove again to delete the payments of this import.')) spEdit({action: 'import-delete', id: b.dataset.rmimp}, 'Import removed').then(drawLog); });
  $$('[data-undoimp]', box).forEach(b => b.onclick = async () => {
    if (!confirmTwice('u' + b.dataset.undoimp, b.dataset.first === '1' ? 'Click Undo again to undo this import.' : 'This also undoes every change made after it. Click Undo again to go ahead.')) return;
    try { await post('/api/undo', {id: b.dataset.undoimp}); toast('Import undone'); await load(); SP.d = null; importView(); } catch (e) { toast(e.message); }
  });
}

/* ---------- settings ---------- */
async function settings() {
  settingsBase();
  const box = $('#settingsExtras'); if (!box) return;
  const p = S ? S.profile || {} : {}, pr = UIS.prefs || {};
  let usage = {};
  try { usage = await (await fetch('/api/ai-usage', {cache: 'no-store'})).json(); } catch {}
  const months = Object.keys(usage).sort().slice(-6), cur = usage[isoD(new Date()).slice(0, 7)] || {};
  const KIND0 = {chat: 'Chat answers', import: 'Imports', categorise: 'Categorising', note: 'Payment conversations', places: 'Countries', briefing: 'Daily briefing', holding: 'Investment notes', news: 'News picks', ideas: 'Investment ideas', classify: 'Grouping investments', spending: 'Other'};
  const KIND = new Proxy(KIND0, {get: (o, k) => typeof k === 'string' && k.endsWith('-local') ? `${o[k.slice(0, -6)] || k.slice(0, -6)}, on this computer` : o[k]});
  box.innerHTML = `<section class="card"><h2>About you</h2><p class="sub">Used for the plan, the advice and what Claude knows about you.</p>
      <form id="profForm" class="prof">
        <label class="field">Birth year<input type="number" name="birth_year" value="${esc(p.birth_year ?? '')}" placeholder="1995"></label>
        <label class="field">Want to stop working at age<input type="number" name="retire_age" value="${esc(p.retire_age ?? '')}" placeholder="60"></label>
        <label class="field">Household<input type="text" name="household" value="${esc(p.household || '')}" placeholder="Single, partner, children"></label>
        <label class="field">Risk you are comfortable with<select name="risk">${[['', 'Not set'], ['low', 'Low: steady over growth'], ['medium', 'Medium'], ['high', 'High: growth over steady']].map(([v, l]) => `<option value="${v}" ${p.risk === v ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
        <label class="field">Best savings rate you could get elsewhere (%)<input type="number" step="0.01" name="compare_rate_pct" value="${esc(p.compare_rate_pct ?? '')}"></label>
        <label class="field">Benchmark for your investments<input type="text" name="benchmark" value="${esc(p.benchmark || 'IWDA.AS')}" placeholder="IWDA.AS"></label>
        <label class="field" style="grid-column:1/-1">Goals in your own words<textarea name="goals_text" rows="2" placeholder="For example: buy a house in 2029, keep a year of expenses as a buffer">${esc(p.goals_text || '')}</textarea></label>
        <div><button class="btn primary">Save</button></div></form></section>
    <section class="card"><h2>Notifications</h2>
      <div class="pref-row"><span>Claude's briefing on the home page</span>${seg('pBrief', [['daily', 'Daily'], ['weekly', 'Weekly'], ['off', 'Off']], pr.briefing || 'daily')}</div>
      <label class="check pref-row"><input type="checkbox" id="pCel" ${pr.celebrations !== false ? 'checked' : ''}> Celebrate milestones (net worth, debt free, goals)</label>
      <label class="check pref-row"><input type="checkbox" id="pStale" ${pr.stale_reminders !== false ? 'checked' : ''}> Remind me when bank data gets old</label></section>
    <section class="card"><h2>AI use</h2><p class="sub">How often Claude was asked to do something. With Claude Code this counts toward your Claude plan; with an API key it is billed per use.</p>
      <div class="pref-row"><span>How hard Claude thinks in the chat</span>${seg('pEffort', EFFORTS.map(([v, l]) => [v, l]), pr.effort || 'auto')}</div>
      <p class="muted small">Auto answers simple lookups with a quick model and the rest with a normal one. Claude only reads through your data files when you ask it to change something, or on Deep. You can change it per question in the chat, and every answer offers Think harder.</p>
      ${Object.keys(cur).length ? `<div class="kv">${Object.entries(cur).sort((a, b) => b[1] - a[1]).map(([k, n]) => `<span>${esc(KIND[k] || k)}</span><span>${n}</span>`).join('')}<span><b>This month</b></span><span><b>${Object.values(cur).reduce((a, b) => a + b, 0)}</b></span></div>` : '<div class="empty" style="padding:10px 0">Nothing yet this month.</div>'}
      ${months.length > 1 ? chartHtml({type: 'bar', unit: '', labels: months.map(mLabel), series: [{name: 'Requests', values: months.map(m => Object.values(usage[m]).reduce((a, b) => a + b, 0))}]}, 420) : ''}</section>
    <section class="card"><h2>Export</h2><p class="sub">Your data as files, to keep or to open elsewhere.</p>
      <div class="controls" style="margin:0"><a class="btn" href="/api/export?what=all">Everything (JSON)</a><a class="btn" href="/api/export?what=transactions">Transactions (CSV)</a><a class="btn" href="/api/export?what=holdings">Investments (CSV)</a></div></section>
    <section class="card" data-card="set-local"><h2>Model on this computer</h2><p class="sub">Small, frequent jobs (countries, the briefing, grouping investments, news picks, categorising) can run on a free model on your own computer with <a href="https://ollama.com" target="_blank" rel="noopener noreferrer">Ollama</a>. Nothing leaves the computer and it saves your Claude usage. When it isn't running, Claude does them.</p>
      <div id="localBox"><div class="skel-line"></div></div></section>
    <section class="card" data-card="set-public"><h2>Public data</h2><p class="sub">Interest rates and inflation come from the ECB, company figures from the SEC. Both are free and official. The SEC asks callers for a contact email.</p>
      <form id="contactForm" class="controls" style="margin:0"><input type="email" id="contactEmail" placeholder="Your email, sent only to the SEC" style="flex:1" aria-label="Contact email"><button class="btn">Save</button></form></section>
    <section class="card"><h2>Layout</h2><p class="sub">Drag any card by its grip (top right, next to the title) to move it. Every page remembers its own arrangement.</p>
      <button type="button" class="btn" id="layoutReset">Put every page back</button></section>`;
  $('#layoutReset').onclick = () => resetLayout(true);
  $('#contactForm').onsubmit = async e => { e.preventDefault(); try { await post('/api/settings', {contact_email: $('#contactEmail').value}); toast('Saved'); } catch (err) { toast(err.message); } };
  fetch('/api/local-ai', {cache: 'no-store'}).then(r => r.json()).then(L => {
    const box = $('#localBox'); if (!box) return;
    box.innerHTML = L.models.length ? `<div class="pref-row"><span>Use it for small jobs</span>${seg('pLocal', [['auto', 'On'], ['off', 'Off']], L.mode || 'auto')}</div>
      <div class="pref-row"><span>Model</span><select id="pLocalModel" aria-label="Local model">${L.models.map(m => `<option ${m === L.model ? 'selected' : ''}>${esc(m)}</option>`).join('')}</select></div>`
      : '<p class="muted small">Ollama isn\'t running on this computer. Install it from ollama.com, then run <code>ollama pull qwen2.5:7b</code> once. The app finds it by itself.</p>';
    onSeg('pLocal', v => uiPost({action: 'prefs', prefs: {local_ai: v}}, v === 'off' ? 'Small jobs go to Claude' : 'Small jobs run on this computer'));
    if ($('#pLocalModel')) $('#pLocalModel').onchange = e => uiPost({action: 'prefs', prefs: {local_model: e.target.value}}, 'Saved');
  }).catch(() => {});
  $('#profForm').onsubmit = e => { e.preventDefault(); const f = Object.fromEntries(new FormData(e.target)); edit({section: 'profile', fields: f}, 'Saved').then(() => { if (view === 'settings') settings(); }); };
  onSeg('pEffort', v => { CP.effort = null; store.set('chat.effort', null); uiPost({action: 'prefs', prefs: {effort: v}}, 'Saved'); });
  onSeg('pBrief', v => { uiPost({action: 'prefs', prefs: {briefing: v}}, 'Saved').then(() => { HOME.brief = null; $$('[data-seg="pBrief"] button').forEach(b => b.setAttribute('aria-pressed', b.dataset.v === v)); }); });
  $('#pCel').onchange = e => uiPost({action: 'prefs', prefs: {celebrations: e.target.checked}}, 'Saved');
  $('#pStale').onchange = e => uiPost({action: 'prefs', prefs: {stale_reminders: e.target.checked}}, 'Saved');
}
