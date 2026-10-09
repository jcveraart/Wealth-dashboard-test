"""Normalize supported annual statements without mixing currencies or reporting durations."""
from datetime import date
from .analytics import number

SEC_FIELDS={
 'income':{'Total Revenue':['RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet','Revenue'],
           'Net Income':['NetIncomeLoss','ProfitLoss'],'Operating Income':['OperatingIncomeLoss','ProfitLossFromOperatingActivities'],
           'Pretax Income':['IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest','ProfitLossBeforeTax'],
           'Tax Provision':['IncomeTaxExpenseBenefit','IncomeTaxExpenseContinuingOperations']},
 'cashflow':{'Operating Cash Flow':['NetCashProvidedByUsedInOperatingActivities','CashFlowsFromUsedInOperatingActivities'],
             'Capital Expenditure':['PaymentsToAcquirePropertyPlantAndEquipment','PurchaseOfPropertyPlantAndEquipment']},
 'balance':{'Stockholders Equity':['StockholdersEquity','EquityAttributableToOwnersOfParent'],
            'Cash And Cash Equivalents':['CashAndCashEquivalentsAtCarryingValue','CashAndCashEquivalents']}}

def sec_statements(facts,currency):
    result={k:[] for k in SEC_FIELDS}
    if not currency:return result
    namespaces=facts.get('facts',{})
    for kind,fields in SEC_FIELDS.items():
        periods={}
        for label,concepts in fields.items():
            candidates=[]
            for namespace in ('us-gaap','ifrs-full'):
                for concept in concepts:
                    items=namespaces.get(namespace,{}).get(concept,{}).get('units',{}).get(currency,[])
                    for r in items:
                        if r.get('form') not in ('10-K','10-K/A','20-F','20-F/A','40-F','40-F/A'):continue
                        try:
                            ending=date.fromisoformat(r['end'])
                            if kind!='balance' and not 300<=(ending-date.fromisoformat(r['start'])).days<=400:continue
                        except (KeyError,ValueError):continue
                        if number(r.get('val')) is not None:candidates.append(r)
                    if candidates:break
                if candidates:break
            # Later annual filings may restate an earlier annual period.
            seen=set()
            for r in sorted(candidates,key=lambda r:r.get('filed',''),reverse=True):
                if r['end'] in seen:continue
                seen.add(r['end']);row=periods.setdefault(r['end'],{'period':r['end'],'currency':currency,'items':{},'source':'SEC EDGAR','evidence':{}})
                value=number(r['val']);row['items'][label]=-abs(value) if label=='Capital Expenditure' else value
                row['evidence'][label]={'accession':r.get('accn'),'filed':r.get('filed'),'start':r.get('start'),'end':r['end']}
        result[kind]=[periods[p] for p in sorted(periods,reverse=True)][:5]
    # Balance sheets include comparative interim instants in annual filings. Align only
    # to actual annual income periods before they enter ratio calculations.
    annual={r['period'] for r in result['income']}
    result['balance']=[r for r in result['balance'] if r['period'] in annual]
    return result

OPENBB_FIELDS={
 'income':{'Total Revenue':['total_revenue','revenue'],'Net Income':['net_income','net_income_common_stockholders'],
           'Operating Income':['operating_income'],'EBIT':['ebit'],'Pretax Income':['pretax_income'], 'Tax Provision':['tax_provision']},
 'cashflow':{'Operating Cash Flow':['operating_cash_flow'],'Capital Expenditure':['capital_expenditure','purchase_of_ppe']},
 'balance':{'Stockholders Equity':['stockholders_equity','total_equity_gross_minority_interest'],'Total Debt':['total_debt'],
            'Cash And Cash Equivalents':['cash_and_cash_equivalents']}}

def openbb_statements(data,currency):
    out={}
    for kind,fields in OPENBB_FIELDS.items():
        rows=[]
        for r in data.get('datasets',{}).get(kind,[]):
            period=str(r.get('period_ending') or r.get('date') or '')[:10]
            try:date.fromisoformat(period)
            except ValueError:continue
            if r.get('currency') and r['currency']!=currency:continue
            items={}
            for label,names in fields.items():
                value=next((number(r[k]) for k in names if number(r.get(k)) is not None),None)
                if value is not None:items[label]=-abs(value) if label=='Capital Expenditure' else value
            if items:rows.append({'period':period,'currency':currency,'items':items,'source':'OpenBB'})
        out[kind]=sorted(rows,key=lambda r:r['period'],reverse=True)
    return out
