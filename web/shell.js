'use strict';
/* Everything shared by all pages: the Claude panel, search (⌘K), right-click menus, the date range, saved views,
   card tools (ask, full screen, download), drag and drop, shortcuts, focus mode, milestones. Uses app.js helpers. */

window.GEO = null;
const PICKS = {};  // clickable chart id -> (i, k) => popover spec


function markPicked(pt) {
  clearPicked();
  const chart = pt.closest('.c-box') || pt.closest('[data-pick]');
  if (chart) chart.classList.add('picking');
  pt.classList.add('picked');
}
function clearPicked() {
  document.querySelectorAll('.picking').forEach(b => b.classList.remove('picking'));
  document.querySelectorAll('[data-pt].picked').forEach(p => p.classList.remove('picked'));
}
const UIS = {views: [], pins: [], celebrated: [], prefs: {}};
async function loadUI() {
  try { Object.assign(UIS, await (await fetch('/api/ui', {cache: 'no-store'})).json()); } catch {}
  renderViews();
}
async function uiPost(body, msg) {
  try { Object.assign(UIS, await post('/api/ui', body)); if (msg) toast(msg); renderViews(); return true; }
  catch (e) { toast(e.message); return false; }
}
async function loadGeo() {
  if (window.GEO) return window.GEO;
  try { window.GEO = await (await fetch('countries.json')).json(); } catch { window.GEO = {countries: {}, w: 1000, h: 487}; }
  return window.GEO;
}
/* public data (ECB rates and inflation, company figures): loaded once in a while, shown only where it helps */
let ECON = null, ECON_AT = 0, FUND = null;
async function loadEcon() {
  if (!ECON || Date.now() - ECON_AT > 3600e3) { try { ECON = await (await fetch('/api/economy', {cache: 'no-store'})).json(); ECON_AT = Date.now(); } catch { ECON = ECON || {}; } }
  return ECON;
}
async function loadFund() {
  if (!FUND) { try { FUND = await (await fetch('/api/fundamentals', {cache: 'no-store'})).json(); } catch { FUND = {}; } }
  return FUND;
}
async function ensureSpending() { if (!SP.d) await loadSpending(); return SP.d; }
const ago = iso => {
  if (!iso) return '';
  const s = (Date.now() - Date.parse(iso)) / 1000;
  if (s < 90) return 'just now';
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  const d = Math.round(s / 86400);
  return d < 45 ? `${d} day${d === 1 ? '' : 's'} ago` : fdate(iso.slice(0, 10));
};
const agoPill = (iso, prefix = 'updated') => iso ? `<span class="ago" title="${esc(fdate(iso.slice(0, 10)))}">${prefix} ${ago(iso)}</span>` : '';

/* ---------- the shared date range ---------- */
const RANGE = {p: store.get('range.p', '12m'), from: store.get('range.from', ''), to: store.get('range.to', ''), cmp: store.get('range.cmp', ''), g: store.get('range.g', 'auto')};
const RANGE_PAGES = ['overview', 'spending', 'holdings', 'account'];
const PRESETS = [['month', 'This month'], ['3m', 'Last 3 months'], ['12m', 'Last 12 months'], ['ytd', 'This year'], ['all', 'All time']];
const isoD = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
function rangeFor(p = RANGE.p, anchor = new Date()) {
  // {from, to, label, prev} ; to '9999-12-31' means open ended
  const y = anchor.getFullYear(), m = anchor.getMonth();
  const back = n => isoD(new Date(y, m - n + 1, 1));
  let r;
  if (p === 'month') r = {from: isoD(new Date(y, m, 1)), to: isoD(new Date(y, m + 1, 0)), prev: [isoD(new Date(y, m - 1, 1)), isoD(new Date(y, m, 0))]};
  else if (p === '3m') r = {from: back(3), to: '9999-12-31', prev: [back(6), isoD(new Date(y, m - 2, 0))]};
  else if (p === '12m') r = {from: back(12), to: '9999-12-31', prev: [back(24), isoD(new Date(y, m - 11, 0))]};
  else if (p === 'ytd') r = {from: `${y}-01-01`, to: '9999-12-31', prev: [`${y - 1}-01-01`, `${y - 1}-${String(m + 1).padStart(2, '0')}-${String(anchor.getDate()).padStart(2, '0')}`]};
  else if (p.startsWith('y:')) { const yy = +p.slice(2); r = {from: `${yy}-01-01`, to: `${yy}-12-31`, prev: [`${yy - 1}-01-01`, `${yy - 1}-12-31`]}; }
  else if (p === 'custom' && RANGE.from) {
    const a = new Date(RANGE.from + 'T12:00'), b = new Date((RANGE.to || isoD(new Date())) + 'T12:00'), days = Math.round((b - a) / 864e5);
    r = {from: RANGE.from, to: RANGE.to || '9999-12-31', prev: [isoD(new Date(a - (days + 1) * 864e5)), isoD(new Date(a - 864e5))]};
  } else r = {from: '0000-01-01', to: '9999-12-31', prev: null};
  r.label = rangeLabel(p);
  if (RANGE.cmp === 'yoy' && r.from !== '0000-01-01') {
    const shift = s => s.startsWith('9999') ? isoD(new Date(y - 1, m, anchor.getDate())) : `${+s.slice(0, 4) - 1}${s.slice(4)}`;
    r.cmp = {from: shift(r.from), to: shift(r.to), label: 'same period last year'};
  } else if (RANGE.cmp === 'prev' && r.prev) r.cmp = {from: r.prev[0], to: r.prev[1], label: 'the period before'};
  return r;
}
/* bars per day, week, month or year; auto picks what fits the period */
const GRAINS = [['auto', 'Auto'], ['day', 'Day'], ['week', 'Week'], ['month', 'Month'], ['year', 'Year']];
function grainFor(from, to, g = RANGE.g) {
  const days = (Date.parse(to + 'T12:00') - Date.parse(from + 'T12:00')) / 864e5;
  if (g && g !== 'auto') return days / {day: 1, week: 7, month: 30.4, year: 365}[g] > 400 ? (days > 4000 ? 'year' : 'month') : g;
  return days <= 45 ? 'day' : days <= 120 ? 'week' : days <= 1100 ? 'month' : 'year';
}
function bucketer(grain) {
  // key(iso date) → bucket, plus a label, the dates it spans and the next bucket
  const monday = iso => { const d = new Date(iso + 'T12:00'); d.setDate(d.getDate() - (d.getDay() + 6) % 7); return isoD(d); };
  const addDays = (iso, n) => { const d = new Date(iso + 'T12:00'); d.setDate(d.getDate() + n); return isoD(d); };
  const short = iso => `${+iso.slice(8, 10)} ${MONTHS[+iso.slice(5, 7) - 1]}`;
  if (grain === 'day') return {grain, key: iso => iso, label: short, span: b => ({from: b, to: b}), next: b => addDays(b, 1), noun: 'day'};
  if (grain === 'week') return {grain, key: monday, label: b => 'wk ' + short(b), span: b => ({from: b, to: addDays(b, 6)}), next: b => addDays(b, 7), noun: 'week'};
  if (grain === 'year') return {grain, key: iso => iso.slice(0, 4), label: b => b, span: b => ({from: `${b}-01-01`, to: `${b}-12-31`}), next: b => String(+b + 1), noun: 'year'};
  return {grain: 'month', key: iso => iso.slice(0, 7), label: b => `${MONTHS[+b.slice(5, 7) - 1]} ${b.slice(2, 4)}`, span: b => ({from: `${b}-01`, to: `${b}-31`}),
    next: b => { const y = +b.slice(0, 4), m = +b.slice(5, 7); return m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, '0')}`; }, noun: 'month'};
}
function bucketsBetween(B, first, last) {
  // every bucket from the first to the last date, so a quiet week shows as an empty bar
  const out = [];
  for (let b = B.key(first), end = B.key(last); b <= end && out.length < 1500; b = B.next(b)) out.push(b);
  return out;
}
function rangeLabel(p = RANGE.p) {
  const pre = PRESETS.find(x => x[0] === p);
  if (pre) return pre[1];
  if (p.startsWith('y:')) return p.slice(2);
  if (p === 'custom' && RANGE.from) return `${fdate(RANGE.from)} to ${RANGE.to ? fdate(RANGE.to) : 'today'}`;
  return 'All time';
}
function setRange(p, extra = {}) {
  Object.assign(RANGE, {p}, extra);
  for (const k of ['p', 'from', 'to', 'cmp', 'g']) store.set('range.' + k, RANGE[k]);
  renderRangeSlot();
  closeMenus();
  if (view === 'spending') spendingPage(); else renderView();
}
function rangeYears() {
  const ys = new Set((S && S.history || []).map(h => h.date.slice(0, 4)));
  if (SP.d) SP.d.transactions.forEach(t => ys.add(t.date.slice(0, 4)));
  return [...ys].sort().reverse();
}
function renderRangeSlot() {
  const slot = $('#rangeSlot');
  if (!slot) return;
  const on = RANGE_PAGES.includes(view);
  slot.hidden = !on;
  if (!on) return;
  slot.innerHTML = `<button type="button" class="range-btn" id="rangeBtn" aria-haspopup="true"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/></svg>${esc(rangeLabel())}${RANGE.cmp ? `<span class="cmp-tag">vs ${RANGE.cmp === 'yoy' ? 'last year' : 'before'}</span>` : ''}${RANGE.g && RANGE.g !== 'auto' ? `<span class="cmp-tag">per ${RANGE.g}</span>` : ''}</button>`;
  $('#rangeBtn').onclick = e => { e.stopPropagation(); openRangeMenu(); };
}
function openRangeMenu() {
  const years = rangeYears();
  const row = (v, l) => `<button type="button" class="menu-row ${RANGE.p === v ? 'on' : ''}" data-rg="${v}">${RANGE.p === v ? '<b class="ck">✓</b>' : '<span class="ck"></span>'}${esc(l)}</button>`;
  const menu = openMenu($('#rangeBtn'), `<div class="menu-sec">${PRESETS.map(([v, l]) => row(v, l)).join('')}</div>
    ${years.length ? `<div class="menu-sec menu-years">${years.slice(0, 6).map(y => `<button type="button" class="chipbtn ${RANGE.p === 'y:' + y ? 'on' : ''}" data-rg="y:${y}">${y}</button>`).join('')}</div>` : ''}
    <div class="menu-sec"><div class="menu-h">Custom</div><div class="menu-custom"><input type="date" id="rgFrom" value="${esc(RANGE.from || '')}" aria-label="From"><span class="muted">to</span><input type="date" id="rgTo" value="${esc(RANGE.to || '')}" aria-label="To"><button type="button" class="btn" id="rgApply">Apply</button></div></div>
    <div class="menu-sec"><div class="menu-h">Compare with</div>${[['', 'Nothing'], ['prev', 'The period before'], ['yoy', 'Same period last year']].map(([v, l]) =>
      `<button type="button" class="menu-row ${RANGE.cmp === v ? 'on' : ''}" data-cmp="${v}">${RANGE.cmp === v ? '<b class="ck">✓</b>' : '<span class="ck"></span>'}${l}</button>`).join('')}</div>
    <div class="menu-sec"><div class="menu-h">Bars per</div><div class="menu-years">${GRAINS.map(([v, l]) => `<button type="button" class="chipbtn ${RANGE.g === v ? 'on' : ''}" data-grain="${v}">${l}</button>`).join('')}</div></div>`, 'range-menu');
  $$('[data-grain]', menu).forEach(b => b.onclick = () => setRange(RANGE.p, {g: b.dataset.grain}));
  $$('[data-rg]', menu).forEach(b => b.onclick = () => setRange(b.dataset.rg));
  $$('[data-cmp]', menu).forEach(b => b.onclick = () => setRange(RANGE.p, {cmp: b.dataset.cmp}));
  $('#rgApply', menu).onclick = () => { const f = $('#rgFrom', menu).value, t = $('#rgTo', menu).value; if (f) setRange('custom', {from: f, to: t}); };
}

/* ---------- small menus (range, views, card downloads, right click) ---------- */
function openMenu(anchor, html, cls = '', at = null) {
  closeMenus();
  const m = document.createElement('div');
  m.className = 'menu ' + cls;
  m.innerHTML = html;
  document.body.appendChild(m);
  const r = anchor ? anchor.getBoundingClientRect() : {left: at.x, right: at.x, bottom: at.y, top: at.y};
  const W = m.offsetWidth, H = m.offsetHeight;
  let x = at ? at.x : r.right - W, y = (at ? at.y : r.bottom) + 6;
  x = Math.max(8, Math.min(x, innerWidth - W - 8));
  if (y + H > innerHeight - 8) y = Math.max(8, (at ? at.y : r.top) - H - 6);
  m.style.left = x + 'px'; m.style.top = y + 'px';
  setTimeout(() => document.addEventListener('mousedown', menuOutside));
  return m;
}
function menuOutside(e) { if (!e.target.closest('.menu')) closeMenus(); }
function closeMenus() { $$('.menu').forEach(m => m.remove()); document.removeEventListener('mousedown', menuOutside); }

/* ---------- saved views ---------- */
function viewState() {
  return {hash: location.hash || '#overview', range: {...RANGE}, sp: {tab: SP.tab, accts: [...SP.accts], focus: [...SP.focus], tx: {...SP.tx}}, hold: {...ui.hold}};
}
function applyView(v) {
  const s = v.state || {};
  if (s.range) Object.assign(RANGE, s.range);
  for (const k of ['p', 'from', 'to', 'cmp', 'g']) store.set('range.' + k, RANGE[k]);
  if (s.sp) { SP.tab = s.sp.tab || SP.tab; SP.accts = s.sp.accts || (s.sp.acct && s.sp.acct !== 'all' ? [s.sp.acct] : []); SP.focus = s.sp.focus || []; Object.assign(SP.tx, s.sp.tx || {}); }
  if (s.hold) Object.assign(ui.hold, s.hold);
  if (location.hash === s.hash) route(); else location.hash = s.hash || '#overview';
}
function renderViews() {
  const box = $('#navViews');
  if (!box) return;
  box.innerHTML = UIS.views.length ? `<div class="nav-h">Saved views</div>${UIS.views.map(v => `<div class="nav-view"><button type="button" data-view="${v.id}">${esc(v.name)}</button><button type="button" class="x-btn" data-unview="${v.id}" aria-label="Remove ${esc(v.name)}">×</button></div>`).join('')}` : '';
  $$('[data-view]', box).forEach(b => b.onclick = () => applyView(UIS.views.find(v => v.id === b.dataset.view)));
  $$('[data-unview]', box).forEach(b => b.onclick = () => uiPost({action: 'view-delete', id: b.dataset.unview}, 'View removed'));
}
function openViewsMenu() {
  const m = openMenu($('#viewsBtn'), `<div class="menu-sec"><div class="menu-h">Save this view</div>
      <form class="menu-custom" id="vwForm"><input type="text" id="vwName" placeholder="For example: Groceries this year" aria-label="Name"><button class="btn primary">Save</button></form>
      <div class="muted small" style="margin-top:6px">Keeps this page with its period, account and filters.</div></div>
    ${UIS.views.length ? `<div class="menu-sec">${UIS.views.map(v => `<button type="button" class="menu-row" data-view="${v.id}"><span class="ck"></span>${esc(v.name)}</button>`).join('')}</div>` : ''}`, 'views-menu');
  setTimeout(() => $('#vwName', m).focus());
  $('#vwForm', m).onsubmit = async e => { e.preventDefault(); if (await uiPost({action: 'view-add', name: $('#vwName', m).value, state: viewState()}, 'View saved')) closeMenus(); };
  $$('[data-view]', m).forEach(b => b.onclick = () => { closeMenus(); applyView(UIS.views.find(v => v.id === b.dataset.view)); });
}

/* ---------- the Claude panel ---------- */
const CP = {open: false, conv: {id: null, messages: []}, busy: false, steps: [], error: null, files: [], ctx: null, mode: 'chat', q: '', list: []};
const STARTERS_BY = {
  overview: ['How am I doing overall?', 'What changed in my net worth this month?', 'What should I do with my money this month?'],
  spending: ['Where can I spend less without noticing?', 'Which subscriptions could I cancel?', 'How does this month compare to my average?'],
  holdings: ['Is my portfolio well diversified?', 'Which of my investments look expensive or cheap?', 'What does the recent news mean for my investments?', 'How did my investments do against the market?'],
  accounts: ['Which account is doing best?', 'Should I consolidate my accounts?', 'How much did I pay in costs this year?'],
  account: ['How is this account doing?', 'What did this account cost me?', 'Should I keep this account?'],
  cash: ['Is my cash earning enough interest?', 'How big should my emergency fund be?', 'Should I repay my loan early or keep saving?'],
  history: ['What was my best year and why?', 'How fast is my wealth growing?', 'Where did most of my growth come from?'],
  plan: ['When could I stop working?', 'Am I on track for my goals?', 'How much should I save each month?'],
  taxes: ['How much box 3 tax will I pay?', 'Can I lower my box 3 tax?', 'What do I need for my tax return?'],
  advice: ['Which of these should I do first?', 'Explain the biggest recommendation', 'What am I missing?'],
  import: ['Which files should I import to complete my data?', 'Is any of my data out of date?'],
  settings: ['What does the app know about me?'],
};
const TOPIC_ORDER = ['Spending', 'Investing', 'Savings & debt', 'Planning', 'Taxes', 'General'];
function openChat({text = '', ctx = null, send = false, files = null, conv = null} = {}) {
  CP.open = true; CP.mode = 'chat';
  if (conv && CP.conv.id !== conv) {
    // a conversation of its own, for example about one recommendation: picked up where it was left
    CP.conv = {id: conv, title: ctx && ctx.title, messages: []}; CP.error = null;
    CP.loading = fetch('/api/chats/get?id=' + encodeURIComponent(conv), {cache: 'no-store'}).then(r => r.json()).then(c => {
      if (c && c.messages && CP.conv.id === conv && !CP.conv.messages.length) { CP.conv.messages = c.messages; renderChat(); }
    }).catch(() => {});
  }
  if (ctx) CP.ctx = ctx;
  if (files) CP.files.push(...files);
  document.body.classList.add('chat-open');
  renderChat();
  const q = $('#cpQ');
  if (text && send) sendChat(text);
  else if (q) { q.value = text || q.value; setTimeout(() => q.focus(), 60); }
}
function closeChat() { CP.open = false; document.body.classList.remove('chat-open'); const p = $('#chatPanel'); if (p) p.hidden = true; }
function newChat() { CP.conv = {id: null, messages: []}; CP.error = null; CP.ctx = null; CP.mode = 'chat'; renderChat(); }
function deliverInbox() {
  // Claude's open questions after an import go into the conversation, once
  const items = (S && S.inbox || []).filter(i => !CP.conv.messages.some(m => m.inbox === i.id));
  if (!items.length || CP.busy) return false;
  for (const i of items) CP.conv.messages.push({role: 'assistant', content: i.text, inbox: i.id});
  post('/api/inbox/seen', {ids: items.map(i => i.id)}).then(load);
  saveConv();
  return true;
}
function chatBadge() {
  const n = (S && S.inbox || []).length, b = $('#claudeBtn');
  if (b) { if (n) b.dataset.badge = n; else delete b.dataset.badge; }
  if (n && CP.open && deliverInbox()) renderChat();
}
function msgHtml(m, i) {
  if (m.role === 'user') return `<div class="msg user">${m.ctx ? `<div class="msg-ctx">About ${esc(m.ctx.title)}</div>` : ''}${esc(m.content).replace(/\n/g, '<br>')}${m.attachments && m.attachments.length ? `<div class="att">📎 ${m.attachments.map(esc).join(', ')}</div>` : ''}</div>`;
  return `<div class="msg assistant${m.inbox ? ' question' : ''}" data-mi="${i}">${m.inbox ? '<div class="q-tag">Question after your import</div>' : ''}${md(m.content)}${changedBar(m, i)}
    <div class="msg-tools">${m.level ? `<span class="muted small">${LEVEL_NAME[m.level] || ''}</span>` : ''}${m.level && m.level !== 'deep' && i === CP.conv.messages.length - 1 ? `<button type="button" class="linkish small" data-harder="${i}">Think harder</button>` : ''}<button type="button" class="linkish small" data-pin="${i}">${m.pinned ? 'Pinned to home' : 'Pin to home'}</button></div></div>`;
}
function renderChat() {
  let p = $('#chatPanel');
  if (!p) { p = document.createElement('aside'); p.id = 'chatPanel'; p.className = 'panel'; p.setAttribute('aria-label', 'Claude'); document.body.appendChild(p); }
  p.hidden = !CP.open;
  if (!CP.open) return;
  deliverInbox();
  const C = CP, starters = STARTERS_BY[view] || STARTERS_BY.overview;
  p.innerHTML = `<div class="panel-head"><div class="panel-title"><span class="claude-mark">${CLAUDE_ICON}</span>${CP.mode === 'history' ? 'Conversations' : 'Claude'}</div>
      <div class="panel-tools">
        <button type="button" class="icon-btn sm" id="cpHist" title="${CP.mode === 'history' ? 'Back to the chat' : 'Earlier conversations'}" aria-label="Earlier conversations">${CP.mode === 'history' ? ICON.back : ICON.list}</button>
        <button type="button" class="icon-btn sm" id="cpNew" title="New conversation" aria-label="New conversation">${ICON.plus}</button>
        <button type="button" class="icon-btn sm" id="cpClose" title="Close (Esc)" aria-label="Close">${ICON.x}</button></div></div>
    ${CP.mode === 'history' ? `<div class="panel-body"><input type="search" id="cpSearch" placeholder="Search conversations" value="${esc(CP.q)}" aria-label="Search conversations" style="width:100%;margin-bottom:12px"><div id="cpList"><div class="skel-line"></div><div class="skel-line"></div></div></div>` : `
    <div class="panel-body" id="cpMsgs">
      ${C.conv.messages.length ? '' : `<div class="cp-empty"><div class="cp-hello">What would you like to know?</div><div class="starters">${starters.map(s => `<button type="button" class="btn" data-q="${esc(s)}">${esc(s)}</button>`).join('')}</div></div>`}
      ${(() => { CHART_W = 380; const h = C.conv.messages.map(msgHtml).join(''); CHART_W = 640; return h; })()}
      ${C.busy ? `<div class="msg assistant working" id="working">${stepsHtml(C.steps)}</div>` : ''}
      ${C.error ? `<div class="banner err">${esc(C.error)}</div>` : ''}
    </div>
    ${C.ctx ? `<div class="cp-ctx"><span class="muted">About</span> <b>${esc(C.ctx.title)}</b><button type="button" class="x-btn" id="cpCtxX" aria-label="Remove">×</button></div>` : ''}
    ${C.files.length ? `<div class="chips cp-files">${C.files.map((f, i) => `<span class="chip">${f.url ? `<img src="${f.url}" alt="">` : '📄'} ${esc(f.name)} <button data-unattach="${i}" aria-label="Remove">×</button></span>`).join('')}</div>` : ''}
    <form class="panel-ask" id="cpAsk">
      <button type="button" class="icon-btn sm" id="cpAttach" title="Attach files or pictures" aria-label="Attach files" ${C.busy ? 'disabled' : ''}>${ICON.clip}</button>
      <input type="file" id="cpFile" multiple hidden accept="image/*,.csv,.tsv,.txt,.json,.xml,.pdf,.xlsx,.xls,.xlsm,.zip">
      <textarea id="cpQ" rows="1" placeholder="Ask about your money" aria-label="Message" ${C.busy ? 'disabled' : ''}></textarea>
      <button class="send" aria-label="Send" ${C.busy ? 'disabled' : ''}>${ICON.up}</button></form>
    <div class="cp-effort" role="group" aria-label="How hard Claude thinks"><span class="muted">Effort</span>${EFFORTS.map(([v, l, t]) =>
      `<button type="button" data-effort="${v}" aria-pressed="${chatEffort() === v}" title="${esc(t)}">${l}</button>`).join('')}</div>`}`;
  $('#cpClose').onclick = closeChat;
  $('#cpNew').onclick = newChat;
  $('#cpHist').onclick = () => { CP.mode = CP.mode === 'history' ? 'chat' : 'history'; renderChat(); };
  if (CP.mode === 'history') { loadChatList(); $('#cpSearch').oninput = e => { CP.q = e.target.value; clearTimeout(CP.t); CP.t = setTimeout(loadChatList, 200); }; return; }
  const box = $('#cpMsgs'); box.scrollTop = box.scrollHeight;
  attachTips(p, box);
  const q = $('#cpQ');
  const fit = () => { q.style.height = 'auto'; q.style.height = Math.min(q.scrollHeight, 160) + 'px'; };
  q.oninput = fit;
  q.onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('#cpAsk').requestSubmit(); } };
  $('#cpAsk').onsubmit = e => { e.preventDefault(); sendChat(q.value); };
  $('#cpAttach').onclick = () => $('#cpFile').click();
  $('#cpFile').onchange = async e => { const draft = q.value; CP.files.push(...await readFiles(e.target.files)); renderChat(); $('#cpQ').value = draft; };
  if ($('#cpCtxX')) $('#cpCtxX').onclick = () => { CP.ctx = null; renderChat(); };
  $$('[data-unattach]', p).forEach(b => b.onclick = () => { CP.files.splice(+b.dataset.unattach, 1); renderChat(); });
  $$('[data-q]', p).forEach(b => b.onclick = () => sendChat(b.dataset.q));
  $$('[data-effort]', p).forEach(b => b.onclick = () => { CP.effort = b.dataset.effort; store.set('chat.effort', CP.effort); $$('[data-effort]', p).forEach(x => x.setAttribute('aria-pressed', x === b)); });
  $$('[data-harder]', p).forEach(b => b.onclick = () => {
    // ask the same question again, thinking harder
    const i = +b.dataset.harder, ask = CP.conv.messages[i - 1];
    if (!ask || ask.role !== 'user' || CP.busy) return;
    CP.conv.messages.splice(i - 1, 2);
    CP.ctx = ask.ctx || null;
    sendChat(ask.content, 'deep');
  });
  $$('[data-undo]', p).forEach(b => b.onclick = async () => {
    const m = CP.conv.messages[+b.dataset.undo];
    try { await post('/api/undo', {id: m.undo}); m.undone = true; saveConv(); toast('Change undone'); await load(); } catch (e) { toast(e.message); }
    renderChat();
  });
  $$('[data-pin]', p).forEach(b => b.onclick = async () => {
    const i = +b.dataset.pin, m = CP.conv.messages[i];
    if (m.pinned) return;
    const asked = [...CP.conv.messages.slice(0, i)].reverse().find(x => x.role === 'user');
    const title = (m.content.match(/^#+\s*(.+)$/m) || [])[1] || (m.content.match(/"title":\s*"([^"]+)"/) || [])[1] || (asked ? asked.content.split('\n')[0].slice(0, 70) : 'Pinned answer');
    if (await uiPost({action: 'pin-add', title, content: m.content}, 'Pinned to your home page')) { m.pinned = true; saveConv(); renderChat(); renderPins(); }
  });
  $$('[data-act]', p).forEach(b => b.onclick = e => runAction(JSON.parse(b.dataset.act), b, e));
  if (!C.busy) setTimeout(() => q.focus(), 30);
}
async function loadChatList() {
  try { CP.list = await (await fetch('/api/chats?q=' + encodeURIComponent(CP.q), {cache: 'no-store'})).json(); } catch { CP.list = []; }
  const box = $('#cpList'); if (!box) return;
  const groups = {};
  for (const c of CP.list) (groups[c.topic || 'General'] = groups[c.topic || 'General'] || []).push(c);
  box.innerHTML = CP.list.length ? TOPIC_ORDER.filter(t => groups[t]).map(t => `<div class="cp-topic">${esc(t)}</div>${groups[t].map(c => `<div class="cp-item ${CP.conv.id === c.id ? 'on' : ''}">
      <button type="button" data-conv="${c.id}"><b>${esc(c.title)}</b><span class="muted small">${ago(c.updated)} · ${c.count} message${c.count === 1 ? '' : 's'}</span>${c.snippet ? `<span class="small cp-snip">${esc(c.snippet)}</span>` : ''}</button>
      <button type="button" class="x-btn" data-delconv="${c.id}" aria-label="Delete">×</button></div>`).join('')}`).join('')
    : `<div class="empty">${CP.q ? 'No conversation mentions that.' : 'No conversations yet.'}</div>`;
  $$('[data-conv]', box).forEach(b => b.onclick = async () => {
    const c = await (await fetch('/api/chats/get?id=' + b.dataset.conv, {cache: 'no-store'})).json();
    if (c.error) return toast(c.error);
    CP.conv = {id: c.id, messages: c.messages}; CP.mode = 'chat'; CP.ctx = null; renderChat();
  });
  $$('[data-delconv]', box).forEach(b => b.onclick = async () => {
    if (!confirmTwice('conv' + b.dataset.delconv, 'Click × again to delete this conversation.')) return;
    await post('/api/chats/delete', {id: b.dataset.delconv});
    if (CP.conv.id === b.dataset.delconv) CP.conv = {id: null, messages: []};
    loadChatList();
  });
}
async function saveConv() {
  if (!CP.conv.messages.length) return;
  try { const r = await post('/api/chats/save', {id: CP.conv.id, title: CP.conv.title, messages: CP.conv.messages, page: view}); CP.conv.id = r.id; } catch {}
}
const EFFORTS = [['auto', 'Auto', 'Quick for simple lookups, normal for the rest'], ['quick', 'Quick', 'Fastest and lightest on your usage. Good for lookups'],
  ['normal', 'Normal', 'A balanced answer'], ['deep', 'Deep', 'The most capable model, and it may read through all your data. Uses the most']];
const LEVEL_NAME = {quick: 'Quick answer', normal: 'Normal answer', deep: 'Deep answer'};
const chatEffort = () => CP.effort || store.get('chat.effort', null) || (UIS.prefs && UIS.prefs.effort) || 'auto';
async function sendChat(text, effort) {
  text = (text || '').trim();
  if (CP.busy || (!text && !CP.files.length)) return;
  const files = CP.files; CP.files = [];
  const ctx = CP.ctx; CP.ctx = null;
  CP.conv.messages.push({role: 'user', content: text || 'Here are some files.', attachments: files.map(f => f.name), ...(ctx ? {ctx} : {})});
  CP.busy = true; CP.error = null; CP.steps = [];
  renderChat();
  const pid = 'c' + Date.now() + Math.random().toString(36).slice(2, 7);
  watchProgress(pid, () => CP.busy, '#working');
  try {
    // a question about a card carries that card's numbers along
    const msgs = CP.conv.messages.filter(m => !m.local).map(m => ({role: m.role, content: m.role === 'user' && m.ctx ? `(About this part of the dashboard, "${m.ctx.title}": ${m.ctx.text})\n\n${m.content}` : m.content}));
    const r = await post('/api/chat', {messages: msgs, files: files.map(({name, media_type, data}) => ({name, media_type, data})), progress_id: pid, effort: effort || chatEffort()});
    CP.conv.messages.push({role: 'assistant', content: r.reply, undo: r.undo || null, level: r.level || null});
    if (r.undo) load();
    saveConv();
  } catch (e) { CP.error = e.message; CP.conv.messages.pop(); CP.files = files; CP.ctx = ctx; }
  CP.busy = false;
  if (CP.open) renderChat();
  else toast('Claude answered. Press / to read it.');
}
function cardContext(card) {
  // the card's title and what it shows, as plain text for Claude
  const title = (($('h2', card) || $('.k', card) || {}).textContent || 'this card').trim();
  const chart = $('.tc', card) || $('[data-chart]', card);
  let data = '';
  if (chart && chart.chartData) data = chart.chartData().slice(0, 60).map(r => r.join(', ')).join('\n');
  else if (chart && CHART_DATA[chart.dataset.chart]) { const c = CHART_DATA[chart.dataset.chart]; data = c.labels.map((l, i) => `${l}: ` + c.series.map(s => `${s.name} ${s.values[i]}`).join(', ')).join('\n'); }
  const text = card.innerText.replace(/\n{2,}/g, '\n').trim().slice(0, 2500);
  return {title, text: `${text}${data ? '\nData:\n' + data : ''}`.slice(0, 4000)};
}

/* ---------- buttons in Claude's answers ---------- */
function actionsHtml(json) {
  let list;
  try { list = JSON.parse(json); } catch { return ''; }
  if (!Array.isArray(list)) return '';
  return `<div class="acts">${list.slice(0, 3).filter(a => a && a.label && a.do).map(a => `<button type="button" class="btn act" data-act="${esc(JSON.stringify(a))}">${esc(a.label)}</button>`).join('')}</div>`;
}
async function runAction(a, btn, e) {
  const done = label => { if (btn) { btn.disabled = true; btn.textContent = '✓ ' + label; } };
  try {
    if (a.do === 'open_payments') { await openThing({kind: 'payments', title: a.label, filter: a.filter || {}}, e); }
    else if (a.do === 'open_page') { closeChat(); openThing({kind: 'page', page: a.page}); }
    else if (a.do === 'add_todo') { await post('/api/edit', {section: 'todos', action: 'add', fields: {text: a.text}}); await load(); done('Added to your to do list'); }
    else if (a.do === 'open_holding') { const p = S.positions.find(x => x.name.toLowerCase() === String(a.name).toLowerCase()) || S.positions.find(x => x.name.toLowerCase().includes(String(a.name).toLowerCase())); if (p) openHolding(p.isin || 'n:' + p.name.trim().toLowerCase()); else toast('Holding not found'); }
    else if (a.do === 'set_invest') { const i = S.savings.findIndex(x => x.name.toLowerCase() === String(a.name || '').toLowerCase()); if (i < 0) throw new Error('No savings account called ' + a.name);
      await post('/api/edit', {section: 'savings', index: i, fields: {invest: !!a.invest}}); await load(); done(a.invest ? 'Counted as an investment' : 'Counted as cash'); }
    else if (a.do === 'add_watch') { await post('/api/edit', {section: 'watchlist', action: 'add', fields: {name: a.name || a.symbol, symbol: a.symbol, buy_below: a.buy_below ?? null, note: a.note || ''}}); await load(); OPP = null; done('On your watchlist'); }
    else if (a.do === 'set_profile') { await post('/api/edit', {section: 'profile', fields: a.fields || {}}); await load(); done('Saved to your profile'); }
    else if (a.do === 'add_goal') { await post('/api/edit', {section: 'goals', action: 'add', fields: {name: a.name, target_eur: +a.target, date: a.date || '', source: 'net_worth'}}); await load(); done('Goal added'); }
    else toast('Unknown action');
  } catch (err) { toast(err.message); }
}

/* ---------- opening things: payments, a payment, a page, a holding ---------- */
async function openThing(spec, e) {
  if (typeof spec === 'string') { const i = spec.indexOf(':'); spec = {kind: spec.slice(0, i), id: spec.slice(i + 1)}; }
  const at = e && e.clientX != null ? e : {clientX: innerWidth / 2 - 200, clientY: innerHeight / 3};
  if (spec.kind === 'payments') {
    await ensureSpending();
    openPop(() => ({title: spec.title || 'Payments', list: paymentsMatching(spec.filter || {}), filter: txFilterFrom(spec.filter || {})}), at);
  } else if (spec.kind === 'tx') { await ensureSpending(); txSheet(spec.id); }
  else if (spec.kind === 'page') {
    if (spec.page === 'spending' && spec.tab) SP.tab = spec.tab;
    const go = '#' + spec.page;
    if (location.hash === go) renderView(); else location.hash = go;
    if (spec.card) setTimeout(() => { const c = $(`[data-card="${spec.card}"]`); if (c) c.scrollIntoView({behavior: 'smooth', block: 'center'}); }, 200);
  } else if (spec.kind === 'holding') openHolding(spec.id);
  else if (spec.kind === 'account') location.hash = '#account/' + encodeURIComponent(spec.id || spec.name);
}

function chatDrill(c, i, k) {
  // a click on a chart Claude drew: work out what the bar stands for from its label, its series and the title
  const low = x => String(x || '').toLowerCase().trim();
  const label = String((c.labels || [])[i] ?? ''), sname = String(((c.series || [])[k] || {}).name || ''), title = c.title || '';
  const pos = (S.positions || []).find(p => [label, sname].some(x => low(p.name) === low(x)));
  if (pos) { openHolding(posId(pos)); return null; }
  if (!SP.d) { ensureSpending().then(() => openPop(() => chatDrill(c, i, k), {clientX: ($('#chatPanel') || {getBoundingClientRect: () => ({left: innerWidth})}).getBoundingClientRect().left - 430, clientY: innerHeight / 3})); return null; }
  const payAcct = [...new Set(SP.d.transactions.map(t => t.account))].find(id => [label, sname].some(x => low(id) === low(x) || low(acctName(id)) === low(x)));
  const acct = [...(S.accounts || []), ...(S.savings || [])].find(a => [label, sname].some(x => low(a.name) === low(x)));
  if (acct && !payAcct) { openThing({kind: 'account', id: acct.name}); return null; }
  const f = {}, words = [label, sname, title];
  for (const w of [label, sname]) {
    if (/^\d{4}-\d{2}$/.test(w)) f.month = w;
    else if (/^\d{4}$/.test(w)) { f.from = w + '-01-01'; f.to = w + '-12-31'; }
  }
  const has = (text, name) => new RegExp(`(^|[^a-z])${low(name).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}([^a-z]|$)`).test(low(text));
  const longest = list => list.sort((a, b) => b.length - a.length);
  for (const w of words) {
    if (!f.category && !f.group) {
      const cat = longest(SP.d.categories.map(x => x.name)).find(n => w === title ? has(w, n) : low(w) === low(n));
      if (cat) { f.category = cat; continue; }
      const grp = longest([...new Set(SP.d.categories.map(x => x.group))]).find(n => w === title ? has(w, n) : low(w) === low(n));
      if (grp) { f.group = grp; continue; }
    }
    if (!f.country && w !== title && window.GEO) {
      const code = Object.keys(GEO.countries).find(cd => low(cd) === low(w) || low(GEO.countries[cd].n) === low(w));
      if (code) { f.country = code; continue; }
    }
    if (!f.merchant && w !== title && SP.rows.some(t => low(t.merchant) === low(w))) f.merchant = w;
  }
  if (payAcct) f.account = payAcct;
  const keys = Object.keys(f);
  if (!keys.length || keys.every(x => ['month', 'from', 'to'].includes(x)) && !/spen|pay|cost|expens|bought/i.test(title)) {
    openChat({text: `Tell me more about ${label}${sname && c.series.length > 1 ? ` (${sname})` : ''} in "${title || 'this chart'}"`});
    return null;
  }
  const list = paymentsMatching(f);
  const name = [f.merchant || f.category || f.group || (f.country && ctyName(f.country)) || (f.account && acctName(f.account)), f.month ? mLabel(f.month) : f.from ? f.from.slice(0, 4) : ''].filter(Boolean).join(', ');
  return {title: name || 'Payments', list, filter: txFilterFrom(f)};
}

/* ---------- card tools: ask about this, full screen, download ---------- */
const ICON = {
  ask: '<svg viewBox="0 0 24 24"><path d="M21 12a8 8 0 01-11.6 7.1L4 20l1-4.6A8 8 0 1121 12z"/></svg>',
  full: '<svg viewBox="0 0 24 24"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>',
  down: '<svg viewBox="0 0 24 24"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>',
  x: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  plus: '<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>',
  list: '<svg viewBox="0 0 24 24"><path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/></svg>',
  back: '<svg viewBox="0 0 24 24"><path d="M15 6l-6 6 6 6"/></svg>',
  clip: '<svg viewBox="0 0 24 24"><path d="M21 11.5l-8.6 8.6a5 5 0 01-7.1-7.1l8.6-8.6a3.3 3.3 0 014.7 4.7l-8.6 8.6a1.7 1.7 0 01-2.4-2.4l7.9-7.9"/></svg>',
  up: '<svg viewBox="0 0 24 24"><path d="M12 19V5M6 11l6-6 6 6"/></svg>',
  search: '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>',
  bookmark: '<svg viewBox="0 0 24 24"><path d="M6 3h12v18l-6-4-6 4z"/></svg>',
  grip: '<svg viewBox="0 0 24 24"><circle cx="9" cy="6" r="1.2"/><circle cx="15" cy="6" r="1.2"/><circle cx="9" cy="12" r="1.2"/><circle cx="15" cy="12" r="1.2"/><circle cx="9" cy="18" r="1.2"/><circle cx="15" cy="18" r="1.2"/></svg>',
  focus: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M3 8V5a2 2 0 012-2h3M16 3h3a2 2 0 012 2v3M21 16v3a2 2 0 01-2 2h-3M8 21H5a2 2 0 01-2-2v-3"/></svg>',
};
const CLAUDE_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/></svg>';
function decorateCards(root = $('#view')) {
  for (const card of $$('.card', root)) {
    if (card.dataset.tools || card.classList.contains('no-tools')) continue;
    const head = $(':scope > h2, :scope > .card-head > h2, :scope > .card-head > div > h2', card) || (card.classList.contains('tile') && $('.k', card)) || (card.classList.contains('hero') && $('.label', card));
    if (!head) continue;
    card.dataset.tools = '1';
    const hasChart = $('svg.c-svg, .tc svg, table', card);
    const span = document.createElement('span');
    span.className = 'ctools';
    if (!card.dataset.card) card.dataset.card = 'k-' + (head.firstChild ? head.firstChild.textContent : head.textContent).trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 40);
    span.innerHTML = `<button type="button" class="grip" data-ct="move" title="Drag to move" aria-label="Drag to move this card">${ICON.grip}</button><button type="button" data-ct="ask" title="Ask Claude about this" aria-label="Ask Claude about this">${ICON.ask}</button>
      ${card.classList.contains('tile') || card.classList.contains('hero') ? `<button type="button" data-ct="focus" title="Focus" aria-label="Focus on this number">${ICON.focus}</button>` : ''}
      ${hasChart ? `<button type="button" data-ct="full" title="Full screen" aria-label="Full screen">${ICON.full}</button><button type="button" data-ct="down" title="Download" aria-label="Download">${ICON.down}</button>` : ''}`;
    head.appendChild(span);
  }
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-ct]');
  if (!b) return;
  e.stopPropagation();
  const card = b.closest('.card');
  if (b.dataset.ct === 'ask') openChat({ctx: cardContext(card)});
  else if (b.dataset.ct === 'full') fullScreen(card);
  else if (b.dataset.ct === 'focus') focusCard(card);
  else if (b.dataset.ct === 'down') {
    const m = openMenu(b, `<div class="menu-sec">${$('svg.c-svg, .tc svg', card) ? '<button type="button" class="menu-row" data-dl="png"><span class="ck"></span>Image (PNG)</button>' : ''}<button type="button" class="menu-row" data-dl="csv"><span class="ck"></span>Data (CSV)</button></div>`);
    $$('[data-dl]', m).forEach(x => x.onclick = () => { closeMenus(); x.dataset.dl === 'png' ? downloadPng(card) : downloadCsv(card); });
  }
}, true);
/* ---------- move cards around: drag a card by its grip; every page remembers its own arrangement ---------- */
const pageKey = () => view === 'spending' ? 'spending:' + SP.tab : view === 'account' ? 'account' : view;
const movable = c => !c.closest('.pop, .drawer, .fs, .panel, .menu') && c.dataset.card && !(c.parentElement && c.parentElement.closest('.card'));
/* Long lists and tables scroll inside their card instead of stretching the page. */
const CAP = 440, SCROLLS = {};
addEventListener('hashchange', () => { for (const k in SCROLLS) delete SCROLLS[k]; });
function capLong(root = $('#view')) {
  const mark = (el, key) => {
    el.classList.add('scrolly');
    if (el.dataset.cap === 'tall') el.classList.add('tall');
    const fade = () => el.classList.toggle('at-end', el.scrollTop + el.clientHeight >= el.scrollHeight - 4);
    el.addEventListener('scroll', () => { SCROLLS[key] = el.scrollTop; fade(); }, {passive: true});
    if (SCROLLS[key]) el.scrollTop = SCROLLS[key];  // a re-render keeps your place
    fade();
  };
  $$('.card', root).forEach((card, ci) => {
    if (card.closest('.fs-box')) return;
    const base = (card.dataset.card || cardTitle(card) || ci) + ':';
    let n = 0;
    const walk = el => {
      for (const c of el.children) {
        if (c.classList.contains('scrolly')) { n++; continue; }
        if (c.matches('svg, canvas, .seg, .controls, form, .pop, .menu')) continue;
        const listy = c.matches('.table-wrap') || (c.children.length >= 6 && !c.querySelector('svg.c-svg, .map'));
        if (c.dataset.cap === 'tall' || (listy && c.offsetHeight > CAP + 40)) mark(c, base + n++); else if (c.offsetHeight > CAP) walk(c);
      }
    };
    walk(card);
  });
}

function layoutBoxes() {
  // the containers that hold cards, in page order: a card can move within one or into another
  return [...new Set($$('#view .card').filter(movable).map(c => c.parentElement))];
}
function applyLayout() {
  const boxes = layoutBoxes(), fresh = boxes.filter(b => !b.dataset.box);
  if (!fresh.length) return;
  boxes.forEach((b, i) => { if (!b.dataset.box) { b.dataset.box = 'b' + i; [...b.children].forEach((c, j) => { c.dataset.slot = j; }); } });
  const saved = ((UIS.prefs || {}).layouts || {})[pageKey()];
  if (!saved) return;
  for (const b of fresh) {
    const keys = saved[b.dataset.box];
    if (!keys) continue;
    const listed = keys.map(k => k.startsWith('slot:') ? [...b.children].find(c => c.dataset.slot === k.slice(5) && !(c.matches('.card') && movable(c)))
      : $(`#view .card[data-card="${CSS.escape(k)}"]`)).filter(el => el && (!el.matches('.card') || movable(el)));
    const rest = [...b.children].filter(c => !listed.includes(c));
    const order = [...listed];
    // anything the saved arrangement doesn't know (a card that is new on this visit) keeps its own place
    for (const c of rest) order.splice(Math.min(+c.dataset.slot || 0, order.length), 0, c);
    order.forEach(el => b.appendChild(el));
  }
}
function saveLayout() {
  const lay = {};
  for (const b of $$('#view [data-box]')) lay[b.dataset.box] = [...b.children].map(c => c.matches('.card') && movable(c) ? c.dataset.card : 'slot:' + c.dataset.slot);
  const layouts = {...((UIS.prefs || {}).layouts || {}), [pageKey()]: lay};
  uiPost({action: 'prefs', prefs: {layouts}});
}
function resetLayout(all) {
  const layouts = all ? {} : {...((UIS.prefs || {}).layouts || {})};
  if (!all) delete layouts[pageKey()];
  uiPost({action: 'prefs', prefs: {layouts}}, all ? 'Every page is back to its first layout' : 'This page is back to its first layout').then(() => renderView());
}
let dragCard = null;
document.addEventListener('pointerdown', e => {
  const g = e.target.closest && e.target.closest('.grip');
  if (!g) return;
  const card = g.closest('.card');
  if (card && movable(card)) { card.draggable = true; dragCard = card; }
});
document.addEventListener('dragstart', e => {
  if (!dragCard || e.target !== dragCard) return;
  e.dataTransfer.effectAllowed = 'move';
  try { e.dataTransfer.setData('text/plain', dragCard.dataset.card); } catch {}
  setTimeout(() => dragCard && dragCard.classList.add('dragging'));
  document.body.classList.add('moving-cards');
});
document.addEventListener('dragover', e => {
  if (!dragCard) return;
  const over = e.target.closest && e.target.closest('#view .card');
  $$('.drop-before, .drop-after').forEach(x => x.classList.remove('drop-before', 'drop-after'));
  if (!over || over === dragCard || !movable(over) || over.contains(dragCard)) return;
  e.preventDefault();
  const r = over.getBoundingClientRect(), vertical = !over.parentElement.matches('.grid');
  const after = vertical ? e.clientY > r.top + r.height / 2 : e.clientX > r.left + r.width / 2;
  over.classList.add(after ? 'drop-after' : 'drop-before');
});
document.addEventListener('drop', e => {
  if (!dragCard) return;
  const over = $('.drop-before, .drop-after');
  if (over) { e.preventDefault(); over.classList.contains('drop-after') ? over.after(dragCard) : over.before(dragCard); saveLayout(); toast('Moved. Settings can put every page back.'); }
});
document.addEventListener('dragend', () => {
  if (dragCard) { dragCard.classList.remove('dragging'); dragCard.draggable = false; }
  dragCard = null;
  document.body.classList.remove('moving-cards');
  $$('.drop-before, .drop-after').forEach(x => x.classList.remove('drop-before', 'drop-after'));
});

function cardTitle(card) { return (($('h2', card) || $('.k', card) || $('.label', card) || {}).firstChild?.textContent || 'chart').trim(); }
function fullScreen(card) {
  const ov = document.createElement('div');
  ov.className = 'fs';
  ov.innerHTML = `<div class="fs-box card no-tools"><div class="fs-head"><h2>${esc(cardTitle(card))}</h2><button type="button" class="icon-btn sm" aria-label="Close">${ICON.x}</button></div><div class="fs-body"></div></div>`;
  document.body.appendChild(ov);
  const body = $('.fs-body', ov);
  const live = card.renderFull;
  if (live) live(body); else {
    const clone = card.cloneNode(true);
    $$('.ctools', clone).forEach(x => x.remove());
    body.append(...[...clone.children].filter(x => !x.matches('h2, .card-head')));
  }
  body.style.position = 'relative';
  attachTips(body, body);
  const close = () => { ov.remove(); document.removeEventListener('keydown', esc1); };
  const esc1 = e => { if (e.key === 'Escape') close(); };
  $('.fs-head button', ov).onclick = close;
  ov.onclick = e => { if (e.target === ov) close(); };
  document.addEventListener('keydown', esc1);
}
function focusCard(card) {
  const label = cardTitle(card).replace(/\s+$/, ''), big = $('.big, .v', card), sub = $('.day, .n, .tile-delta', card);
  const ov = document.createElement('div');
  ov.className = 'focus';
  ov.innerHTML = `<div class="focus-k">${esc(label)}</div><div class="focus-v">${big ? big.innerHTML : ''}</div>${sub ? `<div class="focus-n">${sub.innerHTML}</div>` : ''}<div class="muted small focus-hint">Press Esc or click to close</div>`;
  document.body.appendChild(ov);
  const close = () => { ov.remove(); document.removeEventListener('keydown', k); };
  const k = e => { if (e.key === 'Escape') close(); };
  ov.onclick = close; document.addEventListener('keydown', k);
}
function downloadBlob(blob, name) {
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name;
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
const fileName = s => s.replace(/[^\w\- ]+/g, '').trim().replace(/\s+/g, '-').toLowerCase() || 'chart';
function downloadCsv(card) {
  let rows = null;
  const tc = $('.tc', card), box = $('[data-chart]', card), table = $('table', card);
  if (tc && tc.chartData) rows = tc.chartData();
  else if (box && CHART_DATA[box.dataset.chart]) { const c = CHART_DATA[box.dataset.chart]; rows = [['', ...c.series.map(s => s.name)], ...c.labels.map((l, i) => [l, ...c.series.map(s => s.values[i])])]; }
  else if (table) rows = $$('tr', table).map(tr => $$('th, td', tr).map(td => td.innerText.trim()));
  else rows = $$('[data-tip]', card).map(x => [x.dataset.tip]);
  const csv = rows.map(r => r.map(v => /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : v).join(',')).join('\n');
  downloadBlob(new Blob([csv], {type: 'text/csv'}), fileName(cardTitle(card)) + '.csv');
}
function downloadPng(card) {
  // copy the chart with its computed colours, draw it on a canvas with the card's background
  const svg = $('svg.c-svg, .tc svg', card);
  const clone = svg.cloneNode(true), src = [svg, ...svg.querySelectorAll('*')], dst = [clone, ...clone.querySelectorAll('*')];
  src.forEach((el, i) => {
    const cs = getComputedStyle(el), d = dst[i];
    for (const p of ['fill', 'stroke', 'stroke-width', 'opacity', 'fill-opacity', 'font-size', 'font-weight', 'font-family', 'visibility', 'stroke-dasharray'])
      d.style.setProperty(p, cs.getPropertyValue(p));
  });
  const vb = svg.viewBox.baseVal, scale = 2, W = vb.width || svg.clientWidth, H = vb.height || svg.clientHeight;
  clone.setAttribute('width', W); clone.setAttribute('height', H);
  const url = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(new XMLSerializer().serializeToString(clone));
  const img = new Image();
  img.onload = () => {
    const c = document.createElement('canvas'); c.width = (W + 40) * scale; c.height = (H + 70) * scale;
    const g = c.getContext('2d'); g.scale(scale, scale);
    g.fillStyle = getComputedStyle(card).backgroundColor; g.fillRect(0, 0, W + 40, H + 70);
    g.fillStyle = getComputedStyle(document.body).color; g.font = '600 16px system-ui, sans-serif'; g.fillText(cardTitle(card), 20, 32);
    g.drawImage(img, 20, 50, W, H);
    c.toBlob(b => downloadBlob(b, fileName(cardTitle(card)) + '.png'));
  };
  img.src = url;
}

/* ---------- search (⌘K) ---------- */
async function openSearch() {
  closeMenus();
  if ($('.cmdk')) return;
  const ov = document.createElement('div');
  ov.className = 'cmdk-wrap';
  ov.innerHTML = `<div class="cmdk" role="dialog" aria-label="Search"><div class="cmdk-in">${ICON.search}<input type="text" id="ckQ" placeholder="Search transactions, investments, pages and actions" aria-label="Search"><kbd>Esc</kbd></div><div class="cmdk-list" id="ckList"></div></div>`;
  document.body.appendChild(ov);
  const q = $('#ckQ'); q.focus();
  let items = searchIndex(), sel = 0, shown = [];
  ensureSpending().then(() => { items = searchIndex(); draw(); }).catch(() => {});
  const close = () => { ov.remove(); };
  ov.onclick = e => { if (e.target === ov) close(); };
  const draw = () => {
    const s = q.value.trim().toLowerCase();
    const score = it => { const n = it.name.toLowerCase(); if (!s) return it.base || 0; if (n.startsWith(s)) return 100 + (it.base || 0); if (n.includes(' ' + s)) return 60 + (it.base || 0); if (n.includes(s)) return 40 + (it.base || 0); if ((it.extra || '').toLowerCase().includes(s)) return 20; return -1; };
    shown = items.map(it => [score(it), it]).filter(([sc]) => sc >= 0).sort((a, b) => b[0] - a[0]).slice(0, s ? 40 : 14).map(x => x[1]);
    if (s && SP.d) {
      const tx = SP.d.transactions.filter(t => (t.merchant + ' ' + t.description + ' ' + Math.abs(t.amount).toFixed(2)).toLowerCase().includes(s)).slice(0, 6);
      shown.push(...tx.map(t => ({type: 'Payment', name: `${t.merchant}, ${fdate(t.date)}`, sub: `${t.amount < 0 ? '−' : '+'}€${Math.abs(t.amount).toFixed(2)}`, run: () => txSheet(t.id)})));
    }
    sel = Math.min(sel, Math.max(0, shown.length - 1));
    $('#ckList').innerHTML = shown.length ? shown.map((it, i) => `<button type="button" class="ck-row ${i === sel ? 'on' : ''}" data-ck="${i}"><span class="ck-type">${esc(it.type)}</span><span class="ck-name">${esc(it.name)}</span><span class="ck-sub muted">${esc(it.sub || '')}</span></button>`).join('') : '<div class="empty">Nothing found.</div>';
    $$('[data-ck]').forEach(b => b.onclick = () => go(+b.dataset.ck));
    const on = $('.ck-row.on'); if (on) on.scrollIntoView({block: 'nearest'});
  };
  const go = i => { const it = shown[i]; if (!it) return; close(); it.run(); };
  q.oninput = () => { sel = 0; draw(); };
  q.onkeydown = e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); sel = Math.min(shown.length - 1, sel + 1); draw(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); sel = Math.max(0, sel - 1); draw(); }
    else if (e.key === 'Enter') { e.preventDefault(); go(sel); }
    else if (e.key === 'Escape') close();
  };
  draw();
}
function searchIndex() {
  const out = [];
  const page = (h, n, base = 5) => out.push({type: 'Page', name: n, base, run: () => { location.hash = '#' + h; }});
  Object.entries(TITLES).forEach(([h, n]) => { if (h !== 'chat' && h !== 'account') page(h, n, 10); });
  const act = (name, run, base = 8) => out.push({type: 'Action', name, base, run});
  act('Ask Claude', () => openChat(), 12);
  act('New conversation with Claude', () => { newChat(); openChat(); });
  act('Import files', () => { location.hash = '#import'; });
  act('Add savings account', () => { location.hash = '#cash'; setTimeout(() => $('#addSav') && $('#addSav').click(), 150); });
  act('Add debt', () => { location.hash = '#cash'; setTimeout(() => $('#addDebt') && $('#addDebt').click(), 150); });
  act('Add goal', () => { location.hash = '#plan'; setTimeout(() => $('#goalAdd') && $('#goalAdd').click(), 200); });
  act('Add a pot', () => { location.hash = '#cash'; setTimeout(() => $('#potAdd') && $('#potAdd').click(), 200); });
  act('Quick check payments', () => { SP.tab = 'check'; location.hash = '#spending'; if (view === 'spending') spendingPage(); });
  act('Review last month', () => { SP.tab = 'check'; SP.check.review = 'last'; location.hash = '#spending'; if (view === 'spending') spendingPage(); });
  act('Refresh prices', async () => { await post('/api/refresh', {}); toast('Refreshing prices'); });
  act('Save this view', () => setTimeout(openViewsMenu, 50));
  act('Hide or show amounts', () => setPrivate(!document.body.classList.contains('private')));
  act('Switch light or dark', () => { const t = store.get('theme', 'system'), dark = t === 'dark' || (t === 'system' && matchMedia('(prefers-color-scheme: dark)').matches); store.set('theme', dark ? 'light' : 'dark'); applyTheme(); });
  act('Keyboard shortcuts', () => showShortcuts());
  act('Export all data', () => { location.href = '/api/export?what=all'; });
  for (const v of UIS.views) out.push({type: 'View', name: v.name, base: 9, run: () => applyView(v)});
  if (S) {
    for (const p of combined(S.positions)) out.push({type: 'Holding', name: p.name, sub: fmtV(p.value, '€'), base: 4, run: () => openHolding(p.isin || 'n:' + p.name.trim().toLowerCase())});
    for (const a of [...S.accounts.map(a => a.name), S.managed.name]) out.push({type: 'Account', name: a, base: 4, run: () => { location.hash = '#account/' + encodeURIComponent(a); }});
    for (const s of S.savings) out.push({type: 'Savings', name: s.name, sub: fmtV(s.value, '€'), base: 3, run: () => { location.hash = '#cash'; }});
    for (const g of S.goals || []) out.push({type: 'Goal', name: g.name, base: 3, run: () => { location.hash = '#plan'; }});
  }
  if (SP.d) {
    const m = {};
    for (const t of SP.d.transactions) { const x = m[t.merchant] = m[t.merchant] || {n: 0, v: 0}; x.n++; x.v += t.amount; }
    Object.entries(m).sort((a, b) => b[1].n - a[1].n).slice(0, 400).forEach(([name, x]) => out.push({type: 'Merchant', name, sub: `${x.n} payment${x.n === 1 ? '' : 's'}`, base: Math.min(3, x.n / 10), run: () => openThing({kind: 'payments', title: name, filter: {merchant: name}})}));
    for (const c of SP.d.categories) out.push({type: 'Category', name: c.name, sub: c.group, base: 2, run: () => openThing({kind: 'payments', title: c.name, filter: {category: c.id}})});
    const tags = new Set(SP.d.transactions.flatMap(t => t.tags || []));
    for (const t of tags) out.push({type: 'Tag', name: '#' + t, base: 2, run: () => openThing({kind: 'payments', title: '#' + t, filter: {tag: t}})});
    const cty = new Set(SP.d.transactions.map(t => t.country).filter(Boolean));
    for (const c of cty) out.push({type: 'Country', name: ctyName(c), base: 1, run: () => openThing({kind: 'payments', title: ctyName(c), filter: {country: c}})});
  }
  return out;
}

/* ---------- right click (or long press) on a row ---------- */
async function ctxMenu(target, x, y) {
  const [kind, ...rest] = target.dataset.ctx.split(':'), id = rest.join(':');
  let items = [];
  if (kind === 'tx') {
    await ensureSpending();
    const t = txById(id); if (!t) return;
    items = [['Change category', () => txSheet(id, 'category')], ['Ask Claude about this', () => txSheet(id, 'chat')],
      [t.checked ? 'Mark as not checked' : 'Mark as checked', () => setChecked([id], !t.checked)], ['Split over categories', () => txSheet(id, 'split')],
      [t.excluded ? 'Count it again' : 'Leave out of totals', () => spEdit({action: 'exclude', ids: [id], excluded: !t.excluded}, t.excluded ? 'Counted again' : 'Left out of totals')],
      [`All payments to ${t.merchant}`, () => openThing({kind: 'payments', title: t.merchant, filter: {merchant: t.merchant}}, {clientX: x, clientY: y})]];
  } else if (kind === 'holding') {
    const p = S.positions.find(p => (p.isin || 'n:' + p.name.trim().toLowerCase()) === id);
    items = [['Open details', () => openHolding(id)], ['Ask Claude about this', () => openChat({ctx: {title: p ? p.name : 'this holding', text: p ? `${p.name}, ${p.category}, ${p.account}, value €${p.value.toFixed(0)}, profit ${p.profit == null ? 'unknown' : '€' + p.profit.toFixed(0)}` : ''}})],
      ['Set target weight', () => setTarget(id)]];
  } else if (kind === 'account') {
    items = [['Open account', () => { location.hash = '#account/' + encodeURIComponent(id); }], ['Ask Claude about this', () => openChat({ctx: {title: id, text: cardContext(target.closest('.card') || target).text}})]];
  }
  if (!items.length) return;
  const m = openMenu(null, `<div class="menu-sec">${items.map((it, i) => `<button type="button" class="menu-row" data-ci="${i}"><span class="ck"></span>${esc(it[0])}</button>`).join('')}</div>`, 'ctx-menu', {x, y});
  $$('[data-ci]', m).forEach(b => b.onclick = () => { closeMenus(); items[+b.dataset.ci][1](); });
}
document.addEventListener('contextmenu', e => {
  const t = e.target.closest('[data-ctx]');
  if (!t || e.shiftKey) return;
  e.preventDefault();
  ctxMenu(t, e.clientX, e.clientY);
});
let pressTimer = null;
document.addEventListener('pointerdown', e => {
  if (e.pointerType !== 'touch') return;
  const t = e.target.closest('[data-ctx]');
  if (!t) return;
  pressTimer = setTimeout(() => ctxMenu(t, e.clientX, e.clientY), 550);
});
['pointerup', 'pointermove', 'pointercancel'].forEach(ev => document.addEventListener(ev, () => clearTimeout(pressTimer)));

/* ---------- clicks on chart marks and other openable things ---------- */
document.addEventListener('click', e => {
  if (e.target.closest('.menu, .cmdk-wrap, [data-ct]')) return;
  const pt = e.target.closest('[data-pt]'), box = e.target.closest('[data-pick]');
  if (pt && box && PICKS[box.dataset.pick]) {
    const [i, k] = pt.dataset.pt.split('|').map(Number);
    openPop(() => PICKS[box.dataset.pick](i, k), e);
    markPicked(pt);  // after opening, because opening clears the previous pick
    return;
  }
  const op = e.target.closest('[data-open]');
  if (op && op.dataset.open) { openThing(op.dataset.open, e); return; }
  const tx = e.target.closest('[data-open-tx]');
  if (tx && !e.target.closest('.pop')) { txSheet(tx.dataset.openTx); return; }
  const lk = e.target.closest('[data-link]');
  if (lk) { openThing(JSON.parse(lk.dataset.link), e); }
});

/* ---------- series hover: a legend entry, or a row naming a group, lights that series up in every chart ---------- */
let hoverS = null;
function lightSeries(name) {
  if (name === hoverS) return;
  hoverS = name;
  const v = $('#view');
  $$('.hl', v).forEach(x => x.classList.remove('hl'));
  v.classList.toggle('hl-on', !!name);
  if (!name) return;
  const sel = CSS.escape(name);
  $$(`[data-s="${sel}"], [data-series="${sel}"]`, v).forEach(x => x.classList.add('hl'));
}
document.addEventListener('mouseover', e => {
  const x = e.target.closest && e.target.closest('#view [data-series], #view [data-s]');
  lightSeries(x ? x.dataset.series || x.dataset.s : null);
});
// clicking a legend entry of a spending group filters the spending pages on it
document.addEventListener('click', e => {
  const x = e.target.closest && e.target.closest('#sp .c-legend [data-series], #sp [data-focus], .pop [data-focus]');
  if (!x) return;
  const g = x.dataset.focus || x.dataset.series;
  if (SP.d && (SP.d.categories.some(c => c.group === g) || g === 'Uncategorised')) { e.stopPropagation(); toggleFocus(g); }
}, true);

/* ---------- linked hover: the same month lights up in every chart on the page ---------- */
document.addEventListener('mouseover', e => {
  const x = e.target.closest('[data-x]');
  const key = x ? x.dataset.x : null;
  if (key === hoverX) return;
  hoverX = key;
  $$('.xhl').forEach(el => el.classList.remove('xhl'));
  if (key) { $$(`#view [data-x="${CSS.escape(key)}"]`).forEach(el => el.classList.add('xhl')); document.dispatchEvent(new CustomEvent('xsync', {detail: {x: key, from: null}})); }
});
let hoverX = null;
document.addEventListener('xsync', e => {
  if (!e.detail.from) return;
  $$('.xhl').forEach(el => el.classList.remove('xhl'));
  if (e.detail.x) $$(`#view [data-x="${CSS.escape(e.detail.x)}"]`).forEach(el => el.classList.add('xhl'));
});

/* ---------- drop files anywhere ---------- */
let dragDepth = 0;
window.addEventListener('dragenter', e => {
  if (!e.dataTransfer || ![...e.dataTransfer.types].includes('Files') || view === 'import') return;
  dragDepth++;
  if ($('.dropzone')) return;
  const ov = document.createElement('div');
  ov.className = 'dropzone';
  ov.innerHTML = `<div class="dz" data-dz="import"><b>Import into my data</b><span>Investments, balances, statements and bank exports</span></div>
    <div class="dz" data-dz="chat"><b>Ask Claude about it</b><span>Attach to a message</span></div>`;
  document.body.appendChild(ov);
  $$('.dz', ov).forEach(z => { z.ondragover = ev => { ev.preventDefault(); z.classList.add('over'); }; z.ondragleave = () => z.classList.remove('over'); });
});
window.addEventListener('dragleave', () => { dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) setTimeout(() => { if (!dragDepth && $('.dropzone')) $('.dropzone').remove(); }, 50); });
window.addEventListener('dragover', e => { if ($('.dropzone')) e.preventDefault(); });
window.addEventListener('drop', async e => {
  const zone = e.target.closest && e.target.closest('[data-dz]'), ov = $('.dropzone');
  if (!ov) return;
  e.preventDefault(); dragDepth = 0; ov.remove();
  if (!zone) return;
  const files = await readFiles(e.dataTransfer.files);
  if (!files.length) return;
  if (zone.dataset.dz === 'chat') openChat({files});
  else { ui.imp.images.push(...files); ui.imp.result = null; location.hash = '#import'; setTimeout(analyse, 100); }
});

/* ---------- keyboard ---------- */
let gPending = 0;
const GO = {o: 'overview', h: 'holdings', a: 'accounts', c: 'cash', s: 'spending', y: 'history', p: 'plan', t: 'taxes', v: 'advice', i: 'import', ',': 'settings'};
document.addEventListener('keydown', e => {
  const typing = document.activeElement && /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openSearch(); return; }
  // Escape closes the top most thing only: a menu, then a popover or side panel, then the Claude panel
  if (e.key === 'Escape') { if ($('.menu')) closeMenus(); else if (CP.open && !SP.pop && !$('#drawer') && !$('#dlg').open && !$('.fs, .focus, .cmdk-wrap, .story')) closeChat(); return; }
  if (typing || e.metaKey || e.ctrlKey || e.altKey || $('#dlg').open || $('.cmdk-wrap')) return;
  if (gPending && Date.now() - gPending < 1200 && GO[e.key]) { gPending = 0; location.hash = '#' + GO[e.key]; return; }
  gPending = 0;
  if (e.key === '/') { e.preventDefault(); openChat(); }
  else if (e.key === '?') showShortcuts();
  else if (e.key === 'g') gPending = Date.now();
  else if (e.key === 'b' && !(view === 'spending' && SP.tab === 'check')) setPrivate(!document.body.classList.contains('private'));
});
function showShortcuts() {
  const rows = [['/', 'Ask Claude'], ['⌘ K or Ctrl K', 'Search everything'], ['?', 'These shortcuts'], ['g then o, h, a, c, s', 'Overview, Investments, Accounts, Savings & debt, Spending & income'],
    ['g then y, p, t, v, i', 'History, Plan, Taxes, Advice, Import'], ['b', 'Hide or show amounts'], ['Esc', 'Close a panel or menu'],
    ['Enter, S, ←, A', 'Quick check: looks right, skip, back, all from merchant'], ['Right click a row', 'Actions for a transaction or investment']];
  const f = $('#dlgForm');
  f.innerHTML = `<h3>Keyboard shortcuts</h3><div class="keys">${rows.map(([k, l]) => `<div class="key-row"><span>${k.split(' or ').map(x => `<kbd>${esc(x)}</kbd>`).join(' or ')}</span><span class="muted">${esc(l)}</span></div>`).join('')}</div>
    <div class="dialog-actions"><button class="btn" value="close">Close</button></div>`;
  f.onsubmit = null;
  $('#dlg').showModal();
}

/* ---------- small touches ---------- */
const counted = new Set();
function countUp(root = $('#view')) {
  // numbers rise to their value once per page per visit; quick and quiet
  if (matchMedia('(prefers-reduced-motion: reduce)').matches || counted.has(view)) return;
  counted.add(view);
  for (const el of $$('[data-count]', root)) {
    const v = +el.dataset.count, kind = el.dataset.fmt || 'eur', t0 = performance.now(), from = v * 0.92;
    const paint = x => { el.innerHTML = kind === 'sgn' ? sgn(x) : eur(x); };
    const step = now => { const k = Math.min(1, (now - t0) / 520), e = 1 - (1 - k) ** 3; paint(from + (v - from) * e); if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }
}
function skeleton(kind = 'page') {
  return `<div class="stack-y skel">${kind === 'page' ? '<div class="skel-card tall"></div>' : ''}<div class="grid g4">${'<div class="skel-card"></div>'.repeat(4)}</div><div class="grid g2"><div class="skel-card tall"></div><div class="skel-card tall"></div></div></div>`;
}
function milestones() {
  if (!S || !UIS.prefs || UIS.prefs.celebrations === false) return;
  const nw = S.totals.net_worth, list = [];
  const steps = [10e3, 25e3, 50e3, 75e3, 100e3, 150e3, 200e3, 250e3, 300e3, 400e3, 500e3, 750e3, 1e6, 1.5e6, 2e6];
  for (const s of steps) if (nw >= s) list.push({id: 'nw:' + s, text: `Your net worth passed ${fmtV(s, '€', true).replace('k', ',000')}`});
  const hadDebt = (S.history || []).some(h => (h.debt || 0) > 100);
  if (hadDebt && S.totals.debt < 1) list.push({id: 'debt-free', text: 'You are debt free'});
  for (const g of S.goals || []) if (goalProgress(g) >= 1) list.push({id: 'goal:' + g.name, text: `You reached your goal: ${g.name}`});
  const fresh = list.filter(m => !UIS.celebrated.includes(m.id));
  if (!fresh.length) return;
  if (!UIS.celebrated.includes('init')) {
    // the first time, everything already reached counts as celebrated
    fresh.forEach(m => UIS.celebrated.push(m.id));
    uiPost({action: 'celebrated-add', id: 'init'});
    fresh.forEach(m => uiPost({action: 'celebrated-add', id: m.id}));
    return;
  }
  const m = fresh[fresh.length - 1];
  fresh.forEach(x => { UIS.celebrated.push(x.id); uiPost({action: 'celebrated-add', id: x.id}); });
  const el = document.createElement('div');
  el.className = 'celebrate';
  el.innerHTML = `${'<i></i>'.repeat(14)}<div class="cel-box"><b>${esc(m.text)}</b><span class="muted small">Nicely done.</span><button type="button" class="x-btn" aria-label="Close">×</button></div>`;
  document.body.appendChild(el);
  $('button', el).onclick = () => el.remove();
  setTimeout(() => el.remove(), 9000);
}
function goalProgress(g) {
  const have = goalAmount(g);
  return g.target_eur ? have / g.target_eur : 0;
}
function goalAmount(g) {
  if (!S) return 0;
  const t = S.totals;
  if (g.source === 'savings') return t.savings;
  if (g.source === 'investments') return t.self_directed + t.managed;
  if (g.source === 'pot') { const p = (S.pots || []).find(p => p.name === g.pot); return p ? p.saved_eur : 0; }
  if (g.source === 'manual') return g.saved_eur || 0;
  return t.net_worth;
}

/* ---------- start ---------- */
function shellInit() {
  const tools = $('.topbar .tools');
  tools.insertAdjacentHTML('afterbegin', `<div id="rangeSlot" hidden></div>
    <button type="button" class="icon-btn" id="searchBtn" title="Search (⌘K)" aria-label="Search">${ICON.search}</button>
    <button type="button" class="icon-btn" id="viewsBtn" title="Saved views" aria-label="Saved views">${ICON.bookmark}</button>`);
  tools.insertAdjacentHTML('beforeend', `<button type="button" class="icon-btn claude-btn" id="claudeBtn" title="Ask Claude (/)" aria-label="Ask Claude">${CLAUDE_ICON}</button>`);
  $('#searchBtn').onclick = openSearch;
  $('#viewsBtn').onclick = e => { e.stopPropagation(); openViewsMenu(); };
  $('#claudeBtn').onclick = () => CP.open ? closeChat() : openChat();
  // the old chat history in this browser becomes the first saved conversation
  const old = store.get('chat', null);
  if (old && old.length) { CP.conv = {id: null, messages: old}; saveConv(); store.set('chat', []); }
  new MutationObserver(() => { clearTimeout(shellInit.t); shellInit.t = setTimeout(() => { decorateCards(); applyLayout(); capLong(); }, 30); }).observe($('#view'), {childList: true, subtree: true});
  loadUI();
  loadGeo();
}
