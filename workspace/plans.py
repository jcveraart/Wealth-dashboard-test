"""Recurring investment instructions are plans, never evidence of an executed trade."""
import calendar
from datetime import date,timedelta
from . import store
FREQUENCIES={'weekly','biweekly','twice_monthly','monthly','quarterly'}
FIELDS={'account','instrument','isin','amount_eur','frequency','starts_on','day','second_day','active','asset_class','execution_fee_eur','note'}

def validate(fields,old,cfg):
    if set(fields)-FIELDS:raise ValueError('Unsupported savings-plan field.')
    out=dict(fields);merged={**old,**out}
    names=[a['name'] for a in cfg['accounts']]+[cfg['managed'].get('name','Managed portfolio')]
    if merged.get('account') not in names:raise ValueError('Choose an existing investment account.')
    if not str(merged.get('instrument','')).strip():raise ValueError('A plan needs its product name.')
    if merged.get('frequency') not in FREQUENCIES:raise ValueError('Use weekly, biweekly, twice_monthly, monthly or quarterly.')
    if 'amount_eur' in out:out['amount_eur']=store.finite(out['amount_eur'],.01,1000000)
    elif not old.get('amount_eur'):raise ValueError('A plan needs an amount per execution.')
    for key in ('day','second_day'):
        if key in out and out[key] not in (None,''):
            number=store.finite(out[key],1,31)
            if int(number)!=number:raise ValueError('Execution days must be whole calendar days.')
            out[key]=int(number)
        elif key in out:out[key]=None
    merged={**old,**out}
    if merged.get('second_day') is not None and merged.get('second_day')==merged.get('day'):raise ValueError('Twice-monthly executions need distinct days.')
    if 'starts_on' in out:out['starts_on']=store.iso(out['starts_on']) if out['starts_on'] else None
    if 'execution_fee_eur' in out:out['execution_fee_eur']=store.finite(out['execution_fee_eur'],0) if out['execution_fee_eur'] is not None else None
    if 'active' in out and type(out['active']) is not bool:raise ValueError('Running must be true or false.')
    for k in ('account','instrument','isin','note','asset_class'):
        if k in out:out[k]=str(out[k] or '').strip()[:1000]
    return out

def monthly(plan):
    return plan['amount_eur']*{'weekly':52/12,'biweekly':26/12,'twice_monthly':2,'monthly':1,'quarterly':1/3}.get(plan.get('frequency'),1)

def next_date(plan,today=None):
    today=today or date.today()
    if not plan.get('active'):return None
    start=date.fromisoformat(plan['starts_on']) if plan.get('starts_on') else None
    if start and start>=today:return start.isoformat()
    frequency=plan.get('frequency')
    if frequency in ('weekly','biweekly'):
        anchor=start or (date.fromisoformat(plan['last_execution']) if plan.get('last_execution') else None)
        if not anchor:return None
        step=7 if frequency=='weekly' else 14
        candidate=anchor+timedelta(days=max(0,((today-anchor).days//step+1))*step)
        return candidate.isoformat()
    days=[plan.get('day')]
    if frequency=='twice_monthly':
        if not plan.get('day') or not plan.get('second_day'):return None
        days.append(plan['second_day'])
    if not all(days):return None
    for months in range(13):
        y,m=divmod(today.year*12+today.month-1+months,12);m+=1
        anchor=start or (date.fromisoformat(plan['last_execution']) if plan.get('last_execution') else None)
        if frequency=='quarterly' and anchor and (y*12+m-anchor.year*12-anchor.month)%3:continue
        for day in sorted(set(days)):
            candidate=date(y,m,min(day,calendar.monthrange(y,m)[1]))
            if candidate>today:return candidate.isoformat()
    return None

def view(cfg,today=None):
    today=today or date.today();rows=[]
    for index,p in enumerate(cfg.get('savings_plans',[])):
        rows.append({**p,'index':index,'per_month':round(monthly(p),2),'next':next_date(p,today),'schedule_complete':bool(next_date(p,today)) if p.get('active') else True})
    active=[p for p in rows if p.get('active')]
    totals={}
    for p in active:totals[p['account']]=round(totals.get(p['account'],0)+monthly(p),2)
    return {'items':rows,'monthly_eur':round(sum(monthly(p) for p in active),2),'accounts':totals,'scope':'Your recorded instructions only: saving a plan here does not activate, cancel or execute it at a broker. Weekly monthly equivalents use 52 executions/year; twice monthly means exactly 24/year. Calendar dates do not account for broker holiday adjustments. Execution fees and ongoing product fees are distinct and remain unknown unless confirmed.'}
