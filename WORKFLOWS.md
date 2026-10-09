# Connected workflows

The existing dashboard, theme, provider switches and AI logos are retained. **Investments** contains the owned portfolio, actual performance, allocation/risk, savings plans and portfolio signals. **Explore** contains opportunities, watchlists, superinvestors, insider activity and company research, with the current portfolio used as context for diversification. **Review** collects actionable evidence tasks.

Navigation follows the Spending design, with at most two menu rows at the top. Investment totals and the main chart sit beside each other on desktop; principal widgets and supporting details start open. Cash flow is linked from Spending, planning records from Plan, documents from Import/Spending, and Connections/Backups from Settings. Search finds every workflow.

Overview retains the original net-worth/Claude header and adds a small recorded net-worth trend. Spending and investment summaries lead the page, followed by advice/review, goals, savings/debt, tax records, exploration and document/connection links. Full net-worth history, account details and personal pins remain available below. Home spending summaries cover all payment accounts. The briefing considers spending, investments, savings plans, goals and pending advice, with useful recorded facts available while AI works in the background.

Payment drill-down popups include From/To dates and minimum/maximum absolute EUR amounts. Bounds are inclusive and narrow the original selection; Reset returns to that selection. The payment count and signed net total update without replacing the filter inputs. Open in Transactions carries the exact selected payment IDs, including the source of split payment lines, and provides a removable popup-selection chip.

The browser preloads frequently used local data with two requests at a time and reuses in-flight requests. Financial responses stay in memory, never in browser persistent storage. Background polls update numbers without rebuilding the active page or clearing chart selections; public research jobs offer an Apply button when new results are ready. Explicit edits and navigation may update the view. First-time external source downloads still take time, and missing data remains missing.

Investment portfolio notes use AI to choose up to two observations from calculated facts; the model cannot create numbers. Notes are scoped to the selected investment account and asset class and carry the original price timestamp. Region classification uses bounded AI requests containing security names/identifiers/categories, without balances or units. Known classifications are preserved, placeholders may be filled, low-confidence answers are withheld, and inferred labels carry their basis/date. Fund exposure is based on the investment mandate rather than registration domicile; exact weights still require disclosed holdings.

## Daily use

- **Review:** watched-folder intake, payments needing categorisation, invoices needing bank links, reimbursements, policy expiry, decision reviews and investment signals. Open the original record or defer a task.
- **Search:** search payments, invoice products, extracted original text, holdings, accounts, notes, chats, workflow records and cached company research. Payment filters accept `account:"Account name"`, `category:groceries`, `after:2026-01-01`, `before:2026-12-31`, `type:payment`, `above:40`, and `missing:invoice`. Search amounts as well as merchant names.
- **Cash flow:** observed recurring payments with evidence, fixed-price changes, a 90-day forecast, budgets with optional carryover, reimbursements and project/trip payment links. Internal transfers are excluded from spending. A forecast needs a recorded or explicitly supplied opening balance; variable shopping is not silently treated as a subscription.
- **Performance:** choose an investment account and date window; inspect actual recorded valuations, external flows, profit, time-weighted return, annualised money-weighted return, and Modified Dietz. Completeness must be explicitly checked. Missing flow-date valuations withhold TWR; missing opening lots, transfers or unverified same-day trade order withhold FIFO gains. Closed positions remain in the full ledger.
- **Planning:** goals without assumed growth, claims, trips/projects, policies, warranties, property evidence, institution/protection evidence, and stress scenarios. Evidence-only property records do not silently change net worth. Lender-specific DUO rules are not replaced with generic fixed-rate loan assumptions.
- **Documents:** originals, local text search, invoice/product/payment chains, bank-credit refund allocations, exact supplier/SKU unit-price history, field-presence checks, layout correction notes, document comparison, and imported ESEF numeric facts with their original contexts and units.
- **Connections:** source availability, last failures and research jobs. Read-only cloud-copy comparison and GitHub source update previews never merge or overwrite either copy.
- **Backups:** complete encrypted financial backups, password-protected portable copies, integrity-checked restoration into a separate folder, local audit history, annual evidence ZIP, Excel, JSON, CSV, calendar dates, printing/PDF and a newly generated fictional demo.

## Savings plans and chat changes

Plans store the investment account, product name, amount per execution, frequency, starting date, optional execution days, optional product type and confirmed execution fee. Weekly means 52 scheduled contributions per year on average; biweekly means 26; **twice monthly means 24**. Unknown ISINs, fund fees and second monthly dates remain unknown. A private-market fund is not mapped to the publicly traded EQT/Apollo company merely because the name matches.

Manual plan edits take precedence over detected Trade Republic plans. Recording or stopping a plan in this application **does not send orders or instructions to the broker**. Confirm its actual activation/cancellation in the broker's own application.

Claude Code, Claude API and OpenAI share the same dashboard tools. Questions expose read tools. Explicit edit requests expose validated edit tools for supported records, scoped to the context selected inside chat. The assistant must read current record indices/references first; stale references are rejected. Successful changes refresh the dashboard and provide **Undo**. Workflow Undo checks for later edits rather than overwriting them. Existing attachment imports retain their established import validation and Undo.

Supported chat edits include savings plans, watchlist, to-dos, legacy goals/pots/profile/savings/debts (as allowed by context), plus workflow goals, budgets, bills, projects, claims, policies, notes, decision journals, prompts, refund links and other validated workflow records. Investments context cannot edit payment-account balances. Document text and public webpages are evidence, not permission to change records. Switching context starts a fresh chat; import questions are delivered only in All context.

The read registry contains 29 tools; an authorised edit turn adds two bounded mutation tools. OpenAI uses the existing ChatGPT connection and model entitlement: the application never falls back to paid API billing. Provider authentication and usage limits still apply. The chat mutation flow was verified end-to-end using Claude Code with a fictional plan, followed by successful Undo. OpenAI's shared tool protocol is covered by regression tests; no claim is made that every account/model entitlement is available.

## Original files and import formats

Drop files into the local **import-inbox** folder. A watcher queues them for review; original bytes are retained separately from parsed data. Existing bank and broker formats remain supported. PDF text extraction, DOCX, TXT, HTML/XHTML/XML and CSV are indexed locally. Scanned image PDFs require the existing AI/OCR importer; no invented text-extraction confidence percentage is displayed.

Download **Broker ledger CSV template** under Performance for complete executions, fees, taxes, deposits, withdrawals, corporate-action ratios and verified timestamps. Cash amounts are signed **net execution cash**. Explicit fee/tax columns are evidence breakdowns, not extra amounts added again. Non-EUR records need verified EUR cash amounts before EUR gains can be computed. Trade Republic exports retain their full ledger independently of current held-position trade limits.

Download **Holdings CSV template** for dated fund disclosures. Include the held fund ISIN, underlying identifier/name, weight and disclosure date. Whole-batch weights validate before any write; versions are retained. Partial lists show coverage and known overlap as a lower bound. An absent holding in a partial report is not assumed sold. Local ESEF imports preserve numeric `nonFraction` facts, reporting contexts, units and supported scale/decimal transforms; unsupported transforms stay unavailable and are not aggregated across dimensions.

Invoices and refund allocations reference existing bank transactions. They do not create duplicate spending or income. No invoice is automatically assumed to match a payment solely because its merchant/amount is similar.

## Public sources

Public queries send only the supplied public company name, market identifier, series or country code. Personal payments and private documents are not appended. Responses are bounded, cached, dated and show failures; stale evidence is labelled.

| Source | Working adapter / scope |
| --- | --- |
| ECB | Existing verified rates, FX and inflation adapter |
| World Bank | Annual country consumer-price inflation |
| Eurostat | Monthly all-items HICP annual change |
| CBS | Raw Dutch CPI table rows, original category/period codes retained |
| BIS | Monthly broad real effective exchange-rate index, e.g. NL |
| OECD | Covered-country composite leading indicator, e.g. USA; current dataset excludes NLD |
| FRED | Public CSV for CPIAUCSL, DGS10, UNRATE and FEDFUNDS; API functions still need a key |
| AFM | Official current short-position and MAR 19 management-transaction CSV exports |
| OpenFIGI | ISIN/ticker mapping candidates requiring exchange/share-class verification |
| GLEIF | Legal-entity candidates; a name match alone does not establish parent ownership |
| GDELT | Public company news discovery; rate-limit failures remain visible |
| ClinicalTrials.gov | Sponsor-matched registered studies, not efficacy or approval predictions |
| openFDA | Drugs@FDA sponsor applications/submission statuses; abbreviations such as NOVO may be required; no matches is a valid empty result |
| USAspending | US disclosed government award keyword search; not inferred listed-parent revenue |
| TED | European published procurement notices, not automatically awarded contracts |
| Kraken quotes | Public exchange market quotes |
| Kraken history | Bounded completed daily OHLC candles; current incomplete interval excluded |
| RSS/Atom | User-saved public feeds with capped responses and private-network URL blocking |

The existing SEC filings/company facts/Form 4/13F, Yahoo/OpenBB prices, valuation history, research scores, source-linked dossiers and portfolio analytics remain integrated. SEC issuer discovery searches the reported ticker universe; numeric screening applies only to companies whose ratios were actually retrieved. Selected batches fetch up to ten companies; original discovered corporate filing text can be retained and compared locally. This is not a complete real-time worldwide stock screener.

## Background operation

On Windows, **start-windows.bat** starts the dashboard in the background and opens the site. Its tray menu opens, restarts or stops the verified local instance. The desktop controller can install/remove its own login-startup shortcut. A terminal need not remain open. The server remains bound to loopback, and API requests reject foreign origins/hosts.

Local maintenance performs weekly encrypted backups and deterministic weekly digests, checks due/price changes, records savings-rate observations, and refreshes enabled public feeds. Browser notifications are optional and request permission only after the user clicks Enable. No email, SMS or third-party messages are sent automatically.

## Coverage of the enhancement list

| Ideas | Implemented foundation | Requires credentials, evidence or further source-specific work |
| --- | --- | --- |
| 1–10 usability | Background/tray, connection coverage, review, global search, filters, saved views, period-aligned performance and evidence links | A full explanation of every historical numerical revision requires versioned source history; not all old dashboard numbers have it |
| 11–20 accounts/imports | Existing bank/broker/PayPal imports, complete broker-ledger format, TR full history, identifiers and coverage | Enable Banking/Tink/bunq/IBKR need app/account authorisation; broker-specific extra layouts need representative exports |
| 21–30 documents | Watched intake, product/payment/refund chains, text search, field checks and reusable correction notes | Email intake, order/shipment APIs and Paperless need account/archive access; camera capture/private phone access needs device permission/setup |
| 31–40 cash/planning | Forecast, recurring costs, price changes, commitments, carryover budgets, goals, claims, trips, SKU prices and monthly comparison | Exact personal inflation needs a verified mapping to published categories |
| 41–50 investment history | TWR/MWR/Dietz, actual valuation curves, full ledger/closed FIFO, explicit fees/taxes, splits, matched-flow benchmark and journal | Full historical holdings, dividend reconciliation and tax-lot corrections need complete verified broker evidence |
| 51–60 research | SEC issuer discovery, researched-company filters/peers, recorded valuations, filings/text comparison, notes and bounded refresh progress | Complete all-market point-in-time fundamentals, segment datasets, transcripts and consensus generally need licensed feeds or issuer-specific acquisition |
| 61–70 fund/disclosure | AFM registers, ESEF facts, fund disclosure versions, look-through, overlap and dated changes | Full fund reports/share classes/cost sheets and issuer IR feeds need exact sources; revenue-weighted currency exposure needs disclosed geographical revenue |
| 71–80 other assets | Fixed-coupon yield/duration/calendar cash flows, savings-rate history, simple interest comparisons, institution evidence, fixed-rate repayment and completed crypto history | Verified protection terms, lender-specific DUO terms, exchange exports and wallet addresses need owner evidence/authorisation |
| 81–90 macro | ECB/FRED/CBS/Eurostat/BIS/World Bank/OECD source views and charts | Category-weighted inflation and macro/market annotations need compatible series and verified event calendars |
| 91–100 alternative data | Existing optional Quiver plus USAspending/TED/trials/FDA/GDELT/GLEIF and public RSS | EPO/EIA keys and some Quiver datasets need registration/entitlement |
| 101–110 AI | Shared deterministic tools, original links/dates, scope selection, progress, saved prompts, fact/assumption notes, local AI fallback, backend scenarios and requested record edits | Provider login/model availability still belongs to the selected provider; autonomous broker trading is not implemented |
| 111–120 evidence/planning | Annual packs/checklists, tax evidence snapshots, goals, stress, property/policy/warranty evidence | Pension-product adapters, complete tax/withholding calculations and BAG property acquisition need statements/verified terms or selected property details |
| 121–130 operations | Optional alerts, digest, complete encryption, verified separate restore, cloud comparison, source update preview, scheduled jobs, fresh synthetic demo and exports | Automatic source merging and authenticated off-laptop/Tailscale/device serving need explicit setup; no external storage destination was invented |

All private records, originals, credentials, sessions, caches, local databases and backups remain excluded from Git. The public demo repository is not modified by this private upgrade.


## Cash and debt workspace

Savings & debt lists current accounts, flexible savings and uninvested broker cash. Fixed deposits and securities remain in Investments; their classification and net-worth values are preserved. Cash history uses recorded cash-account balances only: a broker portfolio-value series is never relabelled as cash.

Debt history uses recorded named balances, with recorded aggregate debt as a fallback. Constant-rate monthly-compounding scenarios compare no repayment, an entered monthly repayment and extra repayment across 5–35 years. Horizon truncation is reported honestly; a missing interest rate withholds the projection. Missing repayments start at zero with an explicit illustration label. Scenario inputs never save financial changes. Edit the debt to record a confirmed repayment, DUO regime or interest-fix end date.

Cash/debt notes compare actual saved cash/debt rates on a marginal EUR 1,000 basis. AI chooses useful recorded observations; it cannot invent rates or numbers. DUO context links official repayment rules, and distinguishes bonds from withdrawable cash. The connected chat can perform a broader live comparison on request.

Payment popups use one compact sorting row (date/absolute amount and ascending/descending). Counts and scope remain unchanged. The tax workspace, home tile, planning preparation panel, shortcut and tax-snapshot search results are disabled for now. Existing financial records and recorded withholding remain preserved.


## Company research

Company research now begins with a compact company summary, a daily stock-price chart in quote currency and a source-linked briefing with a direct conversation input. Plain Yahoo daily Close is cached separately from adjusted investment-return history. A clearly labelled adjusted-history fallback appears while normal prices are retrieved. Missing prices are never synthesized. Chart ranges sit inside the widget; background results respect active chart hover/selection.

The briefing uses recorded company descriptions, dated headlines, financials and calculated portfolio-fit context. Claude writes qualitative observations in the background; numerical claims and foreign source IDs/URLs are rejected. Exact figures remain in deterministic widgets. Source-based notes remain usable while AI is unavailable. Refresh company data and use the chat for broader current research. Full fundamentals, ownership, filings and thesis/scenario tools remain below.


## Consistent AI briefings

Home-style soft-blue Claude cards sit at the top right beside the summary on Cash & debt, Investment overview, Company research, Advice and Explore opportunities. Narrow screens stack the same card after the summary. Each page has its own scoped observations and a context-aware conversation action; charts remain independent.

The state response includes read-only ready cash/investment/advice/opportunity observations, and company research includes its ready briefing. Reading these does not launch models, make network requests or write caches. Existing cached AI observations display immediately; otherwise honest recorded-data observations remain visible while the selected AI route updates in the background. A failed update retains useful content. Source/provenance captions distinguish saved AI observations from recorded-data fallbacks. Chat, provider controls and import flows retain their existing behaviour.


## Savings & debt overhaul

Five views share the Spending-style tab bar and cash-account chips: Overview, Accounts, Rates & options, Debt & repayments, and Reserves. The soft-blue scoped Claude card stays top-right, opens with recorded/cached observations and supports a contextual conversation. The workspace is warmed with other page reads; background public-rate updates offer Apply instead of rebuilding the page during analysis.

Account details include recorded versus estimated value, gross earnings/day/month/year, purpose, withdrawal terms, paid-interest evidence, recorded rate notices, savings plans, account-scoped cash history and uniquely matched payment movements. Unknown or ambiguous payment matches stay unknown. Broker portfolio values are never presented as cash history. Flexible savings, broker cash and managed cash are included; bonds and fixed deposits remain in Investments. Negative cash is deducted when estimating cash above conservative reserves.

Public offer adapters use Raisin's published structured overnight EUR catalogue, ABN AMRO's first Direct Sparen tier and Trade Republic's explicitly advertised new-customer offer. Requests use a generic user-agent and contain no contact email, balances, payment details or credentials. Products retain source/effective/retrieval dates, access, amount tiers, promotional eligibility and reported legal-bank protection. Standard comparisons exclude promotions; introductory returns are limited to the verified period, and unknown durations withhold estimates. Partial failures preserve last verified products with stale markers. Coverage is the published loaded catalogue and named sources, not the entire market. Saved personal rates are never automatically replaced.

Repayment scenarios hold both upfront money and monthly budget equal, save the extra budget in the keep-cash case and save unused repayments after payoff in both cases. Constant nominal annual rates use monthly rate/12 compounding. These are illustrations; rate resets, costs and possible DUO forgiveness are not forecast. Missing saved rates require explicit assumptions. The tool changes no financial records.

The AI can read cash evidence and public quotes and call the deterministic scenario calculator. Its automatic note selection uses only recorded/calculated facts, compares the best saved rate with loaded ongoing quotes, distinguishes promotions and preserves liquidity/DUO context. Cash tools in Planning omit transaction-level payment records.
