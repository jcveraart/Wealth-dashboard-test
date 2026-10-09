# Connections: what to enable and how

Use **personal mode**, install optional packages, then enable the relevant choice in **Setup & help** and restart. All connections start unconfigured. Nothing logs into a bank or shares records just because you downloaded the repository.

## Connection map

| Connection | Supplies | What you need | Cost/access note |
|---|---|---|---|
| Local bank/broker imports | Your payments, holdings and execution records | Files you export yourself | No direct bank-login integration is bundled |
| Yahoo Finance | Public market prices/history | Public-data choice and installed dependencies | No key; availability, timing and coverage vary |
| Flexible savings pages | Published Raisin/ABN/Trade Republic offers | Public-data choice | Public comparisons; no account opening or transfer |
| Claude Code | Chat, supported AI imports and observations | Installed CLI and your own login | Uses your plan/provider rules; account limits apply |
| Anthropic API | AI through a saved API key | Your own key and billing | Separately billed; optional |
| ChatGPT plan | OpenAI chat/import where eligible | Continue with ChatGPT in Settings | Plan eligibility, model access and preview limits apply |
| Ollama | Selected small local AI tasks | Installed/running local model | Local inference; hardware and model quality matter |
| SEC EDGAR | Public issuer filings, Form 4 and 13F disclosures | Explicit SEC identification consent | Your configured contact identification is sent to SEC |
| Supabase | Optional cloud copy of dashboard records | Your own dedicated project and secret key | Cloud data leaves the laptop; project plan limits apply |
| OpenBB | Additional public datasets | Separate optional environment/provider access | Dataset coverage depends on provider/version |
| Quiver | Optional alternative datasets | Your own API key/entitlement | Provider subscription may be required |

## Bank and broker records

In your bank/broker application, export statements or transaction/execution CSVs. In the dashboard, open **Import**, upload and review the returned totals. Recognised bank CSVs apply directly with Undo; inspect a preview before applying when that workflow offers one. Start with current balances/holdings, then add history. Supported CSV formats can work without AI; screenshots, PDFs and unrecognised layouts may require a chosen importer.

Bank exports containing PayPal debits do not identify every purchased product. PayPal exports and invoices can add evidence; confirm matching to avoid double-counting. The dashboard does not store a bank password or place orders. Savings plans are dashboard records, not instructions to a broker.

## Live market and savings information

Enable **Live public data**, restart, then use Investments/Explore and **Savings & debt → Rates & options**. The savings view loads source-dated flexible-EUR products, separates promotions, applies published amount limits and retains stale markers when a source fails. It does not replace a saved personal rate or establish your eligibility. A published overnight account may still require transfer time. Protection limits belong to the legal bank and retain their quoted currency.

Public requests concern securities/products, not your account balances. There is no guarantee of complete market coverage or a real-time quote. Inspect source/retrieval/effective dates and product terms before acting. Ordinary daily price charts are separate from adjusted historical-return series.

## Claude

1. Install Claude Code using the current [official setup guide](https://code.claude.com/docs/en/setup). A native Windows option is `winget install Anthropic.ClaudeCode`; macOS/Linux instructions are on that page.
2. Open a new terminal and run `claude --version`, then `claude` to complete your own login.
3. Enable AI in personal Setup and restart the dashboard.
4. In **Settings → Claude & AI**, check the connection and choose Claude for chat/import. The small chat and import provider switches can also change it per workflow.
5. Ask a small question first. Check the chosen account/context and provider's limits.

An Anthropic API key is an optional alternative in Settings and is billed separately. Do not paste keys into chat, commit them or place them in the public sample files. AI chat/import sends the selected question/document/context to your configured provider. Explicitly requested supported dashboard edits have Undo; they never place broker orders.

## OpenAI / ChatGPT plan

Enable AI, restart, then choose **Continue with ChatGPT** in Settings. Complete the provider's browser consent flow yourself, return to the dashboard and verify connection status. Choose an available model and try a short request. Eligible plan usage is distinct from an API-key account; this app does not silently switch to paid OpenAI API billing. Model lists do not themselves prove entitlement, and the provider can reject a request or impose usage limits. See the [official sign-in quickstart](https://developers.openai.com/siwc/quickstart) and [preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations).

Use your own account, not the author's login or a shared token. You can disconnect it in Settings. Windows credentials use local OS protection; on other systems keep credential files and their containing folder private. Signing in does not grant this dashboard access to your ChatGPT conversation history.

## Ollama

Install [Ollama](https://ollama.com/download), run it on your computer, and install a suitable model using its own instructions. In Settings, select a local model for small tasks. This is not a substitute for a live research source or a guarantee that chat/import supports every local model. Check classifications and extracted figures. Local-model availability can be seen in Settings; the demo never discovers or uses your local model automatically.

## SEC EDGAR and research coverage

1. Enable public data in personal mode.
2. In **Settings → Public data** / **Connections**, enter the contact identification SEC requires.
3. Explicitly allow that identifying contact email to be sent with SEC requests.
4. Refresh research and inspect filing/report dates and coverage.

SEC data is disclosure data: institutional holdings are delayed, insider forms need classification, and non-US coverage can be missing. Absence of a record is not proof that no event occurred. Read [INTELLIGENCE.md](../INTELLIGENCE.md) for sources and calculation conventions. Public ECB, OECD, BIS, AFM and other adapters need no private-bank login; optional providers may need their own account.

## Supabase cloud copy

Local use does not require Supabase. If you choose it, the configured portfolio/history/payment/receipt metadata is copied to your own hosted project; raw local source files are not automatically made public.

1. Create a **dedicated empty project** in [Supabase](https://supabase.com/dashboard). Do not reuse another application's production database.
2. Open **SQL Editor → New query**. Run, in order: `supabase-schema.sql`, `supabase-history.sql`, `supabase-spending.sql`, `supabase-plans.sql`, `supabase-receipts.sql` from this repository.
3. These fresh-install scripts do not contain destructive DROP TABLE commands. They assume this application's schema; they are not a migration tool for arbitrary existing tables.
4. Keep Row Level Security enabled. The included views use the caller's security context; no public read policies are supplied.
5. Find your project URL and a **server secret key** (`sb_secret_…`), or a legacy `service_role` key if your project still uses it. A publishable/anon key cannot perform this server-side copy. Secret keys have elevated access; keep them only in local settings. [Official key documentation](https://supabase.com/docs/guides/getting-started/api-keys).
6. Enable Supabase in personal Setup, restart, then enter your own URL/key in **Settings → Data → Supabase**. Test the connection, then request a sync.
7. Verify the rows in your project. Settings shows sync status. Automatic syncing depends on the running app; manual sync remains available.

Do not run the synthetic SQL seed against a personal project. `build_supabase_seed.py` is only for a separate empty **demo** project if you deliberately want to inspect example tables; it creates SQL locally and makes no connection. Never use a friend's/project author's secret key. GitHub never needs this key.

## OpenBB, Quiver and other optional sources

Most public features use the built-in sources. OpenBB is optional and is not installed by the basic installer. Follow `INTELLIGENCE.md` and `requirements-openbb.txt`, use a separate OpenBB environment, and configure its Python/provider path in Connections. Provider entitlements and returned datasets vary; missing data remains unavailable.

For Quiver, add your own key in Settings only if your subscription supplies the desired dataset. It is not necessary for the core dashboard. You can remove optional keys without losing your local financial records.

## GitHub and updates

GitHub distributes the code, not your finances. Downloading a ZIP requires no Git login. Cloning/pulling requires Git; a private fork requires your own GitHub authentication. Keep runtime folders ignored. Source-update checks do not upload your local finances. Read the installation update steps before replacing code.

## Backups and moving computers

Use a portable encrypted backup with a password you keep separately. Preview the restore and recover into a new/isolated workspace before replacing the old one. Windows-local keys are tied to that OS user; do not assume copying a credential blob is a portable login. Sign in to providers again on the new machine. The demo's sample files and reset backups are distinct from your personal records.
