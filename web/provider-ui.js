'use strict';
function chosenAIProvider(kind) {
  const current = kind === 'chat' ? CP.provider : ui.imp.provider;
  const value = current || store.get(kind + '.provider', null) || S?.status?.ai?.[kind + '_provider'];
  return value === 'openai' ? 'openai' : 'claude';
}
function aiProviderName(kind) { return chosenAIProvider(kind) === 'openai' ? 'OpenAI' : 'Claude'; }
function aiProviderSwitch(kind, busy = false) {
  const selected = chosenAIProvider(kind);
  return `<div class="seg provider-switch" role="group" aria-label="${kind === 'chat' ? 'Chat' : 'Import'} provider">${[['claude', 'Claude'], ['openai', 'OpenAI']].map(([value, name]) =>
    `<button type="button" data-ai-provider="${value}" aria-pressed="${selected === value}" ${busy ? 'disabled' : ''}>${name}</button>`).join('')}</div>`;
}
function bindAIProviderSwitch(control, kind, changed) {
  if (!control) return;
  $$('[data-ai-provider]', control).forEach(button => button.onclick = () => {
    if ((kind === 'chat' ? CP.busy : ui.imp.busy) || button.disabled) return;
    const value = button.dataset.aiProvider;
    if (value === chosenAIProvider(kind)) return;
    if (kind === 'chat') CP.provider = value; else ui.imp.provider = value;
    store.set(kind + '.provider', value);
    $$('[data-ai-provider]', control).forEach(b => b.setAttribute('aria-pressed', b === button));
    changed();
  });
}
function chatProviderControl(panel) {
  if (!$('#cpAsk', panel) || $('.provider-switch', panel)) return;
  const row = document.createElement('div'); row.className = 'provider-picker';
  row.innerHTML = aiProviderSwitch('chat', CP.busy) + `<div class="chat-plan-status">${aiPlanNotice('chat')}</div>`;
  row.insertAdjacentHTML('beforeend',`<label class="small muted">Context <select id="cpContextScope" aria-label="Chat data context" ${CP.busy?'disabled':''}>${[['all','All'],['investments','Investments'],['spending','Spending & purchases'],['planning','Planning'],['documents','Documents & linked payments']].map(([v,l])=>`<option value="${v}" ${(CP.contextScope||store.get('chat.contextScope','all'))===v?'selected':''}>${l}</option>`).join('')}</select></label>`);
  $('#cpAsk', panel).before(row);
  $('#cpContextScope',panel).onchange=e=>{CP.contextScope=e.target.value;store.set('chat.contextScope',CP.contextScope);newChat();toast('Started a fresh chat with '+CP.contextScope+' context.');};
  if((CP.contextScope||store.get('chat.contextScope','all'))!=='all'){ $('#cpAttach',panel).disabled=true; $('#cpAttach',panel).title='Use All context for imports'; }

  bindAIProviderSwitch(row, 'chat', () => {
    // Keep the composer and its selection intact; switching does not rerender the chat.
    $('#cpProviderName', panel).textContent = aiProviderName('chat');
    $('.chat-plan-status', panel).innerHTML = aiPlanNotice('chat');
    bindChatGPTButtons(row);
  });
  bindChatGPTButtons(row);
}
function aiPlanNotice(kind) {
  if (chosenAIProvider(kind) !== 'openai') return '';
  const c = S?.status?.ai?.chatgpt || {};
  const busy = kind === 'chat' ? CP.busy : ui.imp.busy;
  return c.connected
    ? `<span>Using ChatGPT plan</span><a href="https://chatgpt.com/settings/usage" target="_blank" rel="noopener noreferrer">Manage usage</a>`
    : `<button type="button" class="linkish" data-chatgpt-connect ${c.active?`data-profile="${esc(c.active)}"`:''} ${busy?'disabled':''}>Continue with ChatGPT</button>`;
}
function bindChatGPTButtons(root) {
  $$('[data-chatgpt-connect]', root).forEach(b => b.onclick = () => connectChatGPT(b.dataset.profile || null));
}
function updateChatGPTConnection(c) {
  if (!S?.status?.ai) return;
  S.status.ai.chatgpt = c; S.status.ai.has_openai_plan = c.connected;
  const panel = $('#chatPanel');
  if (panel && $('.chat-plan-status', panel)) {
    $('.chat-plan-status', panel).innerHTML = aiPlanNotice('chat'); bindChatGPTButtons(panel);
  }
  if ($('.import-plan-status')) {
    $('.import-plan-status').innerHTML = aiPlanNotice('import'); bindChatGPTButtons($('#view'));
    if (c.connected) $('.banner.warn', $('#view'))?.remove();
  }
  if (view === 'settings') providerSettings();
  if (c.welcome && !connectChatGPT.welcoming) {
    connectChatGPT.welcoming = true;
    const dlg = $('#dlg'), form = $('#dlgForm');
    form.innerHTML = `<h2>You’re using your ChatGPT plan</h2><p>Eligible requests in this dashboard use your existing ChatGPT allowance.</p><p><a href="https://chatgpt.com/settings/usage" target="_blank" rel="noopener noreferrer">Manage usage</a></p><button class="btn primary" id="chatgptWelcome">Got it</button>`;
    $('#chatgptWelcome').onclick = () => { post('/api/chatgpt/welcome', {}).catch(()=>{}); connectChatGPT.welcoming = false; };
    dlg.showModal();
  }
}
async function connectChatGPT(profileId=null) {
  let popup;
  try {
    popup = window.open('about:blank', '_blank');
    if (popup) popup.opener = null;
    const r = await post('/api/chatgpt/start', {profile_id:profileId});
    if (popup) popup.location.href = r.url;
    else {
      const box = $('.chat-plan-status') || $('.import-plan-status') || $('#chatgptConnection');
      box.innerHTML = `<a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">Continue sign-in with ChatGPT</a>`;
    }
    toast('Complete the ChatGPT sign-in in the new tab.');
    clearInterval(connectChatGPT.poll);
    connectChatGPT.poll = setInterval(async () => {
      try {
        const c = await (await fetch('/api/chatgpt/status', {cache:'no-store'})).json();
        if (c.error) throw new Error(c.error);
        if (!['pending','exchanging'].includes(c.phase)) {
          clearInterval(connectChatGPT.poll); updateChatGPTConnection(c);
          if (c.phase !== 'done' || !c.connected) toast(c.message || 'Sign-in expired. Please try again.');
        }
      } catch (e) { clearInterval(connectChatGPT.poll); toast(e.message); }
    }, 2000);
  } catch (e) { if(popup) popup.close(); toast(e.message); }
}
async function providerSettings() {
  const el=$('#providerSettings'); if(!el) return;
  const a=S?.status?.ai || {};
  const sel=(id,label,cur)=>`<select id="${id}" aria-label="${label}"><option value="claude" ${cur!=='openai'?'selected':''}>Claude</option><option value="openai" ${cur==='openai'?'selected':''}>OpenAI</option></select>`;
  el.innerHTML=`<form id="aiProviderForm">
      ${setRow('Chat with','',sel('defaultChatProvider','Default chat provider',a.chat_provider))}
      ${setRow('Read imports with','',sel('defaultImportProvider','Default import provider',a.import_provider))}
      <div id="chatgptConnection" class="set-row"></div>
      <details class="set-more"><summary>OpenAI models</summary><div class="grid g2"><label class="field">Chat model<select id="openaiChatModel"><option value="">Account default</option></select></label><label class="field">Import model<select id="openaiImportModel"><option value="">Account default</option></select></label></div><p class="sub" id="chatgptModelsNote"></p></details>
      <div class="set-save"><button class="btn primary sm">Save choices</button></div>
    </form>`;
  $('#aiProviderForm').onsubmit=async e=>{e.preventDefault();try{await post('/api/settings',{chat_provider:$('#defaultChatProvider').value,import_provider:$('#defaultImportProvider').value,
      openai_chat_model:$('#openaiChatModel').value,openai_import_model:$('#openaiImportModel').value});CP.provider=null;ui.imp.provider=null;store.set('chat.provider',null);store.set('import.provider',null);await load();settings();toast('AI choices saved');}catch(err){toast(err.message);}};
  const c = a.chatgpt || {}, box = $('#chatgptConnection');
  box.innerHTML = `<div class="set-l"><b>ChatGPT plan</b><span>${c.connected?`Connected${c.email?' as '+esc(c.email):''}. Uses your plan's allowance.`:'Connect it to chat and read imports with OpenAI.'}</span>
      ${c.profiles?.length?`<select id="chatgptAccount" aria-label="ChatGPT account" style="margin-top:6px;max-width:320px">${c.profiles.map(p=>`<option value="${esc(p.id)}" ${p.id===c.active?'selected':''}>${esc(p.label)}${p.email?' · '+esc(p.email):''}</option>`).join('')}</select>`:''}</div>
    <div class="set-c">${c.connected?'<a class="linkish" href="https://chatgpt.com/settings/usage" target="_blank" rel="noopener noreferrer">Usage</a>':''}
      ${c.profiles?.length?'<button type="button" class="btn ghost" data-chatgpt-connect>Add account</button>':''}
      ${c.connected?'<button type="button" class="btn ghost" id="chatgptSignout">Sign out</button>':`<button type="button" class="btn sm" data-chatgpt-connect ${c.active?`data-profile="${esc(c.active)}"`:''}>Connect</button>`}</div>`;
  bindChatGPTButtons(box);
  if ($('#chatgptAccount')) $('#chatgptAccount').onchange=async e=>{try{const c=await post('/api/chatgpt/select',{profile_id:e.target.value});updateChatGPTConnection(c);}catch(err){toast(err.message);}};
  if ($('#chatgptSignout')) $('#chatgptSignout').onclick=async()=>{try{const r=await post('/api/chatgpt/signout',{}); const c=await (await fetch('/api/chatgpt/status',{cache:'no-store'})).json();updateChatGPTConnection(c);toast(r.message);}catch(err){toast(err.message);}};
  // Keep saved selections if model loading fails; never silently overwrite choices.
  for (const kind of ['chat','import']) {
    const saved=a['openai_'+kind+'_model'];
    if(saved){const select=$('#openai'+(kind==='chat'?'Chat':'Import')+'Model'); select.add(new Option(saved,saved,true,true));}
  }
  if (c.connected) {
    try {
      const result = await (await fetch('/api/chatgpt/models',{cache:'no-store'})).json();
      if(result.error) throw new Error(result.error);
      if($('#providerSettings')!==el || !el.contains(box)) return;
      for(const kind of ['chat','import']) {
        const select=$('#openai'+(kind==='chat'?'Chat':'Import')+'Model');
        select.innerHTML='<option value="">Account default</option>'+result.models.map(m=>`<option value="${esc(m.id)}" ${a['openai_'+kind+'_model']===m.id?'selected':''}>${esc(m.name)}</option>`).join('');
      }
    } catch(err){if(el.contains(box)) $('#chatgptModelsNote').textContent=err.message;}
  }
}
