import io,json,math,tempfile,threading,unittest
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch
from intelligence import analytics as a,store,sec,service,tools,normalize
from intelligence.data import HTTP,Quiver
import providers,investment_mcp

def company():
    return {'info':{'currentPrice':20,'currency':'EUR','financialCurrency':'EUR','marketCap':1000,'trailingPE':10,'forwardPE':9,'trailingEps':2,'sector':'Technology','country':'Netherlands','fiftyTwoWeekHigh':40},
      'statements':{'income':[{'period':'2025-12-31','items':{'Total Revenue':500,'Net Income':100,'EBIT':150,'Pretax Income':120,'Tax Provision':24}},
                              {'period':'2024-12-31','items':{'Total Revenue':400,'Net Income':80}}],
                    'cashflow':[{'items':{'Operating Cash Flow':150,'Capital Expenditure':-50}}],
                    'balance':[{'items':{'Total Debt':100,'Cash And Cash Equivalents':50,'Stockholders Equity':400}}]}}
def state():
    return {'positions':[{'name':'Alpha','symbol':'ALPHA','account':'Broker','category':'Stock','value':600,'units':30,'cost':450,'trades':[]},
      {'name':'Fund','symbol':'FUND','account':'Broker','category':'ETF','value':400,'units':20,'cost':300,'trades':[]}],
      'accounts':[{'name':'Broker','cash':0}],'savings':[],'managed':{}}

class Analytics(unittest.TestCase):
    def test_concentration_lookthrough_and_costs(self):
        co={'ALPHA':company(),'FUND':{'info':{'currency':'EUR'},'lookthrough':[{'symbol':'ALPHA','weight':.2}]}}
        p=a.portfolio(state(),co,{})
        self.assertAlmostEqual(p['concentration']['hhi'],.52)
        self.assertAlmostEqual(p['concentration']['effective_positions'],1/.52)
        self.assertAlmostEqual(p['lookthrough'][0]['effective_weight_pct'],68)
        self.assertEqual(p['gains']['cost_basis'],750);self.assertEqual(p['gains']['unrealized'],250)
        self.assertIsNone(p['risk']['volatility_pct']);self.assertIsNone(p['risk']['sharpe'])
    def test_missing_fund_data_does_not_invent_exposure(self):
        p=a.portfolio(state(),{},{});self.assertEqual(p['lookthrough_coverage_pct'],0)
        self.assertEqual(p['allocations']['country'][0]['name'],'Unknown')
    def test_metric_units_currency_and_roic(self):
        co=company();f=a.fundamentals(co)
        self.assertAlmostEqual(f['revenue_growth'],.25);self.assertAlmostEqual(f['fcf_yield'],.1)
        self.assertAlmostEqual(f['roic'],.8*150/450)
        co['info']['financialCurrency']='USD';self.assertIsNone(a.fundamentals(co)['fcf_yield'])
    def test_fifo_complete_and_incomplete_lots(self):
        trades=[{'type':'buy','date':'2025-01-01','units':10,'amount':-100},{'type':'buy','date':'2025-02-01','units':10,'amount':-200},{'type':'sell','date':'2025-03-01','units':-12,'amount':240}]
        f=a.fifo(trades,8);self.assertTrue(f['complete']);self.assertEqual(f['realized'],100);self.assertEqual(f['remaining_basis'],160)
        f=a.fifo(trades[1:],8);self.assertFalse(f['complete']);self.assertIsNone(f['realized'])
    def test_return_metrics_risk_contributions_and_beta(self):
        ds=[];d=date(2025,1,1)
        while len(ds)<100:
            if d.weekday()<5:ds.append(d.isoformat())
            d+=timedelta(days=1)
        price=100;series={}
        for i,d in enumerate(ds):price*=1+(.01 if i%2 else -.006);series[d]=price
        p=a.portfolio(state(),{'ALPHA':company(),'FUND':company()},{'ALPHA':series,'FUND':series},series)
        self.assertEqual(p['risk']['observations'],99);self.assertAlmostEqual(p['risk']['beta'],1)
        self.assertAlmostEqual(sum(r['risk_share_pct'] for r in p['contributions']),100)
        self.assertAlmostEqual(p['risk']['max_drawdown_pct'],-.6,places=5)
        self.assertAlmostEqual(p['correlations'][0]['values']['FUND'],1)
    def test_no_daily_metrics_from_long_gaps(self):
        self.assertEqual(a.returns({'2025-01-01':100,'2025-03-01':120}),{})
    def test_scores_are_drillable_and_missing_not_rewarded(self):
        empty=a.score({});self.assertIsNone(empty['overall']);self.assertEqual(empty['coverage_pct'],0)
        sc=a.score(a.fundamentals(company()),50,0,0)
        self.assertIsNotNone(sc['overall']);self.assertTrue(all('rule' in e for c in sc['components'] for e in c['evidence']))
        noearn=a.score({'drawdown_52w':-.5,'fit':100});self.assertIsNone(noearn['overall'])
    def test_fit_and_user_scenarios(self):
        p=a.portfolio(state(),{'ALPHA':company()},{});fit=a.fit(p,company(),'NEW')
        self.assertLess(fit['hhi_after'],fit['hhi_before'])
        rows=a.scenarios(a.fundamentals(company()),[{'name':'Base','years':5,'growth_pct':0,'exit_pe':10,'annual_dividend':0}])
        self.assertEqual(rows[0]['terminal_price'],20);self.assertEqual(rows[0]['cagr_pct'],0)
        with self.assertRaises(ValueError):a.scenarios({},[{'years':0}])
        f=a.fundamentals(company());f['eps']=-1;self.assertIsNone(a.scenarios(f,[{'years':5,'growth_pct':5,'exit_pe':10}])[0]['terminal_price'])

class Database(unittest.TestCase):
    def test_missing_isin_does_not_break_ownership_research(self):
        with patch.object(service,'state',return_value={'positions':[{'symbol':'NKE','isin':None}]}):
            r=service.ownership('NKE',{'info':{}})
        self.assertIsNone(r['score']);self.assertIn('No verified',r['coverage'])
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=store.DB;store.DB=Path(self.tmp.name)/'test.sqlite3'
    def tearDown(self):store.DB=self.old;self.tmp.cleanup()
    def test_migration_observation_dedup_and_provenance(self):
        store.observe('company','ALPHA',company(),'SEC','https://sec.gov/example','2025-12-31','EUR','2026-02-01')
        store.observe('company','ALPHA',company(),'SEC','https://sec.gov/example','2025-12-31','EUR','2026-02-01')
        self.assertEqual(len(store.history('company','ALPHA')),1)
        r=store.latest('company','ALPHA');self.assertEqual(r['currency'],'EUR');self.assertEqual(r['period'],'2025-12-31');self.assertEqual(r['freshness'],'current')
    def test_outbox_signals_idempotent_and_threshold_rules(self):
        service.initialize();store.signal('filing','ALPHA','Filing','Details',{'accession':'x'});store.signal('filing','ALPHA','Filing','Details',{'accession':'x'})
        self.assertEqual(len(store.rows('SELECT * FROM signals')),1);self.assertEqual(len(store.rows('SELECT * FROM deliveries')),1)
        service.action('seen',{'ids':[store.rows('SELECT * FROM signals')[0]['id']]});self.assertEqual(service.alerts()['unread'],0)
    def test_watchlist_save_edit_remove_and_thesis_scenarios(self):
        service.action('watchlist',{'symbol':'alpha','name':'Alpha','thesis':'A real thesis'})
        self.assertEqual(store.rows('SELECT * FROM watchlist')[0]['symbol'],'ALPHA')
        service.action('watchlist',{'symbol':'ALPHA','thesis':'Updated'})
        self.assertEqual(len(store.rows('SELECT * FROM watchlist')),1)
        store.observe('company','ALPHA',company(),'Test')
        result=service.action('thesis',{'symbol':'ALPHA','cases':[{'name':'Base','years':5,'growth_pct':0,'exit_pe':10}]})
        self.assertEqual(result['computed'][0]['terminal_price'],20)
        service.action('watchlist',{'symbol':'ALPHA','delete':True})
        self.assertEqual(store.rows('SELECT * FROM watchlist'),[])
    def test_global_valuation_alert_and_combined_concentration(self):
        service.initialize();store.observe('company','ALPHA',company(),'Test')
        analysis={'positions':[{'name':'Alpha','symbol':'ALPHA','weight_pct':15},{'name':'Alpha','symbol':'ALPHA','weight_pct':15}]}
        opp={'symbol':'ALPHA','fundamentals':{'trailing_pe':10},'changes':{}}
        with patch.object(service,'analyze',return_value=analysis),patch.object(service,'opportunities',return_value={'items':[opp]}):service.evaluate_signals()
        events=store.rows('SELECT * FROM signals');self.assertEqual({r['type'] for r in events},{'concentration','valuation'})
        self.assertIn('30.0%',next(r['detail'] for r in events if r['type']=='concentration'))
    def test_cached_payload_returning_to_earlier_value_is_latest(self):
        store.observe('metric','X',{'value':1},'Source');store.observe('metric','X',{'value':2},'Source')
        store.execute("UPDATE observations SET retrieved_at='2020-01-01T00:00:00+00:00'")
        store.observe('metric','X',{'value':1},'Source')
        self.assertEqual(store.latest('metric','X')['data']['value'],1)
    def test_fx_conversion_and_pence(self):
        prices={'STOCK':{'2025-01-01':200},'EURUSD=X':{'2025-01-01':2},'EURGBP=X':{'2025-01-01':.5}}
        with patch.object(service,'history',side_effect=lambda s:prices.get(s,{})):
            self.assertEqual(service.euro_series('STOCK','USD')['2025-01-01'],100)
            self.assertEqual(service.euro_series('STOCK','GBp')['2025-01-01'],4)
            self.assertEqual(service.euro_series('STOCK',None),{})
    def test_optional_provider_no_key_and_secrets_not_in_status(self):
        with patch('intelligence.data.config',return_value={'quiver_api_key':'SECRET','sec_user_agent':'Wealth test@example.com'}):
            from intelligence.data import connection_status
            self.assertNotIn('SECRET',json.dumps(connection_status()))
        with patch.object(Quiver,'key',return_value=''):
            with self.assertRaises(RuntimeError):Quiver().fetch('ALPHA','insiders')
    def test_history_failure_does_not_discard_company_fundamentals(self):
        with patch('intelligence.service.Yahoo.company',return_value=company()),patch.object(service,'persist_prices',side_effect=RuntimeError('Unavailable')), \
             patch('intelligence.service.sec.company',return_value={'cik':None}),patch('intelligence.service.OpenBB.available',return_value=False),patch.object(Quiver,'key',return_value=''):
            service.refresh_company('ALPHA',True)
        self.assertEqual(a.fundamentals(store.latest('company','ALPHA')['data'])['price'],20)
        self.assertIn('Price history',store.latest('provider_errors','ALPHA')['data'][0])
    def test_edgar_requires_identification_before_any_network_request(self):
        with patch('intelligence.data.config',return_value={}),patch.dict('os.environ',{},clear=True),patch('urllib.request.urlopen') as call:
            with self.assertRaises(RuntimeError):HTTP.get('https://data.sec.gov/test',sec=True)
            call.assert_not_called()
    def test_edgar_request_reserves_shared_rate_slot(self):
        response=unittest.mock.MagicMock();response.__enter__.return_value.read.return_value=b'{}'
        with patch('intelligence.data.config',return_value={'sec_enabled':True,'sec_user_agent':'Wealth test@example.com'}),patch.dict('os.environ',{},clear=True),patch('urllib.request.urlopen',return_value=response):
            self.assertEqual(HTTP.get('https://data.sec.gov/test',sec=True),'{}')
        self.assertGreater(store.setting('sec_rate_limit')['next_request'],0)
    def test_quiver_uses_documented_endpoints_and_paginated_query(self):
        with patch.object(Quiver,'key',return_value='private'),patch('intelligence.data.config',return_value={}),patch.object(HTTP,'get',return_value='[]') as call:
            data,url=Quiver().fetch('AAPL','institutional')
            self.assertEqual(url,'https://api.quiverquant.com/beta/live/sec13f')
            self.assertIn('ticker=AAPL',call.call_args[0][0]);self.assertIn('page_size=500',call.call_args[0][0])
            self.assertEqual(data['records'],[])
            _,url=Quiver().fetch('AAPL','compensation');self.assertIn('executivecompensation/AAPL',url)
    def test_full_13f_history_and_amendment_selection(self):
        for acc,period,filed,shares,amendment in [('q1','2025-03-31','2025-05-01',10,''),('q2','2025-06-30','2025-08-01',15,''),('a2','2025-06-30','2025-08-02',16,'RESTATEMENT'),('add','2025-06-30','2025-08-03',1,'NEW HOLDINGS')]:
            r={'accessionNumber':acc,'cik':'123','form':'13F-HR/A' if amendment else '13F-HR','reportDate':period,'filingDate':filed,'url':'https://sec.gov/'+acc}
            sec.save_filing(r,{'holdings':[{}],'amendment_type':amendment})
            store.execute('INSERT INTO holdings VALUES(?,?,?,?,?,?,?,?)',(acc,'CUSIP|SH|','Issuer','CUSIP',shares,shares*10,'SH',''))
        h=sec.manager_history('123');self.assertEqual(h[0]['accession'],'a2');self.assertEqual(h[0]['changes'][0]['move'],'added');self.assertAlmostEqual(h[0]['changes'][0]['change_pct'],60)

class Filings(unittest.TestCase):
    def test_sec_annual_normalization_excludes_quarters_and_other_currency(self):
        facts={'facts':{'us-gaap':{'Revenues':{'units':{'USD':[{'start':'2025-01-01','end':'2025-12-31','val':100,'form':'10-K','filed':'2026-02-01','accn':'annual'},
               {'start':'2025-10-01','end':'2025-12-31','val':25,'form':'10-K','filed':'2026-02-01'},
               {'start':'2025-01-01','end':'2025-12-31','val':105,'form':'10-K/A','filed':'2026-03-01','accn':'restated'}]}}}}}
        data=normalize.sec_statements(facts,'USD');self.assertEqual(data['income'][0]['items']['Total Revenue'],105)
        self.assertEqual(data['income'][0]['evidence']['Total Revenue']['accession'],'restated')
        self.assertEqual(normalize.sec_statements(facts,'EUR')['income'],[])
    def test_backend_history_summary_ignores_long_gaps_and_has_monthly_returns(self):
        from datetime import datetime,timezone
        pts=[[datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp()*1000,v] for d,v in [('2025-01-31',100),('2025-02-28',110),('2025-03-31',99)]]
        out=a.price_summary(pts);self.assertAlmostEqual(out['drawdown'],-10);self.assertAlmostEqual(out['period_change_pct'],-1)
        self.assertAlmostEqual(out['monthly'][0]['value'],10);self.assertIsNone(out['vol'])
        with self.assertRaises(ValueError):a.price_summary([[float('nan'),1]])
    def test_inconsistent_fund_weights_are_not_used(self):
        co={'FUND':{'lookthrough':[{'symbol':'X','weight':.8},{'symbol':'Y','weight':.8}]}}
        out=a.portfolio(state(),co,{})
        self.assertEqual(out['lookthrough_coverage_pct'],0);self.assertTrue(any(w['title']=='Inconsistent fund weights' for w in out['warnings']))
    def test_13f_units_and_options_do_not_merge(self):
        xml='<informationTable>'+''.join(f'<infoTable><nameOfIssuer>Alpha</nameOfIssuer><cusip>123456789</cusip><value>100</value><shrsOrPrnAmt><sshPrnamt>10</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>{opt}</infoTable>' for opt in ('','<putCall>PUT</putCall>'))+'</informationTable>'
        rows=sec.parse_13f(xml,'2022-01-01');self.assertEqual(len(rows),2);self.assertEqual(rows[0]['value'],100000)
        self.assertEqual(sec.parse_13f(xml,'2025-01-01')[0]['value'],100)
    def test_form4_classification_and_plan_exclusion(self):
        filing={'accessionNumber':'x','filingDate':'2026-01-03','url':'https://sec.gov/x'}
        base='<ownershipDocument><reportingOwner><rptOwnerName>CEO Example</rptOwnerName><officerTitle>CEO</officerTitle></reportingOwner>{transactions}<footnotes><footnote id="F1">Rule 10b5-1 trading plan</footnote></footnotes></ownershipDocument>'
        tx=lambda code,extra='':f'<nonDerivativeTransaction><transactionDate><value>2026-01-01</value></transactionDate><transactionCode>{code}</transactionCode><transactionShares><value>100</value></transactionShares><transactionPricePerShare><value>10</value>{extra}</transactionPricePerShare><sharesOwnedFollowingTransaction><value>500</value></sharesOwnedFollowingTransaction></nonDerivativeTransaction>'
        rows=sec.parse_form4(base.format(transactions=tx('P')+tx('A')+tx('S','<footnoteId id="F1"/>')),'ALPHA',filing)
        self.assertTrue(rows[0]['open_market']);self.assertEqual(rows[0]['value'],1000);self.assertFalse(rows[1]['open_market']);self.assertFalse(rows[2]['open_market']);self.assertTrue(rows[2]['automatic_plan'])
    def test_qoq_exits_and_changes(self):
        h=[{'security':'A','value':10,'shares':20,'name':'A'}];previous={'A':{'security':'A','value':5,'shares':10},'B':{'security':'B','value':5,'shares':10}}
        changes=sec.changes(h,previous);self.assertEqual(changes[0]['move'],'added');self.assertEqual(changes[1]['move'],'exit')

class ToolProtocol(unittest.TestCase):
    def test_large_portfolio_summary_keeps_complete_totals_and_pages_positions(self):
        s=state();s['positions']=[{**s['positions'][0],'name':'Stock '+str(i),'symbol':'X'+str(i),'value':100,'cost':50} for i in range(69)]
        analysis=a.portfolio(s,{},{});analysis.update({'as_of':'2026-10-07','source':'Test','data_status':[]})
        with patch.object(service,'analyze',side_effect=lambda *args:json.loads(json.dumps(analysis))):
            result=tools.call('analyze_portfolio',{});self.assertEqual(result['total'],6900);self.assertEqual(result['total_positions'],69)
            self.assertEqual(len(result['positions']),20);self.assertLess(len(json.dumps(result)),25000)
            first=tools.call('get_portfolio',{'limit':50,'offset':0});second=tools.call('get_portfolio',{'limit':50,'offset':first['next_offset']})
            self.assertEqual(first['total_positions'],69);self.assertEqual(len(first['positions'])+len(second['positions']),69);self.assertIsNone(second['next_offset'])
    def test_mcp_discovery_readonly_and_missing_inputs(self):
        r=investment_mcp.handle({'id':1,'method':'tools/list'});self.assertEqual(len(r['result']['tools']),32)
        self.assertTrue(all(t['annotations']['readOnlyHint'] for t in r['result']['tools']))
        r=investment_mcp.handle({'id':2,'method':'tools/call','params':{'name':'get_company_valuation','arguments':{}}});self.assertTrue(r['result']['isError'])
    def test_no_arbitrary_tool_or_args(self):
        self.assertTrue(tools.safe_call('run_shell',{})['unavailable'])
        self.assertTrue(tools.safe_call('get_portfolio',{'path':'settings.json'})['unavailable'])
    def test_openai_function_call_continuation_preserves_items(self):
        payload={'input':[{'role':'user','content':'Analyse portfolio'}],'tools':tools.openai_definitions(),'tool_choice':'auto'}
        responses=[{'output':[{'type':'reasoning','id':'reason','summary':[]},{'type':'function_call','call_id':'x','name':'analyze_portfolio','arguments':'{"symbol":null,"cik":null}'}]},
                   {'output':[{'type':'message','content':[{'type':'output_text','text':'Analysis complete'}]}]}]
        with patch.object(providers,'request_response',side_effect=responses),patch.object(tools,'safe_call',return_value={'deterministic':True}):
            result=providers.run_responses(payload,'fake',True)
        self.assertEqual(result,responses[1]);self.assertEqual(payload['input'][-1]['type'],'function_call_output');self.assertIn('deterministic',payload['input'][-1]['output'])

if __name__=='__main__':unittest.main()

class FloatCovarianceTests(unittest.TestCase):
    def test_covariance_matches_reference_for_return_series(self):
        import statistics
        from intelligence import analytics
        a=[.001,-.02,.003,.014,-.009]*80;b=[-.003,.004,.012,-.009,.021]*80
        am=statistics.mean(a);bm=statistics.mean(b)
        reference=sum((x-am)*(y-bm) for x,y in zip(a,b))/(len(a)-1)
        self.assertAlmostEqual(analytics.cov(a,b),reference,places=14)
