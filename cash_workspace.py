"""Cash-account evidence and equal-budget savings/debt scenarios. Never transfers money."""
import csv,hashlib,math,re,unicodedata
from datetime import date,datetime,timedelta
import savings_rates

def norm(value):return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',str(value or '')).encode('ascii','ignore').decode().lower())
def finite(value,default=None):
    try:
        number=float(value);return number if math.isfinite(number) else default
    except (ValueError,TypeError):return default
def account_rows(state):
    rows=[];names=set()
    for index,s in enumerate(state.get('savings',[])):
        if s.get('maturity') or s.get('kind')=='deposit':continue
        fields=('name','bank','platform','rate_pct','rate_effective_date','cash_role','cash_access','cash_note','cash_product_id','payment_account_id','withdrawal_days','legal_bank','guarantee_limit_eur','kind','cash_debit_rate_pct')
        row={**{k:s.get(k) for k in fields},'source':'savings','index':index,'balance_eur':finite(s.get('value'),0),'recorded_balance_eur':finite(s.get('principal_eur')),'balance_date':s.get('snapshot_date')};rows.append(row);names.add(norm(s['name']))
    for index,a in enumerate(state.get('accounts',[])):
        if norm(a['name']) in names or not finite(a.get('cash'),0):continue
        row={**{k:a.get(k) for k in ('name','bank','platform','cash_role','cash_access','cash_note','cash_product_id','payment_account_id','cash_rate_pct','cash_debit_rate_pct','rate_effective_date','withdrawal_days','guarantee_limit_eur','legal_bank')},'source':'broker','index':index,'balance_eur':finite(a['cash'],0),'recorded_balance_eur':finite(a['cash']),'balance_date':a.get('updated'),'rate_pct':finite(a.get('cash_rate_pct')),'kind':'broker'};rows.append(row)
    managed=state.get('managed') or {}
    if finite(managed.get('cash'),0) and norm(managed.get('name')) not in names:
        rows.append({**{k:managed.get(k) for k in ('bank','platform','cash_role','cash_access','cash_note','cash_product_id','payment_account_id','cash_debit_rate_pct','rate_effective_date','withdrawal_days','guarantee_limit_eur','legal_bank')},'name':managed.get('name','Managed cash'),'source':'managed','index':None,'balance_eur':finite(managed['cash'],0),'recorded_balance_eur':finite(managed['cash'],0),'balance_date':managed.get('last_real_date'),'rate_pct':finite(managed.get('cash_rate_pct')),'kind':'broker'})
    for row in rows:
        row['id']=hashlib.sha256((row['source']+'|'+str(row['index'])+'|'+row['name']).encode()).hexdigest()[:20]
        row['rate_pct']=finite(row.get('rate_pct'));row['cash_role']=row.get('cash_role') or ('investing' if row['source'] in ('broker','managed') else 'spending' if row.get('kind')=='payment' else 'unallocated')
        row['cash_access']=row.get('cash_access') or ('instant' if row.get('kind')=='payment' else 'transfer' if row['source']=='savings' else 'unknown')
        row['annual_interest_eur']=round(max(0,row['balance_eur'])*row['rate_pct']/100,2) if row['rate_pct'] is not None else None
        row['monthly_interest_eur']=round(row['annual_interest_eur']/12,2) if row['annual_interest_eur'] is not None else None
        row['annual_debit_cost_eur']=round(-row['balance_eur']*row['cash_debit_rate_pct']/100,2) if row['balance_eur']<0 and row.get('cash_debit_rate_pct') is not None else None
        row['earning_status']='unknown' if row['rate_pct'] is None else 'idle' if row['rate_pct']==0 else 'earning' if row['rate_pct']>0 else 'costing'
    return rows
def summary(state,rows=None):
    rows=rows if rows is not None else account_rows(state);positive=sum(max(0,r['balance_eur']) for r in rows);net=sum(r['balance_eur'] for r in rows)
    usable=sum(max(0,r['balance_eur']) for r in rows if r['cash_access'] in ('instant','transfer'));known=[r for r in rows if r['balance_eur']>0 and r['rate_pct'] is not None];known_total=sum(r['balance_eur'] for r in known)
    yearly=sum(r['annual_interest_eur'] or 0 for r in known);pots=sum(finite(p.get('saved_eur'),0) for p in state.get('pots',[]));spend=finite(state.get('spend_month'));buffer=spend*(finite((state.get('profile') or {}).get('buffer_months'),4)) if spend is not None else None
    # Until the owner confirms overlaps, reserve both rather than overstate movable cash.
    negative_cash=sum(min(0,r['balance_eur']) for r in rows)
    reserve=pots+(buffer or 0)-negative_cash;debt=sum(finite(d.get('balance'),0) for d in state.get('debts',[]) if not d.get('expected_gift'))
    debt_known=[d for d in state.get('debts',[]) if not d.get('expected_gift') and d.get('rate_pct') is not None]
    return {'cash_eur':net,'positive_cash_eur':positive,'withdrawable_eur':usable,'negative_cash_eur':sum(min(0,r['balance_eur']) for r in rows),'known_rate_balance_eur':known_total,'rate_coverage_pct':known_total/positive*100 if positive else None,'weighted_rate_pct':yearly/known_total*100 if known_total else None,'annual_interest_eur':yearly if known else None,'monthly_interest_eur':yearly/12 if known else None,'idle_eur':sum(max(0,r['balance_eur']) for r in rows if r['earning_status']=='idle'),'unknown_rate_eur':sum(max(0,r['balance_eur']) for r in rows if r['earning_status']=='unknown'),'buffer_target_eur':buffer,'buffer_months':usable/spend if spend and spend>0 else None,'pots_eur':pots,'planning_reserve_eur':reserve,'unreserved_eur':max(0,usable-reserve),'reserve_overlap_note':'Pots are reserved in addition to the emergency-buffer target until you confirm overlaps. Unknown or restricted withdrawal access is excluded from movable-cash estimates.','debt_eur':debt,'debt_annual_interest_eur':sum(finite(d['balance'],0)*finite(d['rate_pct'],0)/100 for d in debt_known) if debt_known else None,'debt_rate_coverage':len(debt_known)==len([d for d in state.get('debts',[]) if not d.get('expected_gift')])}
def histories(state,row):
    from workspace import store
    values={}
    if row['source']=='savings':
        path=store.ROOT/'history_accounts.csv'
        if path.is_file():
            with path.open(encoding='utf-8-sig') as file:
                for r in csv.DictReader(file):
                    if r['account']==row['name'] and finite(r.get('value')) is not None:values[r['date']]=float(r['value'])
        for r in state.get('account_history',[]):
            if r['account']==row['name'] and finite(r.get('value_eur')) is not None:values[r['date']]=float(r['value_eur'])
    return [{'date':d,'value_eur':v} for d,v in sorted(values.items()) if d<=date.today().isoformat()]
def report(state,offline=False,refresh=False):
    import spending
    from workspace import store
    rows=account_rows(state);totals=summary(state,rows);offers=savings_rates.snapshot(offline,refresh)
    data=spending.load();payment_accounts=data.get('accounts',{});transactions=data.get('transactions',[]);rates=store.records('ratepoint');today=date.today().isoformat();month=today[:7]
    choices=[{'id':key,'name':value.get('name') or key} for key,value in payment_accounts.items() if value.get('role')!='investment']
    for row in rows:
        exact=[key for key,a in payment_accounts.items() if norm(a.get('name') or key)==norm(row['name']) and a.get('role')!='investment']
        supplied=row.get('payment_account_id');matches=[supplied] if supplied in payment_accounts else exact if len(exact)==1 else []
        tx=sorted([t for t in transactions if t.get('account') in matches and t.get('date','')<=today and not t.get('excluded')],key=lambda t:t['date'],reverse=True)
        current=[t for t in tx if t['date'].startswith(month)]
        row.update(share_pct=max(0,row['balance_eur'])/totals['positive_cash_eur']*100 if totals['positive_cash_eur'] else None,payment_link_status='linked' if matches else 'ambiguous' if len(exact)>1 else 'not linked',payment_count=len(tx) if matches else None,month_in_eur=sum(t['amount'] for t in current if t['amount']>0) if matches else None,month_out_eur=-sum(t['amount'] for t in current if t['amount']<0) if matches else None,recent_payments=[{k:t.get(k) for k in ('id','date','amount','merchant','description')} for t in tx[:6]],history=histories(state,row),rate_history=sorted([r for r in rates if r['account']==row['name'] and r.get('date','')<=today],key=lambda r:r['date']),interest_records=[{'year':f['year'],'interest_received_eur':f.get('interest_received_eur'),'interest_paid_eur':f.get('interest_paid_eur'),'source':f.get('note')} for f in state.get('yearly_flows',[]) if f['account']==row['name'] and (f.get('interest_received_eur') is not None or f.get('interest_paid_eur') is not None)],pots=[p for p in state.get('pots',[]) if p.get('account')==row['name']],savings_plan_monthly_eur=sum(finite(p.get('per_month'),0) for p in state.get('savings_plans',[]) if p.get('active') and p.get('account')==row['name']))
        row['verified_product']=next((o for o in offers['offers'] if o['id']==row.get('cash_product_id')),None)
        row['balance_is_estimated']=row.get('recorded_balance_eur') is not None and abs(row['balance_eur']-row['recorded_balance_eur'])>.005
    return {'accounts':rows,'summary':totals,'offers':offers,'debts':state.get('debts',[]),'pots':state.get('pots',[]),'payment_accounts':choices,'date':today,'scope':'Cash excludes bonds and fixed deposits. Annual/monthly earnings are gross illustrations at saved rates, not interest already paid. Broker portfolio-value history is not cash history. Account movements include transfers.'}
def scenario(body):
    fields=('balance_eur','debt_rate_pct','monthly_payment_eur','lump_eur','extra_monthly_eur','cash_rate_pct','years');values={k:finite(body.get(k)) for k in fields}
    if any(v is None or v<0 for v in values.values()) or values['debt_rate_pct']>100 or values['cash_rate_pct']>100 or not 1<=values['years']<=40:raise ValueError('Enter valid nonnegative amounts, rates and a horizon of 1–40 years.')
    B=values['balance_eur'];L=values['lump_eur'];P=values['monthly_payment_eur'];X=values['extra_monthly_eur'];rd=values['debt_rate_pct']/1200;rc=values['cash_rate_pct']/1200
    keep_debt=B;repay_debt=max(0,B-L);keep_cash=L;repay_cash=max(0,L-B);curve=[];keep_interest=repay_interest=0;keep_payoff=repay_payoff=None
    for m in range(round(values['years']*12)+1):
        if m:
            ki=keep_debt*rd;ri=repay_debt*rd;keep_interest+=ki;repay_interest+=ri
            kp=min(keep_debt+ki,P);rp=min(repay_debt+ri,P+X)
            keep_debt=max(0,keep_debt+ki-kp);repay_debt=max(0,repay_debt+ri-rp)
            keep_cash=keep_cash*(1+rc)+(P+X-kp);repay_cash=repay_cash*(1+rc)+(P+X-rp)
        if keep_debt<=.005 and keep_payoff is None:keep_payoff=m
        if repay_debt<=.005 and repay_payoff is None:repay_payoff=m
        curve.append({'month':m,'keep_debt_eur':round(keep_debt,2),'repay_debt_eur':round(repay_debt,2),'keep_cash_eur':round(keep_cash,2),'repay_cash_eur':round(repay_cash,2),'keep_net_eur':round(keep_cash-keep_debt,2),'repay_net_eur':round(repay_cash-repay_debt,2)})
    return {'curve':curve,'keep_interest_eur':round(keep_interest,2),'repay_interest_eur':round(repay_interest,2),'repay_advantage_eur':round((repay_cash-repay_debt)-(keep_cash-keep_debt),2),'keep_payoff_month':keep_payoff,'repay_payoff_month':repay_payoff,'assumptions':values,'scope':'Equal upfront funds and equal monthly budget. Unused repayment budget is saved after payoff; keeping cash saves the extra monthly budget. Rates are constant, interest compounds monthly, and fees, rate resets and possible DUO forgiveness are not modelled. This calculation changes no records.'}
