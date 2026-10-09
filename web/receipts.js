'use strict';
/* Invoice evidence stays separate from bank amounts. Links are always confirmed by the owner. */
const RECEIPTS = {documents: [], sources: [], status: 'all', q: '', loaded: false};
async function loadReceipts() {
  Object.assign(RECEIPTS, await (await fetch('/api/receipts', {cache:'no-store'})).json());
  RECEIPTS.loaded = true;
}
const receiptMoney = (value, currency='EUR') => value == null ? 'Not shown' : currency === 'EUR' ? eur(value,2) : `<span class="amt">${value<0?'−':''}${esc(currency || '?')} ${fmtN(value,2)}</span>`;
const sourceLink = s => `<a class="linkish small" href="/api/receipts/source?id=${encodeURIComponent(s.id)}" target="_blank" rel="noopener">${esc(s.name)}</a>`;
const receiptForPayment = id => RECEIPTS.documents.filter(d => d.links.some(l => l.transaction_id === id));
async function receiptsPage() {
  const box = $('#spBody'); if (!box) return;
  box.innerHTML = '<section class="card"><div class="empty">Loading invoices…</div></section>';
  try { await loadReceipts(); } catch (e) { box.innerHTML = `<div class="banner err">${esc(e.message)}</div>`; return; }
  if (view !== 'spending' || SP.tab !== 'receipts') return;
  const draw = () => {
    const q = RECEIPTS.q.toLowerCase();
    const docs = RECEIPTS.documents.filter(d => (RECEIPTS.status === 'all' || (RECEIPTS.status === 'linked') === !!d.links.length)
      && (!q || [d.supplier,d.invoice_number,d.order_number,...d.items.map(i => i.description)].join(' ').toLowerCase().includes(q))
      && (!SP.accts.length || !d.links.length || d.links.some(l => l.payment && SP.accts.includes(l.payment.account))));
    box.innerHTML = `<section class="card"><div class="card-head"><div><h2>Invoices & receipts</h2><p class="sub">Product details behind your bank payments. No extra spending is added.</p></div>
      <button type="button" class="btn ghost sm" id="receiptImport">Add documents</button></div>
      <div class="controls">${seg('receiptStatus', [['all','All'],['unlinked','To link'],['linked','Linked']],RECEIPTS.status)}
        <input id="receiptSearch" type="search" placeholder="Search products or orders" aria-label="Search receipts" value="${esc(RECEIPTS.q)}"></div>
      ${docs.map(d => `<button type="button" class="list-row row-btn" data-receipt-open="${d.id}"><div><b>${esc(d.supplier || 'Invoice')}</b>
        <div class="muted small">${d.date ? fdate(d.date) + ' · ' : ''}${esc(d.invoice_number || d.order_number || d.attachments[0]?.name || '')} · ${d.items.length} products</div></div>
        <div class="num">${receiptMoney(d.total,d.currency)}<div class="muted small">${d.links.length ? `${d.links.length} payment${d.links.length === 1 ? '' : 's'} linked` : `${d.candidates.length ? 'Possible payment found' : 'To link'}`}</div></div></button>`).join('') ||
        '<div class="empty">Add an Amazon invoice, order screenshot or other receipt on Import, then confirm the payment it belongs to.</div>'}</section>`;
    $('#receiptImport').onclick = () => { ui.imp.mode='receipts'; location.hash='#import'; };
    onSeg('receiptStatus', v => { RECEIPTS.status=v; draw(); });
    $('#receiptSearch').oninput = e => { RECEIPTS.q=e.target.value; const at=e.target.selectionStart; draw(); const el=$('#receiptSearch'); el.focus(); el.setSelectionRange(at,at); };
    $$('[data-receipt-open]', box).forEach(b => b.onclick = () => openReceipt(b.dataset.receiptOpen));
  };
  draw();
}
async function receiptAction(body) {
  const result = await post('/api/receipts/edit',body);
  Object.assign(RECEIPTS,result); RECEIPTS.loaded=true;
  SP.d=null; await loadSpending();
  if (view==='spending' && SP.tab==='receipts') await receiptsPage();
  return result;
}
async function openReceipt(id, backPayment=null) {
  await loadReceipts();
  if (!SP.d) await loadSpending();
  const d = RECEIPTS.documents.find(x => x.id===id); if (!d) return;
  const dialog=$('#dlg'), formEl=$('#dlgForm');
  // A bank detail sheet and a receipt use the same small dialog, with a way back.
  SP.sheet=null;
  dialog.classList.add('wide');
  formEl.innerHTML = `<div class="sh-head"><div><h3>${esc(d.supplier || 'Invoice')}</h3><p class="sub">${d.date ? fdate(d.date) : 'Date not shown'}${d.invoice_number ? ' · Invoice '+esc(d.invoice_number) : ''}${d.order_number ? ' · Order '+esc(d.order_number) : ''}</p></div><div class="num">${receiptMoney(d.total,d.currency)}</div></div>
    <div class="receipt-sources">${d.attachments.map(sourceLink).join(' · ')}</div>
    <div class="receipt-products"><table><thead><tr><th>Product</th><th class="num">Qty</th><th class="num">Line total</th><th>Category</th></tr></thead><tbody>
      ${d.items.map(i => `<tr><td>${esc(i.description)}${i.sku ? `<div class="muted small">${esc(i.sku)}</div>`:''}</td><td class="num">${i.quantity ?? '·'}</td><td class="num">${receiptMoney(i.total,d.currency)}</td>
        <td><select data-receipt-item="${i.id}" aria-label="Category for ${esc(i.description)}"><option value="">Choose category</option>${SP.d.categories.filter(c => c.kind==='expense' || d.total<0 && c.kind==='income').map(c => `<option value="${c.id}" ${c.id===i.category ? 'selected':''}>${esc(c.name)}</option>`).join('')}</select></td></tr>`).join('')}</tbody></table></div>
    ${!d.reconciled ? '<p class="sub">Some product amounts are missing or do not add up to the invoice total. The original is kept; bank spending stays unchanged.</p>' : ''}
    <h4 class="receipt-section">Bank payments</h4>
    ${d.links.map(l => `<div class="list-row"><button type="button" class="linkish" data-receipt-payment="${l.transaction_id}">${l.payment ? `${fdate(l.payment.date)} · ${esc(l.payment.merchant || l.payment.account)} · ${eur(l.payment.amount,2)}` : 'Payment no longer in the ledger'}</button>
      <span class="num">${eur(l.amount_eur,2)} allocated <button type="button" class="linkish small" data-receipt-unlink="${l.transaction_id}">Unlink</button></span></div>`).join('')}
    ${!d.links.length && d.candidates.length ? `<p class="sub">Suggested matches. Check the date, account and amount before confirming.</p>${d.candidates.map(c => `<div class="list-row"><div><b>${esc(c.merchant)}</b><div class="muted small">${fdate(c.date)} · ${esc(acctName(c.account))} · ${esc(c.reason)}</div><div class="muted small receipt-bank-reference">${esc(c.description)}</div></div><div class="num">${eur(c.amount,2)} <button type="button" class="btn ghost sm" data-receipt-confirm="${c.transaction_id}">Confirm link</button></div></div>`).join('')}`:''}
    <details class="opp-more"><summary>${d.links.length ? 'Link another payment' : 'Find a payment manually'}</summary><input id="receiptTxSearch" type="search" placeholder="Merchant, amount, date or account" aria-label="Search bank payments"><div id="receiptTxChoices"></div></details>
    ${d.links.length && d.reconciled && d.currency==='EUR' ? `<p class="sub">Use the confirmed product categories to split the existing payment. Its total remains the same.</p>${d.links.map(l => `<button type="button" class="btn ghost sm" data-receipt-split="${l.transaction_id}">Use product categories for this payment</button>`).join('')}`:''}
    <div class="dialog-actions">${backPayment ? '<button type="button" class="btn ghost" id="receiptBack">Back to payment</button>':''}<button type="button" class="btn" id="receiptDone">Done</button></div>`;
  formEl.onsubmit=e=>e.preventDefault();
  if (!dialog.open) dialog.showModal();
  const act=async body=>{ try { await receiptAction({id, ...body}); await openReceipt(id,backPayment); } catch(e){toast(e.message);} };
  $('#receiptDone').onclick=()=>dialog.close();
  if ($('#receiptBack')) $('#receiptBack').onclick=()=>txSheet(backPayment);
  $$('[data-receipt-item]',formEl).forEach(el=>el.onchange=()=>act({action:'item-category',item_id:el.dataset.receiptItem,category:el.value}));
  $$('[data-receipt-payment]',formEl).forEach(b=>b.onclick=()=>txSheet(b.dataset.receiptPayment));
  $$('[data-receipt-unlink]',formEl).forEach(b=>b.onclick=()=>act({action:'unlink',transaction_id:b.dataset.receiptUnlink}));
  $$('[data-receipt-confirm]',formEl).forEach(b=>b.onclick=()=>act({action:'link',transaction_id:b.dataset.receiptConfirm}));
  $$('[data-receipt-split]',formEl).forEach(b=>b.onclick=()=>act({action:'split-payment',transaction_id:b.dataset.receiptSplit}));
  const choices=()=>{
    const q=$('#receiptTxSearch').value.toLowerCase();
    const rows=SP.d.transactions.filter(t => !d.links.some(l=>l.transaction_id===t.id) && (d.total==null || t.amount*d.total<0)
      && (!q || [t.merchant,t.description,t.date,String(Math.abs(t.amount)),acctName(t.account)].join(' ').toLowerCase().includes(q))).slice(0,20);
    $('#receiptTxChoices').innerHTML=rows.map(t=>`<div class="list-row"><div>${esc(t.merchant)}<div class="muted small">${fdate(t.date)} · ${esc(acctName(t.account))}</div></div><div class="num">${eur(t.amount,2)} <button type="button" class="linkish small" data-receipt-manual="${t.id}">Link</button></div></div>`).join('');
    $$('[data-receipt-manual]',formEl).forEach(b=>b.onclick=()=>{
      const tx=txById(b.dataset.receiptManual), remaining=d.currency==='EUR' && d.total!=null ? Math.max(0,Math.abs(d.total)-d.links.reduce((s,l)=>s+l.amount_eur,0)) : Math.abs(tx.amount);
      const value=prompt('Amount of this bank payment assigned to this invoice (€)',Math.min(Math.abs(tx.amount),remaining).toFixed(2));
      if(value!==null) act({action:'link',transaction_id:tx.id,amount_eur:Number(value.replace(',','.'))});
    });
  };
  $('#receiptTxSearch').oninput=choices; choices();
}
async function paymentReceipts(t) {
  const slot=$('#paymentReceipts'); if(!slot) return;
  try { await loadReceipts(); } catch { return; }
  if(SP.sheet!==t.id || !$('#paymentReceipts')) return;
  const docs=receiptForPayment(t.id), originals=(t.source_ids || []).map(id=>RECEIPTS.sources.find(s=>s.id===id)).filter(Boolean);
  const imported=(SP.d.imports || []).find(i=>i.id===t.import);
  slot.innerHTML=`${originals.length ? `<div class="receipt-sources"><span class="muted small">Bank source</span> ${originals.map(sourceLink).join(' · ')}</div>` : imported ? `<p class="sub">Bank import: ${esc(imported.file)}</p>` : ''}
    ${docs.length ? `<h4 class="receipt-section">Products behind this payment</h4>${docs.map(d=>`<button type="button" class="list-row row-btn" data-payment-receipt="${d.id}"><div><b>${esc(d.supplier || 'Invoice')}</b><div class="muted small">${d.items.slice(0,3).map(i=>esc(i.description)).join(' · ')}${d.items.length>3?' …':''}</div></div><span class="num">${d.items.length} products</span></button>`).join('')}`:
      '<button type="button" class="linkish small" id="paymentAddInvoice">Add an invoice to see its products</button>'}`;
  $$('[data-payment-receipt]',slot).forEach(b=>b.onclick=()=>openReceipt(b.dataset.paymentReceipt,t.id));
  if($('#paymentAddInvoice')) $('#paymentAddInvoice').onclick=()=>{$('#dlg').close();ui.imp.mode='receipts';location.hash='#import';};
}
