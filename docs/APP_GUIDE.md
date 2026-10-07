# Wealth dashboard

A website that runs on your own computer and shows everything you own and owe: DEGIRO, Trade Republic, ABN AMRO (ETFs and the managed portfolio), savings and DUO. Prices update every 5 minutes. Open it at http://wealth.localhost.

Your data stays on your computer. Prices come from Yahoo Finance (about 15 minutes delayed). The only thing that leaves your computer is a screenshot you choose to import, which is sent to Claude to be read. Keep `portfolio.json` and `settings.json` private.

## Working on this code elsewhere (for example a cloud session)

The repository holds only the code. All personal data and keys stay on the owner's computer and are listed in `.gitignore`: `portfolio.json`, `spending.json`, `notes.md`, `history.csv`, `history_accounts.csv`, `inbox.json`, `imports.json`, `ui.json`, `chats.json`, `settings.json`, `backups/` and `cache/`. Never add them.

To run the app without that data:

```
cp portfolio.example.json portfolio.json      # made up data
pip install -r requirements.txt
python app.py --offline --no-browser          # no price fetching, no AI needed
```

`--offline` skips Yahoo Finance, so it works without internet. The AI features (Import, Ask Claude, spending categorisation, note matching) need either Claude Code installed or an Anthropic API key in `settings.json`, so they stay switched off in a sandbox. The pages that do not need them (Overview, Holdings, Accounts, Savings & debt, History, Plan, Taxes, Advice) all render from `portfolio.json` alone.

Tests: `python -m unittest discover tests` (debt payoff, split payments, tags, Tikkies, account kinds, countries, advice).

Spending starts empty; `spending.json` is created on the first import.

## Start

- **Windows:** double click `start-windows.bat` (installs what it needs, then opens the site).
- **Terminal:** `pip install -r requirements.txt`, then `python app.py`.

## Pages

| Page | What it does |
|---|---|
| Overview | Net worth with Claude's short briefing next to it, four tiles (assets, debt, investing profit, savings) with sparklines and the change since last month, an ask box, every account in three columns (day to day money, including the cash at a broker; savings; investing) with a sparkline and today's result, the net worth chart (over time with markers for big events, by type, or per month as a waterfall; in euros or percent; drag across it to read a range), allocation, biggest moves, what is coming up, this month so far, and answers you pinned from the chat. Click an account for its own page with its history |
| Investments | Everything that is not day to day money: brokers, the managed portfolio, bonds, and the savings accounts and deposits you count as investments (you choose, or tell Claude). Look at all of it or one asset class (shares and funds, bonds, savings and deposits, crypto), for all accounts or one. At the top the value, today and returns over a week, a month, three months, this year and longer (click one to set the period). Then today per account (click for the investments behind it) and what moved, with a headline only when something moved two percent or more; value over time, against a benchmark, and drawdown; how it is spread; results per year, a bond ladder or the rates your savings earn, depending on what you look at; everything you hold, grouped, with a three month trend; and one Deeper card for monthly returns, dividends, what is coming up, costs, money put in and savings plans. Cards with nothing to say for your selection stay away |
| Savings & debt | Cash you can reach and money you owe: every savings account with a switch for cash or investment, your buffer in months of spending, pots, debts and a payoff plan with an extra payment slider |
| Spending & income | Tabs for Overview, Spending (money flow, categories with sparklines, this month against your average, calendar, merchants, when you spend), Income, Transactions, Subscriptions (with price changes), Trips, Countries (map), Quick check (go through payments one by one, monthly review), To review and Categories. Pick one or more payment accounts. Hover a legend entry or a category to light it up in every chart, click a legend entry to show only that group. Bars per day, week, month or year from the date menu. Filter transactions on several categories, countries or tags at once. Split a payment, tag it with #hashtags, leave it out of the totals, or leave a merchant out for good (a payment service that only moves money, for example), or talk with Claude about it. Money friends send back (Tikkie) counts as income, never as spending. Long lists scroll inside their card |
| History | How your wealth developed: net worth over time (or by part), change per year split into investment result and the rest, every account at year end, a plain year by year table with a year in review, and every trade with filters |
| Plan | Goals with progress, a projection with sliders and a fan chart of likely outcomes, the year you could stop working, and big decisions (repay the loan or invest, buy a home) |
| Taxes | Box 3 estimate for this year and next, what moving money before 1 January would change, a checklist for the tax return and the tax calendar. Rates can be edited |
| Advice | Opportunities, found automatically: what stands out in your own numbers (investments well below their high, holdings behind your target, watchlist prices reached, a fresh ECB rate cut) and four ideas from Claude every week that fit your portfolio and risk profile, each with Talk about it and Watch. A watchlist for investments you follow before buying. Recommendations, each with its own conversation, Questions for you, your to do list and what you have done |
| Import | Upload anything; a timeline shows which months each source covers and what is missing (with how to export it), and a log of imports with undo |
| Settings | About you (used by Plan, Advice and Claude), briefing and celebration settings, how much AI was used, export everything as JSON or CSV, API key, prices, light or dark mode |

Everywhere: the Claude panel (top right, or press `/`), with a choice of how hard Claude thinks (Auto, Quick, Normal, Deep) and Think harder under every answer, with suggested questions per page, clickable charts and buttons in its answers, and earlier conversations grouped by topic with search. Every card has *Ask about this*, focus and full screen, and download as PNG or CSV, and can be dragged by its grip to another place; each page remembers its layout. One date range at the top drives every chart, with a compare mode. `⌘K` searches everything, right click (or long press) opens a menu on payments, holdings and accounts, files can be dropped anywhere, and views can be saved. Press `?` for all keyboard shortcuts and `b` to hide amounts.

## The AI keeps your data up to date

Import and the Claude panel both run Claude Code (installed with the VS Code extension) on your normal Claude plan. Claude Code works on copies of `portfolio.json` and `notes.md`, following the rules in `DATA.md`. Its changes are checked (the dashboard must still load) before they are saved, and every change has an **Undo** button.

- **Import:** drop screenshots, transaction lists, yearly statements, CSV, Excel or PDF from any bank, broker or crypto exchange. Holdings and balances are updated, new accounts are added, and history goes into `account_history` and `yearly_flows` (the History page). A Trade Republic `Transaction_export.csv` on its own is calculated exactly, without AI.
- **Claude panel:** say what changed ("I sold everything at Trade Republic and moved it to ABN AMRO") and the data is updated. Questions are just answered.
- **New kinds of assets** (crypto, gold ...) need no code: a new category gets its own group, and Yahoo tickers like `BTC-EUR` are priced live.
- With only an API key (no Claude Code), imports still work but the chat cannot change data.

Before every change, `portfolio.json` and `notes.md` are copied to the `backups` folder (the last 100 are kept). Undo restores such a copy.

## Saving on AI use

The Claude panel only hands Claude the data files and tools when you ask it to change something, attach a file, or choose Deep. Everything else is answered from a compact summary in one go. Auto uses a quick model for simple lookups and a normal one for the rest; background jobs (countries, the briefing, grouping investments) use the quick model. Deep uses the most capable model and may search the web. Parsing bank exports, categorising with rules and keywords, subscriptions and all the charts run on your computer without AI.

## Public data and a model on your computer

- **ECB** (free, official, no key): the ECB deposit rate, inflation in the Netherlands and the euro area, what Dutch banks pay on savings on average, and the dollar rate. Used on Savings & debt (one line, and a marker on accounts that earn less than inflation), on History (growth after inflation), in the briefing when the ECB changes its rate, and by Claude.
- **SEC** (free, official, no key): figures from the annual reports of stocks listed in the US (revenue and growth, profit margin, price to earnings and to book). Shown in an investment's detail panel and given to Claude for its views. Add your email under Settings, Public data: the SEC asks callers for one.
- **Signals for the Advice page**, from the same official sources: what safe euro government bonds pay (ECB yield curve) against your savings, and insiders of US listed companies you hold or watch buying their own shares on the open market (SEC Form 4 filings).
- **Research, folded away** under the Opportunities card: your stocks against the typical P/E of their industry (Aswath Damodaran's free data, NYU Stern, refreshed monthly; the industry of each stock is picked once by the local model or Claude), and what a few well known investors (Berkshire Hathaway, Pershing Square, Scion) bought and sold last quarter (SEC 13F filings, refreshed weekly). A signal appears only when one of them buys something you hold or watch; the industry P/E also shows in an investment's detail panel.
- **Ollama** (free, open source): when it runs on your computer, the small jobs (countries, the briefing, grouping investments, news picks, categorising) use it instead of Claude. Install it from ollama.com and run `ollama pull qwen2.5:7b` once; Settings shows what it found.

Everything is cached (a day, company figures a week) and the app works the same without it.

## Spending

Bank exports (ABN AMRO TXT or CSV, ICS credit card, ING, Rabobank, bunq, Revolut, Excel, or the Trade Republic export) are read by code in `spending.py`, so thousands of transactions import in a second and nothing is imported twice. Layouts it doesn't know, and PDF statements, are read by the AI. Data lives in `spending.json`.

**PayPal.** Your bank only shows "PayPal Europe" with no shop behind it. Import PayPal's own transaction export (CSV, Dutch or English) and those purchases appear with the real merchant on a separate PayPal account. For every month the export covers, the PayPal debits on your bank account switch to "Between own accounts", so the same money is never counted twice. Rows that only move money (topping up, withdrawals, currency conversions) are skipped. Months the export does not cover keep the bank line as spending.

Categories are chosen in this order: your own choice, then rules (made when you change a merchant's category, or by Claude), then built-in keywords for Dutch shops and banks, then the AI in the background. What the AI can't place appears under **To review**, grouped per merchant. Transfers between your own accounts, saving and investing, and loan repayments are not counted as spending, so paying off the credit card is not counted twice.

## Cloud database (Supabase)

Optional copy of everything in your own Supabase project: tables `accounts`, `positions`, `savings`, `debts`, `net_worth_history`, `position_history` (one row per holding per day) and `portfolio_backup` (the full portfolio.json).

1. Create a free project at supabase.com.
2. In the SQL Editor, run `supabase-schema.sql`, `supabase-history.sql` and `supabase-spending.sql` from this folder.
3. In Settings on the dashboard, paste the Project URL and the secret key, and press Connect.

It syncs every 15 minutes and after every change. The secret key stays in `settings.json` on this computer; row level security blocks every other key.

## Other updates

| What changed | What to do |
|---|---|
| Trades at Trade Republic | Export the transaction CSV and run `python app.py import-tr Transaction_export.csv` |
| Trade at DEGIRO or ABN AMRO | Import a screenshot, or change `units`, `cost_eur` and `net_cashflow_eur` in `portfolio.json` |
| New DEGIRO dividends | Add them to DEGIRO's `profit_extra_eur` |
| A ticker is wrong | Put the right Yahoo symbol first in that position's `"tickers"` list, delete `cache/tickers.json`, restart |

## How the numbers work

- **Holdings:** units times the latest price, converted to euros.
- **Profit per position:** current value plus all money in and out for that position, so it includes earlier sales and dividends.
- **Managed portfolio:** live per holding once imported. Until then, the last real value moved by a proxy mix (80% world equity, 20% euro corporate bonds).
- **Savings:** interest accrues daily at the fixed rates.
- **DUO:** interest is added daily. The performance grant is shown but not counted, because it should become a gift.
- **Bonds:** valued at `manual_price_eur` per unit, since free bond prices are unreliable.
- **History:** one point per day in `history.csv`, split into managed, savings, self directed and debt.

## Offline mode

`python app.py --offline` shows the site with the last known prices, without fetching anything.
