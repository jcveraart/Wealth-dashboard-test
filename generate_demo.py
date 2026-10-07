"""Generate invented demo fixtures. No personal files, APIs or credentials are read."""
import argparse
import ast
import calendar
import csv
import hashlib
import json
import math
import random
import re
from datetime import date, datetime, timedelta
from pathlib import Path

SEED = 731904

def dump(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')

def pack_fixtures(root):
    """Keep versioned samples easy to review; runtime data still uses the original single files."""
    root = Path(root)
    spending = json.loads((root / 'spending.json').read_text(encoding='utf-8'))
    groups = {}
    for tx in spending['transactions']:
        groups.setdefault(tx['date'][:7], []).append(tx)
    files = []
    for month, rows in sorted(groups.items()):
        name = 'transactions/' + month + '.json'
        dump(root, name, rows)
        files.append(name)
    spending['transactions'] = []
    spending['_transaction_files'] = files
    dump(root, 'spending.json', spending)
    history_files = {}
    for name in ('history.csv', 'history_accounts.csv'):
        with (root / name).open(encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f); fields = reader.fieldnames; rows = list(reader)
        by_quarter = {}
        for row in rows:
            quarter = (int(row['date'][5:7]) - 1) // 3 + 1
            by_quarter.setdefault(row['date'][:4] + '-Q' + str(quarter), []).append(row)
        pieces = []
        for quarter, part in sorted(by_quarter.items()):
            filename = 'history/' + name[:-4] + '-' + quarter + '.csv'
            dest = root / filename; dest.parent.mkdir(exist_ok=True)
            with dest.open('w', encoding='utf-8', newline='') as f:
                w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(part)
            pieces.append(filename)
        # A short index beside the quarterly CSVs keeps every fixture inspectable.
        (root / name).write_text(','.join(fields) + '\n', encoding='utf-8')
        history_files[name] = pieces
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    manifest.update(transaction_files=files, history_files=history_files)
    dump(root, 'manifest.json', manifest)

def month_at(today, offset):
    index = today.year * 12 + today.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)

def generate(root, today=None):
    today = today or date.today()
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    start = date(today.year - 5, today.month, min(today.day, 28))
    snapshot = today.isoformat()
    daylist = [start + timedelta(days=i) for i in range((today - start).days + 1)]
    endyear = today.year
    def pos(name, ident, cat, units, price, cost, symbol, region='Global', sector='Diversified', maturity=None):
        p = {'name': name, 'isin': ident, 'category': cat, 'units': units, 'cost_eur': cost,
             'net_cashflow_eur': -cost, 'ref_price_eur': price, 'tickers': [symbol],
             'region': region, 'sector': sector, 'currency': 'EUR', 'trades': [
                 {'date': start.isoformat(), 'type': 'Buy', 'units': units, 'amount_eur': -cost}]}
        if maturity:
            p.update(manual_price_eur=price, maturity=maturity)
        return p
    world = pos('World Equity ETF', 'DEMO-WORLD', 'Broad ETF', 140, 96.8, 11300, 'IWDA.AS')
    euro = pos('Europe Equity ETF', 'DEMO-EUROPE', 'Broad ETF', 80, 52.4, 3560, 'IMEU.AS', 'Europe')
    tech = pos('Technology ETF', 'DEMO-TECH', 'Tech ETF', 32, 143.1, 3750, 'QDVE.DE', 'North America', 'Technology')
    asml = pos('ASML', 'DEMO-ASML', 'Stock', 5, 712, 3200, 'ASML.AS', 'Europe', 'Technology')
    apple = pos('Apple', 'DEMO-APPLE', 'Stock', 14, 184, 2100, 'AAPL', 'North America', 'Technology')
    unilever = pos('Unilever', 'DEMO-UNILEVER', 'Stock', 45, 49.6, 2390, 'UNA.AS', 'Europe', 'Consumer staples')
    japan = pos('Japan Equity ETF', 'DEMO-JAPAN', 'Broad ETF', 50, 56.3, 2480, 'SJPA.AS', 'Asia')
    emerg = pos('Emerging Markets ETF', 'DEMO-EM', 'Broad ETF', 110, 31.7, 3210, 'EMIM.AS', 'Emerging markets')
    global2 = pos('World Equity ETF', 'DEMO-WORLD', 'Broad ETF', 35, 96.8, 2780, 'IWDA.AS')
    bond = pos('Example Euro Bond ' + str(endyear + 2), 'DEMO-BOND-1', 'Bond', 4000, 0.985, 3980,
               'DEMO.BOND', 'Europe', 'Government', f'{endyear + 2}-06-30')
    corp = pos('Euro Corporate Bond Fund', 'DEMO-CORP', 'Bond fund', 75, 101.8, 7450, 'IEAC.AS', 'Europe', 'Bonds')
    btc = pos('Bitcoin', 'DEMO-BTC', 'Crypto', .035, 58200, 1580, 'BTC-EUR', 'Global', 'Digital assets')
    eth = pos('Ethereum', 'DEMO-ETH', 'Crypto', .65, 2780, 2030, 'ETH-EUR', 'Global', 'Digital assets')
    mworld = pos('Managed Global Equity Fund', 'DEMO-MWORLD', 'Broad ETF', 125, 112.3, 10740, 'VWRL.AS')
    mbond = pos('Managed Euro Bond Fund', 'DEMO-MBOND', 'Bond fund', 80, 95.4, 7650, 'AGGH.AS', 'Europe', 'Bonds')
    mvalue = mworld['units'] * mworld['ref_price_eur'] + mbond['units'] * mbond['ref_price_eur'] + 350
    accounts = [
        {'name': 'Example Broker One', 'since': start.isoformat()[:7], 'cash_eur': 485, 'profit_extra_eur': 240,
         'closed_cashflow_eur': 0, 'note': 'Invented ETF and stock account.', 'updated': snapshot,
         'positions': [world, euro, tech, asml, unilever]},
        {'name': 'Example Broker Two', 'since': f'{endyear - 3}-01', 'cash_eur': 210, 'profit_extra_eur': 160,
         'closed_cashflow_eur': 0, 'note': 'Invented second broker with bonds and stocks.', 'updated': snapshot,
         'positions': [apple, japan, emerg, global2, bond, corp]},
        {'name': 'Example Crypto Exchange', 'since': f'{endyear - 2}-04', 'cash_eur': 95,
         'profit_extra_eur': 0, 'closed_cashflow_eur': 0, 'updated': snapshot, 'positions': [btc, eth]}]
    savings = [
        {'name': 'Demo Bank Current Account', 'bank': 'Demo Bank', 'kind': 'payment', 'principal_eur': 2750,
         'rate_pct': 0, 'snapshot_date': snapshot, 'accrued_at_snapshot_eur': 0, 'maturity': None, 'invest': False},
        {'name': 'Demo Travel Card', 'bank': 'Demo Travel Bank', 'kind': 'payment', 'principal_eur': 650,
         'rate_pct': 0, 'snapshot_date': snapshot, 'accrued_at_snapshot_eur': 0, 'maturity': None, 'invest': False},
        {'name': 'Emergency Savings', 'bank': 'Example Savings Bank', 'kind': 'savings', 'principal_eur': 12400,
         'rate_pct': 2.2, 'snapshot_date': snapshot, 'accrued_at_snapshot_eur': 132, 'maturity': None, 'invest': False},
        {'name': 'Fixed Deposit', 'bank': 'Example Deposit Bank', 'kind': 'deposit', 'principal_eur': 6500,
         'rate_pct': 3.1, 'snapshot_date': snapshot, 'accrued_at_snapshot_eur': 170,
         'maturity': (today + timedelta(days=240)).isoformat(), 'invest': True}]
    debts = [{'name': 'Example Student Loan', 'balance_eur': 14750, 'rate_pct': 2.35, 'monthly_payment_eur': 125,
              'snapshot_date': snapshot, 'expected_gift': False},
             {'name': 'Example Personal Loan', 'balance_eur': 2400, 'rate_pct': 4.5, 'monthly_payment_eur': 100,
              'snapshot_date': snapshot, 'expected_gift': False}]
    portfolio = {'_demo': True, '_readme': 'Every balance, holding, payment, person and price here is invented.',
        'refresh_minutes': 5, 'accounts': accounts, 'managed': {'name': 'Example Managed Portfolio',
            'value_eur': round(mvalue, 2), 'value_date': snapshot, 'start_value_eur': 19000,
            'start_date': f'{endyear - 4}-01-01', 'profit_at_value_date_eur': round(mvalue - 19000, 2),
            'fees_paid_eur': 290, 'cash_eur': 350, 'positions': [mworld, mbond],
            'proxy': [{'symbol': 'IWDA.AS', 'weight': .65}, {'symbol': 'AGGH.AS', 'weight': .35}]},
        'savings': savings, 'debts': debts,
        'profile': {'birth_year': endyear - 32, 'household': 'single', 'risk': 'balanced', 'home_country': 'NL',
            'benchmark': 'IWDA.AS', 'retire_age': 60, 'horizon_years': 20, 'buffer_months': 6,
            'monthly_invest_eur': 550, 'compare_rate_pct': 2.5, 'goals_text': 'Example home deposit and a comfortable buffer.'},
        'pots': [{'name': 'Holiday', 'target_eur': 2500, 'saved_eur': 1600, 'account': 'Emergency Savings'},
                 {'name': 'Laptop', 'target_eur': 1800, 'saved_eur': 1050, 'account': 'Emergency Savings'}],
        'goals': [{'name': 'Home deposit', 'target_eur': 40000, 'date': (today + timedelta(days=1100)).isoformat(), 'source': 'savings'},
                  {'name': 'Holiday fund', 'target_eur': 2500, 'date': (today + timedelta(days=220)).isoformat(), 'source': 'pot', 'pot': 'Holiday'}],
        'savings_plans': [{'account': 'Example Broker One', 'instrument': 'World Equity ETF', 'isin': 'DEMO-WORLD',
            'amount_eur': 400, 'frequency': 'monthly', 'day': 15, 'active': True, 'since': f'{endyear - 2}-01',
            'last_execution': month_at(today, -1).replace(day=15).isoformat(), 'source': 'synthetic demo'},
            {'account': 'Example Broker Two', 'instrument': 'Emerging Markets ETF', 'isin': 'DEMO-EM',
            'amount_eur': 150, 'frequency': 'monthly', 'day': 15, 'active': True, 'source': 'synthetic demo'}],
        'todos': [{'text': 'Compare savings rates (example task)', 'done': False}, {'text': 'Review annual account fees (example task)', 'done': True}],
        'targets': {'DEMO-WORLD': 40, 'DEMO-EM': 15}, 'tax': {'partner': False},
        'watchlist': [{'name': 'Example watched ETF', 'symbol': 'VWRL.AS', 'buy_below': 100,
            'added': (today - timedelta(days=90)).isoformat(), 'note': 'Invented watchlist entry.'}],
        'advice_dismissed': [], 'advice_done': [], 'account_history': [], 'yearly_flows': []}
    allpos = [p for a in accounts for p in a['positions']] + portfolio['managed']['positions']
    prices, tickers, histories = {}, {}, {}
    for p in allpos:
        symbol = p['tickers'][0]
        if symbol not in histories:
            vol = .0015 if 'Bond' in p['category'] else .009 if p['category'] == 'Crypto' else .0045
            trail = [1.0]
            for i in range(1, len(daylist)):
                trail.append(trail[-1] * math.exp(.00021 + rng.gauss(0, vol) + .0004 * math.sin(i / 70)))
            factor = p['ref_price_eur'] / trail[-1]
            close = [round(v * factor, 4) for v in trail]
            divs = [[d.isoformat(), round(p['ref_price_eur'] * .004, 4)] for d in daylist if d.day == 15 and d.month in (3, 6, 9, 12) and p['category'] not in ('Crypto', 'Bond')]
            histories[symbol] = {'symbol': symbol, 'currency': 'EUR', 'fetched': snapshot, '_demo': True,
                'dates': [d.isoformat() for d in daylist], 'close': close, 'divs': divs}
        h = histories[symbol]
        prices[p['isin']] = {'price': p['ref_price_eur'], 'prev': h['close'][-2], 'symbol': symbol, 'time': snapshot + 'T12:00:00', '_demo': True}
        tickers[p['isin']] = symbol
    for symbol, h in histories.items():
        dump(root, 'cache/history/' + symbol + '.json', h)
    dump(root, 'cache/prices.json', prices)
    dump(root, 'cache/tickers.json', tickers)
    values = {a['name']: sum(p['units'] * p['ref_price_eur'] for p in a['positions']) + a['cash_eur'] for a in accounts}
    values[portfolio['managed']['name']] = mvalue
    values.update({s['name']: s['principal_eur'] + s['accrued_at_snapshot_eur'] for s in savings})
    values.update({d['name']: -d['balance_eur'] for d in debts})
    account_rows, history_rows = [], []
    kinds = {'Broad ETF': 'etf', 'Tech ETF': 'etf', 'Stock': 'stocks', 'Bond': 'bonds', 'Bond fund': 'bonds', 'Crypto': 'other_inv'}
    for i, day in enumerate(daylist):
        factor = .50 + .50 * i / max(1, len(daylist) - 1) + .025 * math.sin(i / 85)
        lastfactor = 1 + .025 * math.sin((len(daylist) - 1) / 85)
        factor /= lastfactor
        vals = {name: round(v * factor, 2) for name, v in values.items()}
        for d in debts:
            vals[d['name']] = round(-d['balance_eur'] - (len(daylist) - i - 1) * 3.9, 2)
        account_rows += [{'date': day.isoformat(), 'account': name, 'value': val} for name, val in vals.items()]
        cat = {'etf': 0, 'stocks': 0, 'bonds': 0, 'other_inv': 0}
        for a in accounts:
            for p in a['positions']:
                h = histories[p['tickers'][0]]
                cat[kinds[p['category']]] += p['units'] * h['close'][i] * (.60 + .40 * i / (len(daylist) - 1))
        managed = vals[portfolio['managed']['name']]
        saved = sum(vals[s['name']] for s in savings)
        own = sum(cat.values()) + sum(a['cash_eur'] for a in accounts)
        debt = -sum(vals[d['name']] for d in debts)
        gross = managed + saved + own
        history_rows.append({'date': day.isoformat(), 'net_worth': round(gross - debt, 2), 'gross': round(gross, 2),
            'debt': debt, 'managed': managed, 'savings': saved, 'self_directed': round(own, 2), **{k: round(v, 2) for k, v in cat.items()},
            'cash': round(saved + sum(a['cash_eur'] for a in accounts), 2), 'invest_profit': round((own + managed) * .12 * i / len(daylist), 2)})
        if day.month == 12 and day.day == 31 or day == today:
            portfolio['account_history'] += [{'date': day.isoformat(), 'account': n, 'value_eur': v, 'source': 'synthetic demo'} for n, v in vals.items()]
    for year in range(endyear - 4, endyear + 1):
        for name in [a['name'] for a in accounts] + [portfolio['managed']['name']]:
            portfolio['yearly_flows'].append({'year': year, 'account': name, 'deposits_eur': 5000,
                'withdrawals_eur': 500, 'invested_eur': 4500, 'dividends_eur': 110 + rng.randrange(130),
                'interest_received_eur': 35, 'interest_paid_eur': 0, 'fees_eur': 45, 'taxes_eur': 0,
                'profit_eur': round(values[name] * rng.uniform(-.06, .12), 2), 'return_pct': round(rng.uniform(-5, 12), 1),
                'note': 'Invented yearly statement; not an actual account.'})
    for name, rows in [('history.csv', history_rows), ('history_accounts.csv', account_rows)]:
        with (root / name).open('w', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    dump(root, 'portfolio.json', portfolio)
    # Read only the public category definitions, without importing or opening app data.
    category_file = Path(__file__).absolute().parent / 'spending.py'
    module = ast.parse(category_file.read_text(encoding='utf-8'))
    categories = next(ast.literal_eval(n.value) for n in module.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'DEFAULT_CATEGORIES' for t in n.targets))
    spending_data = {'categories': [{'id': i, 'name': n, 'group': g, 'kind': k} for i, n, g, k in categories],
        'rules': [], 'transactions': [], 'imports': [], 'own_accounts': [], 'accounts': {}, 'budgets': {}, 'subscriptions': {}}
    spending_data.update(_demo=True, home_country='NL', accounts={
        'demo-checking': {'name': 'Demo Bank Current Account', 'role': 'payment'},
        'demo-travel': {'name': 'Demo Travel Card', 'role': 'payment'}}, own_accounts=['demo-checking', 'demo-travel'])
    transactions = []
    def tx(day, amount, merchant, category, account='demo-checking', country='NL', tags=None, **extra):
        if day > today:
            return
        description = f'DEMO ONLY: {merchant}; synthetic payment'
        identity = hashlib.sha256(f'{day}|{amount}|{merchant}|{account}|{len(transactions)}'.encode()).hexdigest()[:20]
        transactions.append({'id': 'demo-' + identity, 'date': day.isoformat(), 'amount': round(amount, 2),
            'description': description, 'merchant': merchant, 'key': re.sub(r'[^a-z&]', '', merchant.lower())[:30], 'counter_iban': '',
            'account': account, 'category': category, 'category_source': 'user', 'note': '', 'import': 'demo-generated',
            'country': country, 'country_source': 'user', 'tags': tags or [], **extra})
    for offset in range(-24, 1):
        month = month_at(today, offset)
        def md(n): return month.replace(day=min(n, calendar.monthrange(month.year, month.month)[1]))
        tx(md(25), 3425 + max(0, offset + 12) * 8, 'Example Employer', 'salary')
        tx(md(1), -1050, 'Example Rent', 'rent')
        tx(md(3), -110, 'Example Energy', 'utilities')
        tx(md(5), -52, 'Example Internet', 'internet-phone')
        tx(md(8), -139, 'Example Health Insurer', 'insurance')
        tx(md(9), -(10.99 if offset < -6 else 12.99), 'Example Music Subscription', 'subscriptions')
        tx(md(11), -14.99, 'Example Video Subscription', 'subscriptions')
        tx(md(12), -34.95, 'Example Fitness Club', 'sports')
        tx(md(15), -550, 'Example Investing Transfer', 'saving-investing')
        tx(md(18), -125, 'Example Loan Payment', 'loan-repayment')
        tx(md(19), 28.50, 'Tikkie from Demo Friend', 'from-people')
        tx(md(20), -22, 'Tikkie to Demo Friend', 'people')
        for week in range(4):
            tx(md(2 + 7 * week), -rng.uniform(38, 82), 'Harbour Grocer', 'groceries')
            tx(md(4 + 7 * week), -rng.uniform(12, 55), 'Copper Cafe', 'restaurants')
            tx(md(6 + 7 * week), -rng.uniform(5, 17), 'Example Rail', 'public-transport')
        tx(md(16), -rng.uniform(25, 105), 'Example Clothes Shop', 'clothing')
        tx(md(21), -rng.uniform(10, 65), 'Demo Online Shop', 'online-shopping')
        tx(md(23), -rng.uniform(18, 48), 'Example Cinema', 'going-out')
        if month.month in (5, 8):
            for k in range(9):
                country = 'ES' if month.month == 8 else 'PT'
                tx(md(6 + k), -rng.uniform(18, 120), 'Example Holiday Restaurant', 'restaurants',
                   account='demo-travel', country=country, tags=['holiday-' + country.lower()])
            tx(md(5), -420, 'Example Holiday Hotel', 'travel', account='demo-travel', country=country, tags=['holiday-' + country.lower()])
        if month.month in (3, 10):
            tx(md(6), -79, 'Example Berlin Hotel', 'travel', account='demo-travel', country='DE', tags=['weekend'])
            tx(md(7), -43, 'Example Berlin Cafe', 'restaurants', account='demo-travel', country='DE', tags=['weekend'])
    # Examples to exercise review, splits, reimbursements and excluded transfers.
    tx(today - timedelta(days=3), -85, 'Example Department Store', 'home', tags=['home'],
       splits=[{'category': 'home', 'amount': -60}, {'category': 'gifts', 'amount': -25}])
    tx(today - timedelta(days=2), -17.50, 'Unknown Demo Merchant', None, category_source=None)
    tx(today - timedelta(days=1), -250, 'Example Internal Transfer', 'own-transfers', excluded=True)
    tx(today - timedelta(days=1), 34, 'Example Return', 'refunds')
    spending_data['transactions'] = sorted(transactions, key=lambda t: (t['date'], t['id']), reverse=True)
    spending_data['imports'] = [{'id': 'demo-generated', 'file': 'Synthetic demo dataset', 'date': snapshot,
        'added': len(transactions), 'from': transactions[0]['date'], 'to': snapshot}]
    spending_data['rules'] = [{'match': 'harbour grocer', 'type': 'merchant', 'category': 'groceries', 'label': 'Example grocery rule'}]
    dump(root, 'spending.json', spending_data)
    dump(root, 'ui.json', {'views': [], 'pins': [{'id': 'demo-summary', 'title': 'About this demo',
        'content': 'Every number and transaction in this dashboard is invented. Try filtering investments or exploring spending by country.',
        'created': snapshot + 'T09:00:00'}], 'celebrated': [], 'prefs': {'local_ai': 'off', 'celebrations': False, 'effort': 'auto'}})
    dump(root, 'settings.json', {})
    dump(root, 'inbox.json', [])
    dump(root, 'imports.json', [{'id': 'demo-seed', 'date': snapshot + 'T09:00:00', 'files': ['Synthetic demo dataset'],
        'summary': 'Invented portfolio, payments and history, generated from a fixed seed.', 'kind': 'spending'}])
    dump(root, 'chats.json', [{'id': 'demo-chat', 'title': 'Exploring the demo', 'topic': 'General',
        'created': snapshot + 'T09:00:00', 'updated': snapshot + 'T09:01:00', 'messages': [
            {'role': 'user', 'content': 'What can I explore here?'},
            {'role': 'assistant', 'content': 'This is a prerecorded demo conversation. Explore asset classes, spending, trips, saving goals and history. Live AI needs your own setup.'}]}])
    (root / 'notes.md').write_text('# Synthetic demo owner\n\nEvery account, balance and transaction is invented. No real person is represented.\n\nThis example uses a balanced portfolio, a savings buffer and a goal to save for a home.\n', encoding='utf-8')
    dump(root, 'cache/economy.json', {'fetched': snapshot + 'T12:00:00', '_demo': True,
        'ecb_rate': {'rows': [[snapshot, 2.0]]}, 'usd': {'rows': [[snapshot, 1.1]]},
        'savings_nl': {'rows': [[today.isoformat()[:7], 1.8]], 'key': 'demo'},
        'inflation_nl': {'rows': [[month_at(today, k).isoformat()[:7], round(2.2 + .4 * math.sin(k / 7), 2)] for k in range(-72, 1)]},
        'inflation_ea': {'rows': [[today.isoformat()[:7], 2.1]]}, 'bond2': {'rows': [[snapshot, 2.7]]}, 'bond10': {'rows': [[snapshot, 3.0]]}})
    dump(root, 'cache/news.json', {})
    dump(root, 'cache/ideas.json', {'date': snapshot, 'time': snapshot + 'T09:00:00', 'ideas': [], '_demo': True})
    dump(root, 'manifest.json', {'synthetic': True, 'seed': SEED, 'anchor_date': snapshot,
        'transactions': len(transactions), 'holdings': len(allpos), 'history_days': len(daylist),
        'source': 'Generated entirely from fictional parameters; no live dashboard data was read.'})
    if root.name == 'demo_data':
        pack_fixtures(root)
    return {'portfolio': portfolio, 'spending': spending_data, 'history': history_rows}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='demo_data')
    parser.add_argument('--date', help='Anchor date YYYY-MM-DD; default today')
    args = parser.parse_args()
    generate(args.output, date.fromisoformat(args.date) if args.date else None)
    print('Synthetic fixtures generated. No personal files or services accessed.')
