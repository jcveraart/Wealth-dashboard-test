import csv
import io
import json
import zipfile
from datetime import date
from pathlib import Path
from . import service,store,performance

def cell(v):
    if isinstance(v,str) and v[:1] in ('=','+','-','@'):return "'"+v
    return v

def csv_data(rows,fields):
    out=io.StringIO();writer=csv.writer(out);writer.writerow(fields)
    for r in rows:writer.writerow([cell(r.get(k,'')) for k in fields])
    return out.getvalue()

def synthetic():
    return {'accounts':[{'name':'Demo Broker','cash_eur':1500,'closed_cashflow_eur':0,'profit_extra_eur':0,'since':'2024-01','positions':[
      {'name':'Example Global Fund','isin':'IE00B4L5Y983','category':'Broad ETF','units':100,'cost_eur':8500,'net_cashflow_eur':-8500,'ref_price_eur':100,'tickers':['IWDA.AS']},
      {'name':'Example Technology Holding','isin':'US0378331005','category':'Stock','units':20,'cost_eur':3000,'net_cashflow_eur':-3000,'ref_price_eur':175,'tickers':['AAPL']}]}],
      'managed':{'name':'Demo Managed Portfolio','value_eur':20000,'value_date':date.today().isoformat(),'profit_at_value_date_eur':2000,'start_value_eur':18000,'start_date':'2024-01-01','fees_paid_eur':100,'positions':[],'proxy':{'IWDA.AS':.8,'IEAC.AS':.2}},
      'savings':[{'name':'Demo Current Account','principal_eur':2500,'rate_pct':0,'snapshot_date':date.today().isoformat(),'kind':'payment','invest':False},{'name':'Demo Savings','principal_eur':10000,'rate_pct':2,'snapshot_date':date.today().isoformat(),'invest':False}],
      'debts':[{'name':'Demo Loan','balance_eur':5000,'rate_pct':2,'snapshot_date':date.today().isoformat(),'monthly_payment_eur':100,'expected_gift':False}],
      'profile':{'home_country':'NL','buffer_months':4,'monthly_invest_eur':200},'goals':[],'pots':[],'watchlist':[],'account_history':[],'yearly_flows':[],'todos':[],'refresh_minutes':5}

def demo_bundle():
    import spending
    import profiles
    out=io.BytesIO();paths=[store.ROOT/name for name in profiles.source_files(store.ROOT) if name!='README.md']
    paths += [store.ROOT/name for name in ('install.py','start-demo-windows.bat','start-personal-windows.bat','start-windows.bat','start-mac.command','start-demo-mac.command','start-demo-linux.sh','start-personal-mac.command','start-personal-linux.sh','install-optional-windows.bat','stop-demo-windows.bat','stop-personal-windows.bat') if (store.ROOT/name).is_file()]
    paths += [p for p in (store.ROOT/'docs').rglob('*') if p.is_file() and p.suffix.lower() in ('.md','.png','.jpg')]
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(set(paths)):
            z.write(p,p.relative_to(store.ROOT).as_posix())
        p=synthetic();z.writestr('portfolio.json',json.dumps(p,indent=2));z.writestr('portfolio.example.json',json.dumps(p,indent=2))
        d=spending.empty();d['transactions']=[{'id':'demo-groceries','account':'Demo Current Account','date':date.today().isoformat(),'amount':-42.5,'description':'Fictional grocery purchase','merchant':'Example Grocer','merchant_key':'examplegrocer','category':'groceries','category_source':'user','checked':True,'country':'NL'}];d['accounts']={'Demo Current Account':{'name':'Demo Current Account','role':'payment'}}
        z.writestr('spending.json',json.dumps(d));z.writestr('settings.json','{}');z.writestr('.gitignore','cache/\nbackups/\n.chatgpt/\n.openbb-env/\nattachments/\nsettings.json\n')
        z.writestr('README.md','# Fictional wealth dashboard\n\nAll included balances and payments are invented. No owner database, invoices, credentials, chats or Git history is included.\n\nOn Windows run start-windows.bat, or install requirements.txt and run python app.py. Open http://127.0.0.1:8051. The launcher starts with a disconnected fictional demo. Read web/guide.html for setup and a separate personal workspace. Optional private integrations start disconnected.\n')
    raw=out.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if any(n.startswith(('.git/','.chatgpt/','attachments/','cache/','backups/')) for n in z.namelist()):raise ValueError('Unexpected private content in generated demo.')
        for n in z.namelist():
            if Path(n).suffix.lower() in ('.png','.jpg','.jpeg'):continue
            text=z.read(n).decode('utf-8')
            import re
            if re.search(r'sk-(?:proj|svcacct)-[A-Za-z0-9_-]{20,}',text):raise ValueError('Credential reference detected in generated demo.')
    return raw

def export(what,q):
    stamp=date.today().isoformat()
    if what=='fund-template':return csv_data([],['fund_isin','instrument','name','weight_pct','sector','country','currency','as_of']),'fund-holdings-template.csv','text/csv; charset=utf-8'
    if what=='calendar':
        from . import cashflow
        def text(s):return str(s or '').replace('\\','\\\\').replace('\n','\\n').replace(';','\\;').replace(',','\\,')
        rows=[{'id':'bill:'+r['id'],'name':r['name'],'date':r['due'],'note':'Saved financial commitment'} for r in store.records('bill') if r.get('active')]
        for kind,key in [('policy','expiry'),('decision','review_date'),('claim','due'),('goal','due')]:rows += [{'id':kind+':'+r['id'],'name':r['name'],'date':r[key],'note':kind+' review'} for r in store.records(kind) if r.get(key)]
        lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Wealth Dashboard//Local dates//EN','CALSCALE:GREGORIAN']
        import hashlib
        for r in rows:
            lines += ['BEGIN:VEVENT','UID:'+hashlib.sha256(r['id'].encode()).hexdigest()+'@wealth.local','DTSTAMP:'+store.now().replace('-','').replace(':','').replace('+0000','Z'),'DTSTART;VALUE=DATE:'+r['date'].replace('-',''),'SUMMARY:'+text(r['name']),'DESCRIPTION:'+text(r['note']),'END:VEVENT']
        return '\r\n'.join(lines+['END:VCALENDAR'])+'\r\n','wealth-dates-'+stamp+'.ics','text/calendar; charset=utf-8'
    if what=='ledger-template':
        fields=['account','date','executed_at','type','instrument','name','currency','amount','units','amount_eur','fee_eur','tax_eur','reference','split_ratio']
        return csv_data([],fields),'broker-ledger-template.csv','text/csv; charset=utf-8'
    if what=='ledger':
        fields=['account','date','type','instrument','name','currency','amount','units','amount_eur','fee_eur','tax_eur','source_id','reference']
        return csv_data(performance.ledger(q.get('account','')),fields),'broker-ledger-'+stamp+'.csv','text/csv; charset=utf-8'
    if what=='demo':return demo_bundle(),'wealth-fictional-demo.zip','application/zip'
    if what=='annual':
        pack=service.annual_pack(q.get('year',date.today().year-1));out=io.BytesIO();import receipts
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('evidence-inventory.json',json.dumps(pack,ensure_ascii=False,indent=2));seen=set();total=0
            for account in pack['checklist']:
                for d in account['evidence_candidates']:
                    if d['source_id'] in seen:continue
                    seen.add(d['source_id']);path,item=receipts.source(d['source_id']);raw=path.read_bytes();total+=len(raw)
                    if total>150*1024*1024:raise ValueError('Annual pack exceeds 150 MB; export documents separately.')
                    name=Path(item['name']).name.replace('\\','_').replace('/','_');z.writestr('evidence/'+d['source_id'][:12]+'-'+name,raw)
        return out.getvalue(),'annual-evidence-'+pack['year']+'.zip','application/zip'
    if what=='xlsx':
        from openpyxl import Workbook
        wb=Workbook();wb.remove(wb.active)
        tables={'Holdings':service.state()['positions'],'Ledger':performance.ledger(),'Payments':service.spending_data()['transactions'],'Goals':store.records('goal'),'Claims':store.records('claim'),'Decisions':store.records('decision')}
        for name,rows in tables.items():
            sheet=wb.create_sheet(name);keys=list(dict.fromkeys(k for r in rows for k,v in r.items() if not isinstance(v,(dict,list))))
            sheet.append(keys)
            for r in rows:sheet.append([cell(r.get(k)) for k in keys])
            sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
        out=io.BytesIO();wb.save(out);return out.getvalue(),'wealth-tables-'+stamp+'.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    data=service.digest() if what=='digest' else service.get(what,q)
    return json.dumps(data,ensure_ascii=False,indent=2),'wealth-'+what+'-'+stamp+'.json','application/json'
