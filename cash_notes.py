"""Cash/debt observations. AI selects recorded, calculated facts; it cannot invent rates."""
import hashlib,json,threading,time
from datetime import datetime
import extras

_running=set()
_lock=threading.Lock()
DUO_URL='https://duo.nl/particulier/studieschuld-terugbetalen/terugbetalingsregels.jsp'
def liquid_rows(state,account=None):
    import cash_workspace
    return [{**r,'value':r['balance_eur']} for r in cash_workspace.account_rows(state) if not account or r['id']==account]

def facts(state,account=None):
    cash=liquid_rows(state,account);debts=[d for d in state.get('debts',[]) if not d.get('expected_gift')]
    items=[];spend=state.get('spend_month');reserve=(state.get('profile') or {}).get('buffer_months',4)
    liquid=sum(max(0,s.get('value') or 0) for s in cash if s.get('cash_access') in ('instant','transfer'))
    if spend and spend>0:
        items.append({'text':f'Confirmed-access cash covers {liquid/spend:.1f} months of recorded spending; your buffer target is {reserve} months. Keep that reserve available before considering an extra repayment.','kind':'buffer'})
    available=[s for s in cash if (s.get('value') or 0)>0 and s.get('rate_pct') is not None]
    best=max(available,key=lambda s:s['rate_pct']) if available else None
    for d in debts:
        rate=d.get('rate_pct');name=d['name']
        if rate is None:
            items.append({'text':f'{name}: the interest rate is missing. Add the rate from your latest statement to compare repayment with keeping cash.','kind':'missing'});continue
        if best:
            spread=best['rate_pct']-rate
            outcome='more gross interest' if spread>0 else 'less gross interest' if spread<0 else 'the same gross interest'
            items.append({'text':f"{name} costs {rate:.2f}% at its saved rate; {best['name']} pays {best['rate_pct']:.2f}%. Per 1,000 EUR retained in that account rather than repaid, the difference is {abs(spread)*10:.2f} EUR {outcome} in the first year, before any costs and assuming unchanged rates. This compares marginal rates, not interest on your entire debt.",'kind':'comparison'})
        else:items.append({'text':f'{name}: debt interest is {rate:.2f}%, but no positive cash account has a recorded comparison rate. Add the actual cash rate before comparing.','kind':'missing'})
        if d.get('monthly_payment_eur') is None:items.append({'text':f'{name}: the monthly repayment is not recorded. The no-payment curve is an illustration, not your repayment schedule.','kind':'missing'})
        if 'duo' in name.lower():
            regime=d.get('repayment_regime');fixed=d.get('rate_fixed_until')
            saved=f" Saved regime: {regime or 'not recorded'}; rate fixed until: {fixed or 'not recorded'}."
            items.append({'text':'For DUO, your repayment regime, income-based monthly payment and interest-fix period also matter.'+saved+' Check these in Mijn DUO before deciding to repay early. A bond yield alone is not an equivalent cash return: selling before maturity exposes you to price changes and some bonds carry credit risk.','kind':'duo','url':DUO_URL})
    import savings_rates,cash_workspace
    market=savings_rates.snapshot(offline=True)
    ongoing=[o for o in market['offers'] if not o.get('promotional') and not o.get('new_customers_only') and not o.get('stale')]
    if ongoing:
        sample=1000;eligible=[o for o in ongoing if savings_rates.estimate(o,sample)['eligible'] is True]
        if eligible:
            top=max(eligible,key=lambda o:o['rate_pct'])
            lower=[r for r in cash if r.get('rate_pct') is not None and r.get('value',0)>0 and r['rate_pct']<top['rate_pct'] and r.get('cash_role') not in ('emergency','goal')]
            if lower:
                low=min(lower,key=lambda r:r['rate_pct']);gain=(top['rate_pct']-low['rate_pct'])*10
                items.insert(0,{'text':f"Review cash earning {low['rate_pct']:.2f}% in {low['name']}. {top['name']} via {top['provider']} publishes {top['rate_pct']:.2f}% for flexible cash: about {gain:.2f} EUR more gross interest per 1,000 EUR over a year if both rates stay unchanged. Keep payment liquidity and your reserve available; verify eligibility and transfer timing before moving money.",'kind':'market','url':top['source_url']})
            for d in debts[:1]:
                if d.get('rate_pct') is not None:
                    reference_rate=max(top['rate_pct'],best['rate_pct'] if best else top['rate_pct'])
                    source=("the saved rate at "+best['name']) if best and best['rate_pct']>=top['rate_pct'] else ("the loaded ongoing quote at "+top['name'])
                    gap=reference_rate-d['rate_pct'];advantage='keeping cash has the higher gross rate' if gap>0 else 'repayment saves the higher gross rate' if gap<0 else 'the gross rates are equal'
                    items.insert(1,{'text':f"{d['name']} is at {d['rate_pct']:.2f}%; {source} is {reference_rate:.2f}%. On that comparison, {advantage}. Verify your saved rate and keep your reserve available. DUO rules, income, rate resets and possible forgiveness can change the decision.",'kind':'market_debt','url':DUO_URL if 'duo' in d['name'].lower() else top['source_url']})
    if any(r.get('rate_pct') is None and r.get('value',0)>0 for r in cash):items.append({'text':'Some cash has no confirmed saved interest rate. Record those rates first: unknown interest is not the same as zero interest.','kind':'missing'})
    if any(r.get('cash_access')=='unknown' and r.get('value',0)>0 for r in cash):items.append({'text':'Some broker cash has unverified withdrawal access. Keep it separate from the confirmed emergency buffer until settlement and withdrawal terms are checked.','kind':'access'})
    if not items:items=[{'text':'Keep cash rates and debt statements up to date. Recorded balances and repayments will build a useful comparison.','kind':'general'}]
    return items

def peek(state):
    """Read ready observations without writes, a model call, or a network request."""
    items=facts(state);ident=hashlib.sha256(json.dumps(items,sort_keys=True).encode()).hexdigest()[:24]
    old=extras.read(extras.CACHE/'cash-notes'/f'{ident}.json',{})
    if old.get('items') and time.time()-old.get('at',0)<4*3600:return {**old,'updating':ident in _running}
    ordered=sorted(enumerate(items),key=lambda row:({'market':0,'market_debt':1,'comparison':2,'duo':3,'buffer':4}.get(row[1]['kind'],3),row[0]))
    return {'items':[item for _,item in ordered[:3]],'by':'facts','updating':False}

def briefing(state,exe=None,key=None,account=None):
    items=facts(state,account);ident=hashlib.sha256(json.dumps(items,sort_keys=True).encode()).hexdigest()[:24]
    path=extras.CACHE/'cash-notes'/f'{ident}.json';old=extras.read(path,{})
    if time.time()-old.get('at',0)<4*3600:return {**old,'updating':ident in _running}
    comparison=next((i for i in items if i['kind']=='market'),None) or next((i for i in items if i['kind']=='comparison'),None)
    context=next((i for i in items if i['kind']=='market_debt'),None) or next((i for i in items if i['kind']=='duo'),None) or next((i for i in items if i['kind']=='buffer'),None)
    selected=[]
    for i in [comparison,context,*items]:
        if i and i not in selected:selected.append(i)
        if len(selected)==3:break
    out={'items':selected,'by':'facts','at':time.time(),'time':datetime.now().isoformat(timespec='seconds'),'updating':False}
    path.parent.mkdir(parents=True,exist_ok=True)
    with _lock:
        if ident in _running:return {**out,'updating':True}
        extras.write(path,out)
        if exe or key:
            _running.add(ident);out['updating']=True
            threading.Thread(target=_choose,args=(ident,path,out,items,exe,key),daemon=True).start()
    return out

def _choose(ident,path,out,items,exe,key):
    import spending
    try:
        answer=spending.json_from(spending.run_ai(json.dumps(items), 'Choose up to three useful cash/debt observations. Prefer current source-backed cash alternatives and repayment comparisons, then DUO context and liquidity or missing repayment data. Return only a JSON array of integer fact indices. No invented figures or recommendation to buy or sell.',exe=exe,api_key=key,kind='briefing',level='quick'))
        chosen=list(dict.fromkeys(i for i in answer if type(i) is int and 0<=i<len(items)))[:3]
        if chosen:extras.write(path,{**out,'by':'claude','items':[items[i] for i in chosen],'updating':False})
        else:extras.write(path,{**out,'updating':False})
    except Exception:extras.write(path,{**out,'updating':False})
    finally:
        with _lock:_running.discard(ident)
