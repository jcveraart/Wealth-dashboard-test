'use strict';
/* After every render: long footnotes move into a small info mark beside the card title (click it to read them),
   cards that only say there is nothing yet stay small, and the signals button gets a proper icon. */
const INFO_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>';
const BELL_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 16V11a6 6 0 0112 0v5l1.5 2h-15zM10 20a2 2 0 004 0"/></svg>';
const FOOTNOTE = '.ws-scope,.int-note,.note';

function cardTitleEl(card) {
  return $(':scope > .card-head h2, :scope > h2, :scope > summary, :scope > .card-head summary', card);
}
function isFootnote(el) {
  if (el.matches(FOOTNOTE)) return true;
  // a long, quiet paragraph at the very end of a card is an explanation, not content
  return el.matches('p.muted, p.small, p.sub, div.muted.small, p.ws-private-note') && !el.querySelector('button, a, input, select, b, strong')
    && el.textContent.trim().length > 70 && el.parentElement.children.length > 2;
}
function addInfo(card, notes) {
  const title = cardTitleEl(card);
  if (!title || !notes.length) return false;
  let btn = $(':scope > .info-btn', title);
  if (!btn) {
    btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'info-btn';
    btn.setAttribute('aria-label', 'About these numbers');
    btn.setAttribute('aria-expanded', 'false');
    btn.innerHTML = INFO_ICON;
    btn.dataset.info = '[]';
    const tools = $(':scope > .ctools', title);
    tools ? title.insertBefore(btn, tools) : title.appendChild(btn);
  }
  const texts = JSON.parse(btn.dataset.info);
  for (const n of notes) { const t = n.textContent.trim(); if (t && !texts.includes(t)) texts.push(t); n.remove(); }
  btn.dataset.info = JSON.stringify(texts);
  return true;
}
function tidyFootnotes(root) {
  for (const card of $$('.card', root)) {
    if (card.closest('.fs-box, .pop, .drawer, .panel')) continue;
    const notes = $$(FOOTNOTE, card).filter(n => n.closest('.card') === card);
    // the last paragraph of the card, or of its only body block
    let last = card.lastElementChild;
    if (last && !last.matches('p') && last.children.length > 1 && last.lastElementChild && last.lastElementChild.matches('p')) last = last.lastElementChild;
    if (last && !notes.includes(last) && last.matches('p, div') && isFootnote(last) && last.closest('.card') === card) notes.push(last);
    addInfo(card, notes);
  }
  // footnotes left between cards belong to the card above them
  for (const n of $$(FOOTNOTE + ', .stack-y > p.muted.small', root)) {
    if (n.closest('.card')) continue;
    let prev = n.previousElementSibling;
    while (prev && !prev.matches('.card, .grid')) prev = prev.previousElementSibling;
    const card = prev && (prev.matches('.card') ? prev : $$(':scope > .card', prev).pop());
    if (card) addInfo(card, [n]);
  }
}
function tidyEmpties(root) {
  for (const card of $$('.card', root)) {
    const body = [...card.children].filter(c => !c.matches('.card-head, h2, summary, .sub, .ctools'));
    const quiet = body.length > 0 && body.every(c => c.matches('.empty, .controls, .ws-form-actions, button, .btn') || (c.children.length && [...c.children].every(x => x.matches('.empty, button, .btn, a'))));
    card.classList.toggle('card-empty', quiet && body.some(c => c.matches('.empty') || $('.empty', c)));
  }
}
/* empty cards next to each other share a row instead of each taking the full width */
function groupEmpties(root) {
  for (const stack of $$('.stack-y', root)) {
    let run = [];
    const flush = () => {
      if (run.length >= 2) {
        const g = document.createElement('div');
        g.className = 'grid g3 empty-group';
        run[0].before(g);
        run.forEach(c => g.appendChild(c));
      }
      run = [];
    };
    for (const el of [...stack.children]) { if (el.matches('section.card.card-empty')) run.push(el); else flush(); }
    flush();
  }
}
function tidySignalsButton() {
  const b = $('#intNotification');
  if (!b || b.dataset.icon) return;
  const unread = (b.textContent.match(/\d+/) || [])[0];
  b.dataset.icon = '1';
  b.innerHTML = BELL_ICON;
  if (unread) b.dataset.badge = unread; else delete b.dataset.badge;
}
/* rows placed straight in a card (no list wrapper) get one, so a long run of them can scroll like any other list */
const ROW = '.barrow, .list-row, .row-btn, .rec-card, .todo, .ws-row, .ws-connection, .opp, .news-row, .acc-row, .mini, .rev, .q-item, .sub-row, .advice, .pot, .fund';
function wrapRuns(root) {
  for (const card of $$('.card', root)) {
    let run = [];
    const flush = () => {
      if (run.filter(el => el.matches(ROW)).length >= 8 && run.reduce((h, el) => h + el.offsetHeight, 0) > 480) {
        const box = document.createElement('div');
        box.className = 'row-run';
        run[0].before(box);
        run.forEach(el => box.appendChild(el));
      }
      run = [];
    };
    // group headings inside a list (.grp) belong to the run, so a list split by headings scrolls as one
    for (const el of [...card.children]) { if (el.matches(ROW) || (el.matches('.grp, .opp-h') && run.length)) run.push(el); else if (el.matches('.grp, .opp-h') && el.nextElementSibling && el.nextElementSibling.matches(ROW)) run.push(el); else flush(); }
    flush();
  }
}
function tidyView() {
  const root = $('#view');
  if (!root) return;
  wrapRuns(root);
  tidyFootnotes(root);
  tidyEmpties(root);
  groupEmpties(root);
  tidySignalsButton();
}
let tidyTimer = null;
new MutationObserver(() => { clearTimeout(tidyTimer); tidyTimer = setTimeout(tidyView, 40); }).observe($('#view'), {childList: true, subtree: true});
new MutationObserver(() => { const b = $('#intNotification'); if (b && !b.querySelector('svg')) { delete b.dataset.icon; tidySignalsButton(); } }).observe($('.topbar .tools'), {childList: true, subtree: true, characterData: true});

/* the info mark opens a small note under it */
document.addEventListener('click', e => {
  const btn = e.target.closest('.info-btn');
  const open = $('.info-pop');
  if (open && !e.target.closest('.info-pop')) { open.remove(); $$('.info-btn[aria-expanded="true"]').forEach(b => b.setAttribute('aria-expanded', 'false')); }
  if (!btn) return;
  e.preventDefault();
  e.stopPropagation();
  if (open && open.dataset.for === btn.dataset.info) return;
  const pop = document.createElement('div');
  pop.className = 'info-pop';
  pop.dataset.for = btn.dataset.info;
  pop.innerHTML = JSON.parse(btn.dataset.info).map(t => `<p>${esc(t)}</p>`).join('');
  document.body.appendChild(pop);
  const r = btn.getBoundingClientRect(), w = pop.offsetWidth;
  pop.style.left = Math.max(12, Math.min(innerWidth - w - 12, r.left - 12)) + 'px';
  pop.style.top = Math.min(innerHeight - pop.offsetHeight - 12, r.bottom + 8) + 'px';
  btn.setAttribute('aria-expanded', 'true');
}, true);
addEventListener('scroll', () => { const p = $('.info-pop'); if (p) p.remove(); }, {passive: true});

/* the page area also changes width without the window resizing (the chat panel opening or closing):
   redraw then too, so charts are drawn for the width they really have */
let viewW = 0, viewTimer = null;
new ResizeObserver(([e]) => {
  const w = Math.round(e.contentRect.width);
  if (!viewW) { viewW = w; return; }
  if (Math.abs(innerWidth - lastW) > 40) { viewW = w; return; }  // a window resize redraws by itself
  if (Math.abs(w - viewW) <= 40) return;
  clearTimeout(viewTimer);
  viewTimer = setTimeout(() => {
    viewW = w;
    const busy = $('#dlg[open], .menu, .pop, .fs, .cmdk-wrap') || (document.activeElement && $('#view').contains(document.activeElement) && /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName));
    if (S && !busy) { const y = scrollY; renderView(); requestAnimationFrame(() => scrollTo(0, y)); }
  }, 250);
}).observe($('#view'));
