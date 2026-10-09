import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import cash_workspace as cash,savings_rates as rates,extras
from workspace import store

def product(id='X1',rate='2.5',**overrides):
    p={'id':id,'productType':'OVERNIGHT','currency':'EUR','interestRateModality':'VARIABLE','interestRates':{'interestRateNominal':rate,'effectiveDate':'2026-01-01'},'conditions':{'opening':{'minimumAmount':'1'},'maximumBalance':'100000','withdrawal':{'enabled':True},'termination':{'noticePeriod':None}},'depositTakingBank':{'name':'Example Bank','legalName':'Example Bank SA','branchCountry':{'name':'France'},'statutoryDepositGuaranteeScheme':{'insuredAmount':'100000','currency':'EUR','name':'Example scheme'}},'termNormalized':None}
    p.update(overrides);return p
def page(products):return '<script id="__NEXT_DATA__" type="application/json">'+json.dumps({'props':{'pageProps':{'component':{'initialCatalogProducts':products}}}})+'</script>'
class PublicRates(unittest.TestCase):
    def test_only_withdrawable_eur_products_are_included(self):
        rows=[product(),product('FIX',productType='TERM'),product('USD',currency='USD'),product('NOTICE',conditions={'withdrawal':{'enabled':True},'termination':{'noticePeriod':{'period':30,'unit':'days'}}})]
        parsed=rates.parse_raisin(page(rows));self.assertEqual(len(parsed),1);self.assertEqual(parsed[0]['rate_pct'],2.5);self.assertEqual(parsed[0]['legal_bank'],'Example Bank SA');self.assertEqual(parsed[0]['guarantee_limit_eur'],100000)
    def test_promotional_return_is_only_for_its_verified_period(self):
        promo=product('PROMO',termNormalized={'months':3});promo['conditions']['opening']['restrictedToNewCustomers']='restricted_to_new_customers'
        row=rates.parse_raisin(page([promo]))[0];self.assertTrue(row['promotional']);value=rates.estimate(row,10000);self.assertEqual(value['interest_eur'],62.5);self.assertEqual(value['months'],3);self.assertIsNone(value['eligible'])
    def test_limits_missing_duration_and_malformed_pages_withhold_values(self):
        row=rates.parse_raisin(page([product()]))[0];self.assertIsNone(rates.estimate(row,200000)['interest_eur']);self.assertIsNone(rates.estimate({**row,'promotional':True,'promo_months':None},1000)['interest_eur'])
        with self.assertRaises(ValueError):rates.parse_raisin('<p>Earn 99% now</p>')
    def test_future_rate_is_not_presented_as_effective_today(self):
        row=product();row['interestRates']['effectiveDate']='2099-01-01'
        with self.assertRaises(ValueError):rates.parse_raisin(page([row]))
    def test_guarantee_in_foreign_currency_is_not_relabelled_as_euros(self):
        row=product();row['depositTakingBank']['statutoryDepositGuaranteeScheme'].update(insuredAmount='1150000',currency='SEK')
        parsed=rates.parse_raisin(page([row]))[0];self.assertIsNone(parsed['guarantee_limit_eur']);self.assertEqual(parsed['guarantee_amount'],1150000);self.assertEqual(parsed['guarantee_currency'],'SEK')
    def test_abn_and_trade_republic_are_parsed_from_the_actual_offer_context(self):
        abn=rates.parse_abn('<p>Direct Sparen € 0 tot en met € 500.000 1,25% 1,25%</p>')[0];self.assertEqual(abn['rate_pct'],1.25);self.assertEqual(abn['maximum_eur'],500000)
        tr=rates.parse_trade_republic('<p>Activeer 3 % rente op je kassaldo tot €50.000, voor nieuwe klanten.</p>')[0];self.assertTrue(tr['new_customers_only']);self.assertTrue(tr['promotional']);self.assertIsNone(rates.estimate(tr,1000)['interest_eur'])
        metadata=rates.parse_trade_republic('<meta name="description" content="Activeer 3 % rente op je kassaldo tot €50.000, voor nieuwe klanten."><script>not used</script>')[0];self.assertEqual(metadata['rate_pct'],3)
    def test_failed_fetch_keeps_last_verified_rate_and_dates(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(extras,'CACHE',Path(folder)),patch.object(rates,'fetch',side_effect=RuntimeError('source offline')):
            offers=[{'source_key':'raisin','id':'last','rate_pct':2.5,'retrieved_at_epoch':1}];extras.write(Path(folder)/'savings-rates.json',{'offers':offers,'at':1});rates._refresh();result=rates.snapshot(offline=True);self.assertEqual(result['offers'][0]['rate_pct'],2.5);self.assertEqual(result['offers'][0]['retrieved_at_epoch'],1);self.assertTrue(result['offers'][0]['stale']);self.assertEqual(len(result['errors']),3)
class CashEvidence(unittest.TestCase):
    def state(self):return {'savings':[{'name':'Bank','kind':'payment','value':2000,'principal_eur':2000,'rate_pct':0,'snapshot_date':'2026-01-01'},{'name':'Flexible','value':5000,'principal_eur':4900,'rate_pct':2,'snapshot_date':'2026-01-01'},{'name':'Deposit','value':10000,'maturity':'2027-01-01','rate_pct':4}], 'accounts':[{'name':'Broker','cash':1000,'value':20000},{'name':'Bank','cash':2000}], 'managed':{'name':'Managed','cash':500,'value':30000},'debts':[{'name':'Loan','balance':5000,'rate_pct':2}], 'pots':[{'name':'Trip','saved_eur':500,'account':'Flexible'}], 'spend_month':1000,'profile':{'buffer_months':3},'account_history':[],'yearly_flows':[]}
    def test_cash_is_not_portfolio_value_and_fixed_deposits_stay_out(self):
        rows=cash.account_rows(self.state());self.assertEqual(sum(r['balance_eur'] for r in rows),8500);self.assertNotIn('Deposit',[r['name'] for r in rows]);self.assertEqual(len({r['id'] for r in rows}),len(rows))
    def test_zero_unknown_rates_and_unknown_access_are_separate(self):
        summary=cash.summary(self.state());self.assertEqual(summary['idle_eur'],2000);self.assertEqual(summary['unknown_rate_eur'],1500);self.assertEqual(summary['withdrawable_eur'],7000);self.assertEqual(summary['unreserved_eur'],3500);self.assertEqual(summary['planning_reserve_eur'],3500)
    def test_broker_account_history_cannot_be_relabelled_as_cash(self):
        state=self.state();state['account_history']=[{'account':'Broker','date':'2026-01-01','value_eur':20000}];row=next(r for r in cash.account_rows(state) if r['name']=='Broker');self.assertEqual(cash.histories(state,row),[])
    def test_unneeded_identifiers_are_not_copied_into_cash_evidence(self):
        state=self.state();state['savings'][0]['iban']='private-identifier';state['savings'][0]['secret']='private-credential';row=cash.account_rows(state)[0];self.assertNotIn('iban',row);self.assertNotIn('secret',row)
    def test_negative_cash_is_reserved_and_borrowing_rate_is_separate(self):
        state=self.state();state['accounts'][0].update(cash=-500,cash_debit_rate_pct=5);summary=cash.summary(state);self.assertEqual(summary['unreserved_eur'],3000);row=next(r for r in cash.account_rows(state) if r['name']=='Broker');self.assertEqual(row['annual_debit_cost_eur'],25)
    def test_cash_metadata_edits_preserve_balance_and_reject_invalid_terms(self):
        import app
        fields=app.clean('account',{'cash_role':'emergency','cash_rate_pct':2,'cash_eur':200,'secret':'discard'});self.assertEqual(fields['cash_eur'],200);self.assertNotIn('secret',fields)
        for changes in ({'cash_rate_pct':float('nan')},{'withdrawal_days':-1},{'guarantee_limit_eur':-100},{'rate_effective_date':'2099-01-01'}):
            with self.assertRaises(ValueError):app.clean('account',changes)
    def test_ambiguous_payment_names_are_not_linked(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(store,'ROOT',Path(folder)),patch('workspace.store.records',return_value=[]),patch('savings_rates.snapshot',return_value={'offers':[]}),patch('spending.load',return_value={'accounts':{'a':{'name':'Bank'},'b':{'name':'Bank'}},'transactions':[{'id':'x','date':'2026-01-01','account':'a','amount':100}]}):
            row=cash.report(self.state(),offline=True)['accounts'][0];self.assertEqual(row['payment_link_status'],'ambiguous');self.assertIsNone(row['month_in_eur']);self.assertEqual(row['recent_payments'],[])
class EqualBudgetScenarios(unittest.TestCase):
    def run_case(self,**kw):return cash.scenario({'balance_eur':10000,'debt_rate_pct':2,'monthly_payment_eur':100,'lump_eur':1000,'extra_monthly_eur':0,'cash_rate_pct':2,'years':10,**kw})
    def test_equal_rates_make_net_positions_equal_including_freed_repayments(self):
        result=self.run_case(extra_monthly_eur=50);self.assertAlmostEqual(result['repay_advantage_eur'],0,places=2);self.assertIsNotNone(result['repay_payoff_month'])
    def test_higher_debt_rate_favours_repayment_higher_cash_rate_favours_saving(self):
        self.assertGreater(self.run_case(debt_rate_pct=4)['repay_advantage_eur'],0);self.assertLess(self.run_case(cash_rate_pct=4)['repay_advantage_eur'],0)
    def test_payoff_does_not_overpay_and_excess_lump_remains_cash(self):
        result=self.run_case(balance_eur=100,lump_eur=1000,debt_rate_pct=0,cash_rate_pct=0,monthly_payment_eur=10,extra_monthly_eur=20,years=1);end=result['curve'][-1];self.assertEqual(end['keep_net_eur'],1260);self.assertEqual(end['repay_net_eur'],1260);self.assertEqual(result['repay_payoff_month'],0)
    def test_growing_debt_is_not_marked_paid_off_at_the_horizon(self):
        self.assertIsNone(self.run_case(monthly_payment_eur=0,lump_eur=0)['keep_payoff_month'])
    def test_nonfinite_missing_and_negative_inputs_are_rejected(self):
        for values in ({'cash_rate_pct':None},{'lump_eur':-1},{'balance_eur':float('nan')},{'years':1000}):
            with self.assertRaises(ValueError):self.run_case(**values)
if __name__=='__main__':unittest.main()
