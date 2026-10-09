"""Deterministic personal-finance calculations. Predictions always expose assumptions."""
import calendar
import math
import statistics
from collections import defaultdict
from datetime import date,timedelta

def day(value): return date.fromisoformat(str(value)[:10])
def money(v): return round(float(v),2)

def payment_rows(data):
    import spending
    return spending.spending_rows(data)

def recurring(data,today=None,overrides=None):
    today=today or date.today(); cats={c['id']:c for c in data.get('categories',[])}
    groups=defaultdict(list)
    for t in payment_rows(data):
        if cats.get(t.get('category'),{}).get('kind')=='transfer':continue
        if not t.get('date') or day(t['date'])>today:continue
        if (today-day(t['date'])).days>430:continue
        # Include the account and direction so unrelated income/debits cannot merge.
        key=(t.get('account',''),t.get('merchant_key') or t.get('merchant') or t.get('counterparty') or t.get('description',''), t['amount']>=0)
        if key[1]:groups[key].append(t)
    result=[]; overrides=overrides or {}
    for key,rows in groups.items():
        rows=sorted(rows,key=lambda r:r['date'])
        dates=sorted(set(r['date'] for r in rows))
        if len(dates)<3:continue
        gaps=[(day(b)-day(a)).days for a,b in zip(dates,dates[1:])]
        median=statistics.median(gaps)
        freq=next(((name,n) for name,n,tol in [('weekly',7,2),('biweekly',14,3),('monthly',30.44,6),('quarterly',91.31,12),('yearly',365.25,25)] if abs(median-n)<=tol),None)
        if not freq:continue
        tol=max(2,freq[1]*.2)
        if sum(abs(g-freq[1])<=tol for g in gaps)/len(gaps)<.7:continue
        amounts=[abs(r['amount']) for r in rows[-6:]]; typical=statistics.median(amounts)
        if not typical or sum(abs(v-typical)<=max(2,typical*.3) for v in amounts)/len(amounts)<.7:continue
        name,interval=freq; last=rows[-1]; next_date=advance(day(last['date']),name)
        annual_factor={'monthly':12,'quarterly':4,'yearly':1}.get(name,365.25/interval)
        active=(today-day(last['date'])).days<=interval*1.7
        while next_date<today:next_date=advance(next_date,name,day(last['date']).day)
        ident='|'.join(map(str,key)); override=overrides.get(ident,{})
        if override.get('dismissed'):continue
        prior=statistics.median([abs(r['amount']) for r in rows[-4:-1]])
        result.append({'id':ident,'name':last.get('merchant') or str(key[1]),'account':key[0],'direction':'income' if key[2] else 'expense',
          'amount_eur':money(last['amount']),'monthly_eur':money(abs(last['amount'])*annual_factor/12),
          'annual_eur':money(abs(last['amount'])*annual_factor),'frequency':name,'next_date':next_date.isoformat(),
          'last_date':last['date'],'previous_amount_eur':money(prior),'change_eur':money(abs(last['amount'])-prior),
          'change_pct':round((abs(last['amount'])/prior-1)*100,2) if prior else None,'active':active,
          'evidence_ids':[r['id'] for r in rows[-8:]],'confidence':'Detected pattern, not a confirmed contract',
          'category':last.get('category'),'source':'Imported payment history'})
    return sorted(result,key=lambda r:(not r['active'],r['next_date'],r['name']))

def advance(d,frequency,anchor=None):
    if frequency in ('weekly','biweekly'):return d+timedelta(days=7 if frequency=='weekly' else 14)
    n={'monthly':1,'quarterly':3,'yearly':12}.get(frequency)
    if n is None:raise ValueError('Unsupported frequency.')
    index=d.year*12+d.month-1+n;y,m=divmod(index,12);m+=1
    return date(y,m,min(anchor or d.day,calendar.monthrange(y,m)[1]))

def forecast(data,balances,bills=(),days=90,today=None,recurrences=None,starting=None):
    today=today or date.today();days=max(1,min(366,int(days)))
    # Starting values are confirmed account balances, never guessed from transactions.
    values=[b for b in balances if b.get('kind') in ('payment','Current account','Cash','cash') or b.get('current')]
    if starting is not None:opening=float(starting);basis='User-entered opening balance'
    elif values:opening=sum(b.get('value',b.get('balance',b.get('principal_eur',0))) for b in values);basis='Current payment/cash accounts in the dashboard'
    else:opening=None;basis='No current payment-account balance available. Set an opening balance to calculate a forecast.'
    scheduled=[];detected=recurrences if recurrences is not None else recurring(data,today)
    manual_keys={b.get('recurrence_id') for b in bills if b.get('recurrence_id')}
    specs=[{'name':r['name'],'amount_eur':r['amount_eur'],'due':r['next_date'],'frequency':r['frequency'],'account':r['account'],'source':'Detected recurring payment','evidence_ids':r['evidence_ids']} for r in detected if r['active'] and r['id'] not in manual_keys]
    specs += [{**b,'source':'Saved commitment'} for b in bills if b.get('active',True)]
    end=today+timedelta(days=days)
    for b in specs:
        due=day(b['due']);anchor=due.day;freq=b.get('frequency','once')
        if freq!='once':
            for _ in range(600):
                if due>=today:break
                due=advance(due,freq,anchor)
        for _ in range(366):
            if due>end:break
            if due>=today:scheduled.append({'date':due.isoformat(),'name':b['name'],'amount_eur':money(b['amount_eur']),'account':b.get('account',''),'source':b['source'],'evidence_ids':b.get('evidence_ids',[])})
            if freq=='once':break
            due=advance(due,freq,anchor)
    scheduled.sort(key=lambda r:(r['date'],r['name']));bydate=defaultdict(float)
    for r in scheduled:bydate[r['date']]+=r['amount_eur']
    current=opening;curve=[]
    for i in range(days+1):
        stamp=(today+timedelta(days=i)).isoformat()
        if current is not None:current+=bydate[stamp]
        curve.append({'date':stamp,'balance_eur':money(current) if current is not None else None,'scheduled_eur':money(bydate[stamp])})
    checkpoints={str(n):next((r['balance_eur'] for r in curve if r['date']==(today+timedelta(days=n)).isoformat()),None) for n in (30,60,90)}
    return {'opening_eur':opening,'basis':basis,'curve':curve,'events':scheduled,'checkpoints':checkpoints,
      'lowest_eur':min((r['balance_eur'] for r in curve if r['balance_eur'] is not None),default=None),
      'assumptions':'Scheduled commitments and detected recurring payments only. Variable spending and unknown income are excluded; this is not a guaranteed balance.',
      'sources':[{'name':b['name'],'value':b.get('value',b.get('balance'))} for b in values]}

def spending_analysis(data,month=None,budgets=(),tags=()):
    import spending
    month=month or date.today().strftime('%Y-%m');start=day(month+'-01')
    previous=(start-timedelta(days=1)).strftime('%Y-%m')
    cats={c['id']:c for c in data.get('categories',[])}
    totals={month:defaultdict(float),previous:defaultdict(float)};merchant=defaultdict(lambda:defaultdict(float));trend=defaultdict(lambda:defaultdict(float));evidence=defaultdict(list)
    for t in payment_rows(data):
        for p in spending.parts(t):
            cat=cats.get(p.get('category'),{})
            if cat.get('kind')=='transfer':continue
            kind=cat.get('kind','expense');amt=-p['amount'] if kind=='expense' else p['amount']
            m=p['date'][:7];trend[m][kind]+=amt
            if m in totals and kind=='expense':totals[m][p.get('category','uncategorized')]+=amt
            if m==month and kind=='expense':
                k=p.get('merchant') or p.get('description') or 'Unknown';merchant[k][m]+=amt;evidence[k].append(p['id'])
            if m==previous and kind=='expense':merchant[p.get('merchant') or p.get('description') or 'Unknown'][m]+=amt
    changes=[{'category':k,'name':cats.get(k,{}).get('name',k),'current_eur':money(totals[month][k]),'previous_eur':money(totals[previous][k]),'change_eur':money(totals[month][k]-totals[previous][k])} for k in set(totals[month])|set(totals[previous])]
    out=[]
    for b in budgets:
        period=b.get('period','monthly');cat=b.get('category','');limit=float(b['limit_eur']);spent=0
        for t in payment_rows(data):
            for p in spending.parts(t):
                if (p['date'][:4]==month[:4] if period=='yearly' else p['date'][:7]==month) and (not cat or p.get('category')==cat) and cats.get(p.get('category'),{}).get('kind')=='expense':spent-=p['amount']
        carry=0
        if b.get('carryover') and period=='monthly' and b.get('since'):
            since=b['since'][:7];months=(start.year-int(since[:4]))*12+start.month-int(since[5:7])
            if months>=0:
                past=sum(-p['amount'] for t in payment_rows(data) for p in spending.parts(t) if since<=p['date'][:7]<month and (not cat or p.get('category')==cat) and cats.get(p.get('category'),{}).get('kind')=='expense')
                carry=months*limit-past
        out.append({**b,'spent_eur':money(spent),'carryover_eur':money(carry),'available_eur':money(limit+carry-spent),'effective_limit_eur':money(limit+carry)})
    merchants=[{'name':k,'current_eur':money(v[month]),'previous_eur':money(v[previous]),'change_eur':money(v[month]-v[previous]),'transaction_ids':list(dict.fromkeys(evidence[k]))[:100]} for k,v in merchant.items()]
    return {'month':month,'comparison_month':previous,'categories':sorted(changes,key=lambda r:abs(r['change_eur']),reverse=True),
      'merchants':sorted(merchants,key=lambda r:abs(r['change_eur']),reverse=True),
      'trend':[{'month':m,'expenses_eur':money(v['expense']),'income_eur':money(v['income']),'net_eur':money(v['income']-v['expense'])} for m,v in sorted(trend.items())],
      'budgets':out,'scope':'Imported payment accounts, with splits and transfers handled by existing spending categories. Current incomplete month is compared with the full previous month.'}

def stress(state,assumptions):
    equity=float(assumptions.get('equity_pct',-20));bonds=float(assumptions.get('bonds_pct',-5));crypto=float(assumptions.get('crypto_pct',-40));months=int(assumptions.get('income_loss_months',3));expense=float(assumptions.get('monthly_expense_eur',0))
    positions=state.get('positions',[]);rows=[]
    for p in positions:
        cat=p.get('category','');shock=crypto if 'crypto' in cat.lower() else bonds if 'bond' in cat.lower() else equity
        value=p.get('value',0);rows.append({'name':p['name'],'account':p['account'],'before_eur':money(value),'shock_pct':shock,'after_eur':money(value*(1+shock/100)),'change_eur':money(value*shock/100)})
    impact=sum(r['change_eur'] for r in rows)-months*expense
    return {'positions':rows,'expense_reserve_eur':money(months*expense),'net_worth_impact_eur':money(impact),'assumptions':assumptions,'scope':'User-defined instantaneous asset-price shocks plus specified expense reserve. No probability, tax effect or recovery forecast is assumed.'}

def goal_projection(goal,today=None):
    today=today or date.today();saved=float(goal.get('saved_eur',0));target=float(goal['target_eur']);due=day(goal['due']);months=max(0,(due.year-today.year)*12+due.month-today.month)
    remaining=max(0,target-saved)
    return {**goal,'remaining_eur':money(remaining),'months_left':months,'monthly_required_eur':money(remaining/months) if months else None,'progress_pct':round(min(100,saved/target*100),2) if target else 100,'scope':'No investment growth assumed; saved amount must refer to money reserved for this goal.'}
