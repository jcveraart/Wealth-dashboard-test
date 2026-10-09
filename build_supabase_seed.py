"""Build fictional SQL locally; never connect or read a personal runtime."""
import csv,json
from pathlib import Path
ROOT=Path(__file__).absolute().parent

def build(root=ROOT):
    data=Path(root)/'demo_data'
    load=lambda name:json.loads((data/name).read_text(encoding='utf-8'))
    manifest=load('manifest.json')
    if manifest.get('synthetic') is not True:raise ValueError('Only marked synthetic fixtures may be seeded.')
    cfg=load('portfolio.json');sp=load('spending.json');rows={}
    def add(table,value):rows.setdefault(table,[]).append(value)
    add('portfolio_backup',{'id':1,'data':cfg})
    for name in manifest['history_files']['history.csv']:
        with (data/name).open(encoding='utf-8') as f:
            for v in csv.DictReader(f):add('net_worth_daily',{'date':v['date'],**{a:float(v[b]) for a,b in [('net_worth','net_worth'),('assets','gross'),('debt','debt'),('managed','managed'),('savings','savings'),('self_directed','self_directed')]}})
    for ident,v in sp['accounts'].items():add('spending_accounts',{'id':ident,'name':v['name']})
    for v in sp['categories']:add('spending_categories',{'id':v['id'],'name':v['name'],'grp':v['group'],'kind':v['kind']})
    for name in manifest['transaction_files']:
        for v in load(name):add('spending_transactions',{'id':v['id'],'date':v['date'],'amount':v['amount'],'description':v['description'],'merchant':v['merchant'],'account_id':v['account'],'category_id':v.get('category'),'category_source':v.get('category_source'),'note':v.get('note','')})
    def literal(v):
        if v is None:return 'NULL'
        if type(v) is bool:return 'true' if v else 'false'
        if isinstance(v,(int,float)):return str(v)
        if isinstance(v,(dict,list)):return "'"+json.dumps(v).replace("'","''")+"'::jsonb"
        return "'"+str(v).replace("'","''")+"'"
    sql=['-- FICTIONAL DATA ONLY. Use a separate EMPTY demo project after the five schema files.','-- Seeds example payments, net-worth history and the portfolio JSON backup; no cloud connection.','BEGIN;']
    for table,values in rows.items():
        for v in values:sql.append('INSERT INTO '+table+' ('+','.join('"'+k+'"' for k in v)+') VALUES ('+','.join(literal(x) for x in v.values())+') ON CONFLICT DO NOTHING;')
    return '\n'.join(sql+['COMMIT;',''])

if __name__=='__main__':
    target=ROOT/'cache/demo-supabase-seed.sql';target.parent.mkdir(exist_ok=True)
    target.write_text(build(),encoding='utf-8')
    print('Fictional SQL saved in cache/demo-supabase-seed.sql. No connection was made.')
