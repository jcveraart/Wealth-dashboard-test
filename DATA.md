# How portfolio.json is structured

The dashboard is built entirely from `portfolio.json`. Anything you add here (new accounts, new kinds of assets like crypto, history) shows up on the website automatically. All amounts are in euros.

## accounts (self directed investment accounts: brokers, crypto exchanges)
```json
{"name": "DEGIRO", "since": "2020-02", "cash_eur": -570.43, "closed_cashflow_eur": 547.88, "profit_extra_eur": 167.02,
 "note": "...", "positions": [ ...position... ]}
```
- `cash_eur`: cash balance in the account (negative means borrowing).
- `closed_cashflow_eur`: total profit (or loss) of positions that were fully sold. When you remove a position because it was sold, add its realised result here: sale proceeds plus its `net_cashflow_eur` (net_cashflow is negative for money put in).
- `profit_extra_eur`: income not tied to an open position (dividends of sold stocks, minus debit interest).
- A new broker or exchange (for example OKX) is simply a new entry in `accounts`.

## position (inside accounts[].positions or managed.positions)
```json
{"name": "Intel", "isin": "US4581401001", "category": "Stock", "units": 25, "cost_eur": 591.88,
 "net_cashflow_eur": -591.88, "ref_price_eur": 106.02, "tickers": ["INTC"]}
```
- `category`: Stock, Broad ETF, Tech ETF, Bond, Bond fund, Crypto, Commodity, Other (a new category is allowed and gets its own group on the site).
- `isin`: only when known. Crypto has no ISIN: leave the key out.
- `units`: amount held. `cost_eur`: what the units still held cost. `net_cashflow_eur`: all money in (negative) and out (positive) for this position over time, including earlier sales and dividends. Profit = value + net_cashflow.
- `ref_price_eur`: last known price per unit in euros (required). Live prices replace it; it is also used to check that a ticker is right (within 35%).
- `tickers`: Yahoo Finance symbols to try, best first. Crypto: "BTC-EUR", "ETH-EUR", "SOL-EUR".
- `manual_price_eur`: set only for individual bonds (fixed price, no live lookup). `maturity`: "YYYY-MM" or "YYYY-MM-DD" for bonds.

## managed (the ABN AMRO managed portfolio, one object)
- `value_eur` and `value_date`: last real value from the bank. `profit_at_value_date_eur`: total result on that date. `fees_paid_eur`, `start_value_eur`, `start_date`.
- Optional `positions` (same shape as above) and `cash_eur`: when present, the portfolio is priced live per holding. When you change the positions, set `value_eur` to their total and `value_date` to the date, and adjust `profit_at_value_date_eur` by the same change in value (unless money was added or withdrawn).
- `proxy`: index mix used to estimate the value when there are no positions.

## savings (savings, deposits, current accounts)
```json
{"name": "Coop Pank", "bank": "Coop Pank", "principal_eur": 11037.35, "rate_pct": 2.92, "accrued_at_snapshot_eur": 1.77,
 "snapshot_date": "2026-10-04", "maturity": "2027-07-02"}
```
- Update `principal_eur` and `snapshot_date` (today) when a balance changes; reset `accrued_at_snapshot_eur` to 0 unless known.
- `invest` (optional, true or false): whether the owner counts this account as an investment (it then shows on the Investments page). Without it, a deposit with a maturity counts, an account without interest does not, and others are asked on the Advice page. Set it when the owner tells you.

## debts
```json
{"name": "DUO student loan", "balance_eur": 34454.97, "rate_pct": 2.56, "snapshot_date": "2026-10-01", "expected_gift": false}
```
- `expected_gift: true` means shown but not counted in net worth.
- `monthly_payment_eur` (optional): what is repaid each month. With it the balance goes down month by month and the Savings & debt page shows when it is paid off.

## savings_plans (automatic recurring buys, for example at Trade Republic)
```json
{"account": "Trade Republic", "instrument": "iShares Core MSCI World", "isin": "IE00B4L5Y983", "amount_eur": 50.0,
 "frequency": "monthly", "day": 2, "active": true, "since": "2024-01", "last_execution": "2026-10-02", "source": "manual"}
```
- `frequency`: weekly, biweekly, monthly or quarterly. `day`: day of the month (monthly and quarterly only).
- Plans with `"source": "detected"` are recreated from each Trade Republic export. When you change a plan because the owner asked, set `"source": "manual"` so the next import keeps his version. Stopping a plan: set `active` to false.

## account_history (values at points in time, for the History page)
```json
{"date": "2023-12-31", "account": "DEGIRO", "value_eur": 4696, "source": "annual statement 2023"}
```
- One row per account per date. Year end values (31 December) matter most. `account` uses the same name as in accounts, savings, debts or the managed portfolio name. Debts as positive numbers with the debt's name.

## yearly_flows (money in and out per account per year)
```json
{"year": 2023, "account": "DEGIRO", "deposits_eur": null, "withdrawals_eur": null, "invested_eur": null,
 "dividends_eur": 69.9, "interest_received_eur": null, "interest_paid_eur": 85.55, "fees_eur": null, "taxes_eur": null,
 "profit_eur": 601, "return_pct": 13, "note": "annual statement"}
```
- One row per account per year. Use null for unknown fields. `invested_eur` is net buys. `profit_eur` and `return_pct` are the result for that year.

## todos
`[{"text": "...", "done": false}]` (the to do list on the Advice page). Add, edit, tick off or remove items when the owner asks.

## Recommendations (Advice page)
Most recommendations are generated from the numbers; the current ones and their ids are listed in the live snapshot.
- `advice_dismissed`: `[{"id": "small-positions", "title": "...", "reason": "the owner wants to keep them"}]`. Add an entry to hide a recommendation (use the exact id from the snapshot). Remove the entry to bring it back.
- `advice_custom`: `[{"id": "custom-rebalance", "title": "...", "detail": "...", "todo": "optional to do text or null"}]`. Recommendations added in the chat. Give each a unique id starting with "custom-". Remove an entry to delete it.

## spending_rules.json (the Spending section)
The transactions themselves live elsewhere; this file controls how they are categorised.
```json
{"categories": [{"id": "groceries", "name": "Groceries", "group": "Food and drink", "kind": "expense"}],
 "rules": [{"match": "albertheijn", "type": "merchant", "category": "groceries", "label": "Albert Heijn"},
           {"match": "tikkie", "type": "contains", "category": "gifts"}],
 "accounts": {"NL12ABNA0123456789": {"name": "ABN AMRO current account"}}}
```
- `kind`: expense, income or transfer. Transfers (between own accounts, saving and investing, loan repayments) are left out of spending and income.
- `group`: the larger group a category belongs to (Housing, Food and drink, Transport ...). A new group name is fine.
- Rules: `type` "merchant" matches the merchant key exactly (lower case letters only, as in the snapshot), `type` "contains" matches any text in the merchant or description. Rules beat built-in keywords and the AI, but never a category the owner picked by hand.
- To move all of a merchant's transactions to a category, add or change a rule. To rename a category, change its `name` (keep the `id`). Never remove a category that rules still use.
- `accounts`: display names for payment accounts (current account, credit card, Trade Republic ...).

## spending_new.json (adding spending transactions from documents)
Starts as `[]`. Write the payments you find in uploaded documents here:
```json
[{"date": "2026-09-14", "amount": -23.50, "description": "Albert Heijn 1427 Westmaas", "counterparty": "Albert Heijn", "account": "ABN AMRO current account"}]
```
- Money out is negative, money in positive. `account` is the payment account name (use an existing one from the spending summary when it's the same account).
- Leave out balances, totals, and transfers that are just between the owner's own accounts if they are already in the data.
- PayPal: his bank shows one line per payment to "PayPal Europe" with no shop behind it. When a document lists what he actually bought through PayPal, use `"account": "PayPal"` for those purchases and leave out rows that only move money from his bank into PayPal (topping up, withdrawals, currency conversions), because the bank line already covers that. The app then books the bank's PayPal debits as a transfer for every month the PayPal data covers.

## Planning and profile
- `profile`: `{"birth_year": 1996, "retire_age": 60, "horizon_years": 15, "buffer_months": 4, "monthly_invest_eur": 300, "household": "Single", "risk": "low|medium|high", "home_country": "NL", "benchmark": "IWDA.AS", "compare_rate_pct": 2.9, "goals_text": "..."}`. Facts about the owner used by the Plan page, the advice and the chat. Update when the owner tells you something new about himself.
- `goals`: `[{"name": "House deposit", "target_eur": 40000, "date": "2029-06-01", "source": "savings"}]`. `source` says what counts toward it: `net_worth`, `savings`, `investments`, `pot` (with `"pot": "<pot name>"`) or `manual` (with `"saved_eur"`).
- `pots`: `[{"name": "Holiday", "saved_eur": 1800, "target_eur": 3000, "account": "Savings account"}]`. Money set aside inside savings.
- `targets`: `{"<position id>": 20}`. Target share in percent of the self directed investments; the position id is the ISIN, or "n:" plus the lower case name when there is no ISIN.
- `tax`: `{"partner": false, "params": {"2026": {"bank": 1.28, "other": 6.0, "debt": 2.7, "allowance": 51396, "threshold": 3800, "rate": 36}}, "checklist": {...}}`. Box 3 settings; only change `params` when the owner gives official numbers.
- `watchlist`: `[{"name": "ASML", "symbol": "ASML.AS", "added": "2026-10-06", "buy_below": 600, "note": "..."}]`. Investments the owner follows before buying; `symbol` is the Yahoo Finance ticker.
- `advice_done`: `[{"id": "...", "title": "...", "impact_eur": 140, "date": "2026-10-05"}]`. Recommendations the owner has acted on.
- Positions can carry `region`, `sector` and `currency` (main currency exposure) for grouping, and Trade Republic positions carry `trades` (buys, sells and dividends from the export). Accounts can carry `updated` and `source` (when and from what the holdings were last updated); set them when you import holdings.

## Other settings
- `refresh_minutes`: how often prices refresh (default 5).

## Rules for changes
- Never record anything twice. Before adding, check what is already there: a statement or screenshot describes a situation, so update the existing holding, balance or history row instead of adding a new one. A transaction list that overlaps with earlier imports must not add units, deposits or payments that are already counted. If a document is entirely already in the data, change nothing and say so.
- Keep valid JSON. Keep every existing field you don't need to change.
- Never invent numbers. If something is unknown, leave it out or null, and say so.
- Moving money between accounts: lower one balance and raise the other by the same amount.
- Selling a position completely: remove it, add its realised result to that account's `closed_cashflow_eur`, and add the proceeds to cash (or to the account the money moved to).
- An account that is completely emptied and closed can be removed after its result is kept in yearly_flows or account_history.
