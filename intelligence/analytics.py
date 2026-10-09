"""Deterministic analytics. Ratios are decimals internally; UI percentages explicitly use pct."""
import math
import statistics as stats
from collections import defaultdict
from datetime import date
from datetime import datetime,timezone

def number(v):
    try:
        n=float(v);return n if math.isfinite(n) else None
    except (ValueError,TypeError):return None
def div(a,b):return a/b if a is not None and b is not None and b!=0 else None
def clamp(v):return max(0,min(100,v)) if v is not None else None
def cov(a,b):
    if len(a)<2:return None
    aa=math.fsum(a)/len(a);bb=math.fsum(b)/len(b)
    return sum((x-aa)*(y-bb) for x,y in zip(a,b))/(len(a)-1)
def correlation(a,b):
    return div(cov(a,b),math.sqrt((cov(a,a) or 0)*(cov(b,b) or 0)))
def returns(series):
    ds=sorted(series);out={}
    for a,b in zip(ds,ds[1:]):
        # Don't turn long missing intervals into daily returns.
        if (date.fromisoformat(b)-date.fromisoformat(a)).days<=5 and series[a]>0:out[b]=series[b]/series[a]-1
    return out
def category(p):
    c=p.get('category','').lower()
    if any(x in c for x in ('bond','obligat','treasur','money market')):return 'Bonds'
    if any(x in c for x in ('crypto','bitcoin','ether')):return 'Crypto'
    if any(x in c for x in ('etf','fund','managed')):return 'Funds'
    if any(x in c for x in ('gold','silver','commod','reit','property')):return 'Alternatives'
    if any(x in c for x in ('cash','deposit','saving')):return 'Cash & deposits'
    return 'Stocks'

def fundamentals(company):
    info=company.get('info',{});statements=company.get('statements',{})
    def val(name):return number(info.get(name))
    income=statements.get('income',[]);cash=statements.get('cashflow',[]);balance=statements.get('balance',[])
    def item(rows,*names,index=0):
        if len(rows)<=index:return None
        data=rows[index].get('items',{})
        return next((number(data[k]) for k in names if number(data.get(k)) is not None),None)
    rev=item(income,'Total Revenue');prior=item(income,'Total Revenue',index=1);earn=item(income,'Net Income');prior_earn=item(income,'Net Income',index=1)
    operating=item(cash,'Operating Cash Flow');capex=item(cash,'Capital Expenditure');fcf=operating+capex if operating is not None and capex is not None else val('freeCashflow')
    debt=item(balance,'Total Debt');debt=debt if debt is not None else val('totalDebt')
    eq=item(balance,'Stockholders Equity');cash_bal=item(balance,'Cash And Cash Equivalents');cash_bal=cash_bal if cash_bal is not None else val('totalCash')
    tax=item(income,'Tax Provision');pretax=item(income,'Pretax Income');ebit=item(income,'EBIT','Operating Income');rate=div(tax,pretax)
    invested=eq+debt-cash_bal if all(v is not None for v in (eq,debt,cash_bal)) else None
    roic=div(ebit*(1-rate),invested) if ebit is not None and rate is not None and 0<=rate<=1 and invested is not None and invested>0 else None
    cap=val('marketCap');price=val('currentPrice') or val('regularMarketPrice')
    def growth(a,b):return (a/b-1) if a is not None and b is not None and b>0 else None
    f={
      'price':price,'currency':info.get('currency'),'financial_currency':info.get('financialCurrency'),'market_cap':cap,
      'trailing_pe':val('trailingPE'),'forward_pe':val('forwardPE'),'price_book':val('priceToBook'),'ev_ebitda':val('enterpriseToEbitda'),
      'revenue':rev if rev is not None else val('totalRevenue'),'revenue_growth':growth(rev,prior) if rev is not None and prior is not None else val('revenueGrowth'),
      'earnings':earn,'earnings_growth':growth(earn,prior_earn) if earn is not None and prior_earn is not None else val('earningsGrowth'),
      'profit_margin':div(earn,rev) if earn is not None and rev else val('profitMargins'),'operating_margin':div(ebit,rev) if ebit is not None and rev else val('operatingMargins'),
      'roe':div(earn,eq) if eq and eq>0 else val('returnOnEquity'),'roic':roic,'fcf':fcf,
      # Market cap and statement amounts may differ in currency; never silently divide them.
      'fcf_yield':div(fcf,cap) if info.get('financialCurrency')==info.get('currency') else None,
      'cash':cash_bal,'debt':debt,'debt_equity':div(debt,eq) if eq and eq>0 else None,
      'net_debt':debt-cash_bal if debt is not None and cash_bal is not None else None,
      'drawdown_52w':price/val('fiftyTwoWeekHigh')-1 if price and val('fiftyTwoWeekHigh') else None,
      'eps':val('trailingEps'),'dividend_yield':val('dividendYield'),'beta_provider':val('beta'),
      'sector':info.get('sector'),'country':info.get('country'),'industry':info.get('industry'),
      'period':income[0].get('period') if income else None,
      'source_note':'Annual statement growth where available; Yahoo TTM/provider growth otherwise. FCF yield requires matching currencies.'}
    return f

def score(metrics,fit=None,smart=None,insider=None,estimate_change=None):
    """Rules v1. Missing components remain absent; overall coverage is always returned."""
    definitions={
      'Quality': [('profit_margin','Net margin',lambda v:clamp(v/.25*100),'0% → 0; 25% → 100'),
                  ('roe','Return on equity',lambda v:clamp(v/.25*100),'0% → 0; 25% → 100'),
                  ('roic','ROIC',lambda v:clamp(v/.20*100),'0% → 0; 20% → 100'),
                  ('debt_equity','Debt / equity',lambda v:clamp(100-v*50),'0 → 100; 2× → 0')],
      'Valuation':[('trailing_pe','Trailing P/E',lambda v:clamp((40-v)/30*100) if v>0 else 0,'10× → 100; 40× → 0; losses → 0'),
                   ('valuation_vs_recorded_median','P/E versus recorded median',lambda v:clamp(50-v*100),'-50% → 100; +50% → 0; actual local snapshots only'),
                   ('fcf_yield','Free cash flow yield',lambda v:clamp(v/.08*100),'0% → 0; 8% → 100'),
                   ('ev_ebitda','EV / EBITDA',lambda v:clamp((25-v)/20*100) if v>0 else 0,'5× → 100; 25× → 0')],
      'Fundamental change':[('revenue_growth','Revenue growth',lambda v:clamp(50+v*200),'-25% → 0; +25% → 100'),
                            ('earnings_growth','Earnings growth',lambda v:clamp(50+v*100),'-50% → 0; +50% → 100'),
                            ('estimate_change','Estimate revisions',lambda v:clamp(50+v*200),'-25% → 0; +25% → 100')],
      'Price dislocation':[('drawdown_52w','Below 52-week high',lambda v:clamp(-v/.50*100),'0% → 0; -50% → 100; not proof of value')],
      'Portfolio fit':[('fit','Diversification fit',lambda v:v,'Backend change in exposure concentration for a 5% cash-funded allocation')],
      'Smart money':[('smart','Disclosed ownership signal',lambda v:v,'Owners × 15 + adders × 10 − reducers × 10; cap 100; delayed 13F')],
      'Insiders':[('insider','Open-market buying signal',lambda v:v,'Distinct buyers × 20 + log10(1 + buy value / $10,000) × 20; plan trades excluded')]
    }
    allmetrics={**metrics,'fit':fit,'smart':smart,'insider':insider,'estimate_change':estimate_change};components=[]
    for name,rules in definitions.items():
        evidence=[]
        for field,label,fn,formula in rules:
            value=number(allmetrics.get(field));points=fn(value) if value is not None else None
            evidence.append({'field':field,'label':label,'value':value,'points':round(points,2) if points is not None else None,'rule':formula})
        known=[e['points'] for e in evidence if e['points'] is not None]
        components.append({'name':name,'score':round(stats.mean(known),1) if known else None,'coverage':len(known)/len(evidence),'evidence':evidence})
    weights={'Quality':.25,'Valuation':.20,'Fundamental change':.15,'Price dislocation':.10,'Portfolio fit':.15,'Smart money':.10,'Insiders':.05}
    known=[c for c in components if c['score'] is not None];coverage=sum(weights[c['name']]*c['coverage'] for c in components)
    total=sum(weights[c['name']] for c in known)
    # A minimum of quality, valuation and change avoids scoring a bare price chart as an opportunity.
    sufficient=all(any(c['name']==k and c['score'] is not None for c in components) for k in ('Quality','Valuation','Fundamental change')) and coverage>=.40
    overall=sum(c['score']*weights[c['name']] for c in known)/total if sufficient else None
    return {'overall':round(overall,1) if overall is not None else None,'coverage_pct':round(coverage*100,1),'components':components,
            'weights':weights,'version':'Rules v1','interpretation':'Screening heuristic, not expected return or a recommendation. Comparable only at similar data coverage.'}

def fifo(trades,units):
    lots=[];realized=0.;matched=0;complete=True
    for t in sorted(trades,key=lambda x:x.get('date','')):
        typ=t.get('type','').lower();qty=abs(number(t.get('units')) or 0);amt=abs(number(t.get('amount')) or 0)
        if typ=='buy' and qty:lots.append([qty,amt/qty])
        elif typ=='sell' and qty:
            remaining=qty;basis=0
            while remaining>1e-8 and lots:
                lot=lots[0];take=min(remaining,lot[0]);basis+=take*lot[1];remaining-=take;lot[0]-=take
                if lot[0]<1e-8:lots.pop(0)
            if remaining>1e-8:complete=False
            else:realized+=amt-basis;matched+=1
    if abs(sum(l[0] for l in lots)-units)>max(.0001,units*.00001):complete=False
    return {'realized':realized if complete and matched else None,'remaining_basis':sum(q*p for q,p in lots) if complete and lots else None,
            'complete':complete,'method':'FIFO of imported EUR cash amounts; requires complete lots matching current units.'}

def portfolio(state,companies,series,benchmark=None,risk_free=0.,account='',asset_class='all'):
    rows=[]
    for p in state.get('positions',[]):
        if account and p['account']!=account:continue
        if asset_class!='all' and category(p)!=asset_class:continue
        sym=p.get('symbol');co=companies.get(sym,{}) if sym else {};f=fundamentals(co)
        r={**p,'symbol':sym,'asset_class':category(p),'sector':f.get('sector') or p.get('sector') or 'Unknown',
           'country':f.get('country') or p.get('region') or 'Unknown','currency':f.get('currency') or p.get('currency') or 'Unknown'}
        r['unrealized']=p['value']-p['cost'] if p.get('cost') is not None else None;r['fifo']=fifo(p.get('trades',[]),p.get('units',0));rows.append(r)
    if asset_class in ('all','Cash & deposits'):
        for a in state.get('accounts',[]):
            if a.get('cash') and (not account or a['name']==account):rows.append({'name':a['name']+' cash','account':a['name'],'value':a['cash'],'asset_class':'Cash & deposits','sector':'Cash','country':'Unknown','currency':'EUR'})
        for s in state.get('savings',[]):
            if s.get('invest') and (not account or s['name']==account):rows.append({'name':s['name'],'account':s['name'],'value':s['value'],'asset_class':'Cash & deposits','sector':'Cash','country':'Unknown','currency':'EUR'})
    m=state.get('managed',{})
    if not any(p.get('managed') for p in state.get('positions',[])) and asset_class in ('all','Funds') and m.get('value') and (not account or account==m['name']):
        rows.append({'name':m['name'],'account':m['name'],'value':m['value'],'asset_class':'Funds','sector':'Unknown','country':'Unknown','currency':'Unknown','estimated':True})
    total=sum(p['value'] for p in rows);combined={}
    for p in rows:
        p['weight_pct']=p['value']/total*100 if total else 0
        key=p.get('isin') or p.get('symbol') or p['name'];combined[key]=combined.get(key,0)+p['weight_pct']/100
    allocations={}
    for key in ('asset_class','sector','country','currency'):
        groups=defaultdict(float)
        for p in rows:groups[p.get(key) or 'Unknown']+=p['value']
        allocations[key]=[{'name':k,'value':v,'weight_pct':v/total*100 if total else 0} for k,v in sorted(groups.items(),key=lambda x:-x[1])]
    hhi=sum(w*w for w in combined.values());warnings=[]
    maxw=max(combined.values(),default=0)
    if maxw>.20:warnings.append({'type':'concentration','title':'A position exceeds 20%','detail':f'Largest combined security: {maxw*100:.1f}% of selected investments.'})
    look=defaultdict(lambda:{'direct':0.,'fund':0.,'via':[]});lookcoverage=0
    for p in rows:
        s=p.get('symbol');co=companies.get(s,{})
        if p['asset_class']=='Funds':
            if sum(number(h.get('weight')) or 0 for h in co.get('lookthrough',[]))>1.0001:
                warnings.append({'type':'coverage','title':'Inconsistent fund weights','detail':p['name']+' reports underlying weights above 100%; look-through excluded pending verification.'});continue
            for h in co.get('lookthrough',[]):
                weight=number(h.get('weight'))
                if not h.get('symbol') or weight is None or not 0<=weight<=1:continue
                q=look[h['symbol']];q['fund']+=p['weight_pct']*weight;q['via'].append(p['name']);lookcoverage+=p['value']*weight
        elif s:look[s]['direct']+=p['weight_pct']
    hidden=[{'symbol':s,**r,'effective_weight_pct':r['direct']+r['fund']} for s,r in look.items()]
    hidden.sort(key=lambda r:-r['effective_weight_pct'])
    if any(h['direct']>0 and h['fund']>0 for h in hidden):warnings.append({'type':'overlap','title':'Fund and stock exposure overlap','detail':'Look-through is partial; top holdings are a lower bound on indirect exposure.'})
    for h in hidden:
        if h['fund']>0 and h['effective_weight_pct']>20:
            warnings.append({'type':'concentration','title':'Hidden concentration in '+h['symbol'],'detail':f"At least {h['effective_weight_pct']:.1f}% combined direct and disclosed fund exposure; unknown fund constituents may add more."})
    for r in allocations['sector'][:1]:
        if r['name'] not in ('Unknown','Cash') and r['weight_pct']>40:warnings.append({'type':'concentration','title':'Sector concentration','detail':f"{r['name']}: {r['weight_pct']:.1f}% of selected investments; fund economic exposures may differ."})
    for key in ('sector','country','currency'):
        unknown=sum(p['value'] for p in rows if p.get(key)=='Unknown')
        if total and unknown/total>.1:warnings.append({'type':'coverage','title':key.title()+' data is incomplete','detail':f'{unknown/total*100:.1f}% of the selected portfolio has no verified classification.'})
    series_returns={s:returns(h) for s,h in series.items()};weights=defaultdict(float)
    for p in rows:
        s=p.get('symbol')
        if s and len(series_returns.get(s,{}))>=60:weights[s]+=p['value']/total if total else 0
    coverage=sum(weights.values());normalized={s:w/coverage for s,w in weights.items()} if coverage else {}
    if rows and coverage<.8:warnings.append({'type':'coverage','title':'Historical risk coverage is limited','detail':f'{coverage*100:.1f}% has sufficient EUR price history; the risk model covers this basket only.'})
    dates=sorted(set.intersection(*(set(series_returns[s]) for s in normalized))) if normalized else []
    pr=[sum(normalized[s]*series_returns[s][d] for s in normalized) for d in dates]
    risk={'coverage_pct':coverage*100,'observations':len(dates),'scope':'Constant-weight model of covered current holdings, in EUR, adjusted prices. Not actual trading performance.',
          'volatility_pct':None,'max_drawdown_pct':None,'beta':None,'sharpe':None,'sortino':None,'risk_free_pct':risk_free*100,
          'risk_free_source':'User assumption (default 0%); not a fetched risk-free curve.'}
    curve=[];contribution=[];matrix=[]
    if len(pr)>=60:
        variance=cov(pr,pr);vol=math.sqrt(variance*252);avg=stats.mean(pr);rf=(1+risk_free)**(1/252)-1
        excess=[r-rf for r in pr];downside=math.sqrt(sum(min(0,r)**2 for r in excess)/len(excess))*math.sqrt(252)
        index=peak=100.;maxdd=0.
        for d,r in zip(dates,pr):
            index*=1+r;peak=max(peak,index);dd=index/peak-1;maxdd=min(maxdd,dd);curve.append({'date':d,'value':index,'drawdown_pct':dd*100})
        br=returns(benchmark or {});common=[d for d in dates if d in br];a=[pr[dates.index(d)] for d in common];b=[br[d] for d in common]
        if len(b)==len(pr):
            bi=100.
            for row,r in zip(curve,b):bi*=1+r;row['benchmark_value']=bi
        risk.update({'volatility_pct':vol*100,'max_drawdown_pct':maxdd*100,'sharpe':div((avg-rf)*252,vol),
                     'sortino':div((avg-rf)*252,downside),'beta':div(cov(a,b),cov(b,b)) if len(a)>=60 else None,
                     'total_return_pct':(index/100-1)*100,'start':dates[0],'end':dates[-1],
                     'benchmark_return_pct':(math.prod(1+r for r in b)-1)*100 if len(b)==len(pr) else None})
        for s,w in normalized.items():
            rr=[series_returns[s][d] for d in dates];rc=div(w*cov(rr,pr),variance)
            contribution.append({'symbol':s,'weight_pct':w*100,'risk_share_pct':rc*100 if rc is not None else None,
                'mean_daily_return_contribution_bps':w*stats.mean(rr)*10000,'daily_return_contributions':[{'date':d,'contribution_bps':w*r*10000} for d,r in zip(dates,rr)],
                'period_price_return_pct':(math.prod(1+r for r in rr)-1)*100})
        for s in normalized:
            rr=[series_returns[s][d] for d in dates]
            matrix.append({'symbol':s,'values':{t:correlation(rr,[series_returns[t][d] for d in dates]) for t in normalized}})
    costs=[p for p in rows if p.get('cost') is not None];gains={'cost_basis':sum(p['cost'] for p in costs),'unrealized':sum(p['unrealized'] for p in costs),
      'cost_coverage_pct':sum(p['value'] for p in costs)/total*100 if total else 0,
      'realized':sum(p['fifo']['realized'] for p in rows if p.get('fifo',{}).get('realized') is not None) if any(p.get('fifo',{}).get('realized') is not None for p in rows) else None,
      'realized_scope':'Only holdings with complete imported FIFO lots; disposed positions and incomplete histories are not included.'}
    values=[]
    for p in rows:
        f=fundamentals(companies.get(p.get('symbol'),{}));pe=f.get('trailing_pe')
        if pe and pe>0:values.append((p['value'],pe))
    valuation={'earnings_yield_pct':sum(v/pe for v,pe in values)/sum(v for v,pe in values)*100 if values else None,
               'coverage_pct':sum(v for v,pe in values)/total*100 if total else 0,'method':'Value-weighted earnings yield over profitable positions with valid P/E; losses and missing earnings excluded.'}
    styles=defaultdict(float)
    for p in rows:
        f=fundamentals(companies.get(p.get('symbol'),{}));value=f.get('trailing_pe');growth=f.get('revenue_growth')
        styles['Value proxy' if value is not None and 0<value<20 else 'Growth proxy' if growth is not None and growth>.15 else 'Unclassified']+=p['value']
    return {'total':total,'positions':sorted(rows,key=lambda r:-r['value']),'allocations':allocations,'concentration':{'hhi':hhi,'effective_positions':1/hhi if hhi else 0,'largest_weight_pct':maxw*100,'top5_weight_pct':sum(sorted(combined.values(),reverse=True)[:5])*100},
       'lookthrough':hidden,'lookthrough_coverage_pct':lookcoverage/total*100 if total else 0,'warnings':warnings,'risk':risk,'curve':curve,
       'correlations':matrix,'contributions':contribution,'gains':gains,'valuation':valuation,
       'style_exposure':[{'name':k,'weight_pct':v/total*100 if total else 0} for k,v in styles.items()],
       'methodology':'Issuer domicile and listing currency are proxies, not revenue geography or economic FX exposure. Style labels are descriptive heuristics, not a regression factor model.'}

def fit(analysis,company,symbol,allocation=.05):
    if not 0<allocation<=.50:raise ValueError('Hypothetical allocation must be above 0 and at most 50%.')
    f=fundamentals(company);sector=f.get('sector');country=f.get('country');currency=f.get('currency')
    weights=defaultdict(float)
    for p in analysis['positions']:weights[p.get('isin') or p.get('symbol') or p['name']]+=p['weight_pct']/100
    security=next((p.get('isin') or symbol for p in analysis['positions'] if p.get('symbol')==symbol),symbol)
    old=sum(w*w for w in weights.values());after={k:v*(1-allocation) for k,v in weights.items()};after[security]=after.get(security,0)+allocation
    new=sum(w*w for w in after.values());overlap=next((h for h in analysis['lookthrough'] if h['symbol']==symbol),None)
    exposures={}
    for k,val in [('sector',sector),('country',country),('currency',currency)]:
        if not val:exposures[k]=None;continue
        before=sum(r['weight_pct']/100 for r in analysis['allocations'][k] if r['name']==val)
        exposures[k]={'name':val,'before_pct':before*100,'after_pct':(before*(1-allocation)+allocation)*100}
    delta=old-new;points=clamp(50+delta*1000) if analysis['total'] else None
    if overlap and overlap['effective_weight_pct']>20:points=clamp((points or 50)-20)
    return {'symbol':symbol,'score':round(points,1) if points is not None else None,'allocation_pct':allocation*100,'hhi_before':old,'hhi_after':new,
            'effective_weight_before_pct':overlap['effective_weight_pct'] if overlap else 0,'exposures':exposures,
            'assumption':'Cash-funded purchase; existing selected investments are proportionally scaled. No sale, taxes, fees or market impact modeled.'}

def scenarios(f,assumptions):
    eps=f.get('eps');price=f.get('price')
    out=[]
    for case in assumptions:
        years=number(case.get('years'));growth=number(case.get('growth_pct'));multiple=number(case.get('exit_pe'));dividend=number(case.get('annual_dividend',0))
        if not years or not 1<=years<=30 or growth is None or not -100<growth<=200 or multiple is None or not 0<multiple<=200 or dividend is None or dividend<0:raise ValueError('Use 1–30 years, growth above -100% through 200%, a positive exit P/E up to 200 and nonnegative dividends.')
        terminal=eps*(1+growth/100)**years*multiple if eps is not None and eps>0 else None
        future=terminal+dividend*years if terminal is not None else None
        out.append({**case,'terminal_price':terminal,'cagr_pct':((future/price)**(1/years)-1)*100 if future is not None and price and price>0 else None,'currency':f.get('currency'),
                    'assumption':'User-entered growth and exit multiple; constant cash dividends, no reinvestment. Illustration, not a forecast.'})
    return out

def price_summary(points):
    if not isinstance(points,list) or len(points)>5000:raise ValueError('Use at most 5000 dated observations.')
    values={}
    for row in points:
        if not isinstance(row,list) or len(row)!=2:raise ValueError('Expected dated price observations.')
        stamp=number(row[0]);value=number(row[1])
        if stamp is None or value is None or value<=0:raise ValueError('Price observations must be finite and positive.')
        dt=datetime.fromtimestamp(stamp/1000,tz=timezone.utc).date().isoformat();values[dt]=value
    dates=sorted(values);peak=0.;dd=0.;ends={}
    for d in dates:
        peak=max(peak,values[d]);dd=min(dd,(values[d]/peak-1)*100);ends[d[:7]]=values[d]
    rr=list(returns(values).values());months=sorted(ends)
    monthly=[{'month':b,'value':(ends[b]/ends[a]-1)*100} for a,b in zip(months,months[1:])]
    yearly={}
    for year in sorted({m[:4] for m in months}):
        ms=[m for m in months if m.startswith(year)];i=months.index(ms[0])
        yearly[year]=(ends[ms[-1]]/ends[months[i-1]]-1)*100 if i else None
    return {'drawdown':dd if dates else None,'vol':math.sqrt(cov(rr,rr)*252)*100 if len(rr)>20 else None,'monthly':monthly,'yearly':yearly,
            'period_change_pct':(values[dates[-1]]/values[dates[0]]-1)*100 if len(dates)>1 else None,
            'positive_months':sum(m['value']>0 for m in monthly),'observations':len(dates),'method':'Backend analysis of the selected closing-price series; not cash-flow-adjusted performance.'}
