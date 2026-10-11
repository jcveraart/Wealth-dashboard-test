# Connections: what to enable and how

Use **personal mode**, install optional packages, then enable the relevant choice in **Setup & help** and restart. All connections start unconfigured. Nothing logs into a bank or shares records just because you downloaded the repository.

## Start in this order

1. **Personal workspace:** follow [Installation](INSTALLATION.md) and check that no sample balances came across.
2. **Your records:** import a small bank/broker export and check totals. This needs no cloud database.
3. **Public data:** enable it for prices and savings comparisons; it does not need a default API key.
4. **One AI route:** choose Claude Code, ChatGPT-plan sign-in or Anthropic API. Use the account you already have when supported.
5. **SEC, if wanted:** configure identification only after you agree to send that contact to SEC.
6. **Cloud/advanced sources, if wanted:** add Supabase, Ollama, OpenBB or Quiver independently. Missing an optional provider should not prevent ordinary local use.

Keep the [complete account/key checklist](KEYCHECKLIST.md) beside you. The [copyable setup-assistant prompt](ASSISTED_SETUP.md) lets ChatGPT or Claude guide these steps. Nothing in this guide supplies a shared key or guarantees a provider subscription.

## Connection map

| Connection | Supplies | What you need | Cost/access note |
|---|---|---|---|
| Local bank/broker imports | Your payments, holdings and execution records | Files you export yourself | No direct bank-login integration is bundled |
| Yahoo Finance | Public market prices/history | Public-data choice and installed dependencies | No key; availability, timing and coverage vary |
| Flexible savings pages | Published Raisin/ABN/Trade Republic offers | Public-data choice | Public comparisons; no account opening or transfer |
| Claude Code | Chat, supported AI imports and observations | Installed CLI and your own login | Uses your plan/provider rules; account limits apply |
| Anthropic API | AI through a saved API key | Your own key and billing | Uses Console API credits/billing; optional |
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

## Claude Code: use your own CLI login

1. Install Claude Code using the current [official setup guide](https://code.claude.com/docs/en/setup). A native Windows option is `winget install Anthropic.ClaudeCode`; macOS/Linux instructions are on that page.
2. Open a new terminal and run `claude --version`, then `claude` to complete your own login.
3. Enable AI in personal Setup and restart the dashboard.
4. In **Settings → Claude & AI**, check the connection and choose Claude for chat/import. The small chat and import provider switches can also change it per workflow.
5. Ask a small question first. Check the chosen account/context and provider's limits.

After login, restart the personal dashboard so it can detect the CLI. A Claude desktop/web login alone is not proof that the command-line program is installed and signed in. If Settings still reports disconnected, run `claude --version` in a new terminal, verify your login with `claude`, then restart the dashboard. See the [official CLI quickstart](https://code.claude.com/docs/en/quickstart).

### Anthropic API: an alternative to CLI login

1. Open your own [Claude Console](https://platform.claude.com/) account.
2. Choose **Settings → API keys → Create key**, name it for this dashboard and choose its scope/expiration.
3. Check the Console's credit/billing balance and usage limits before making API requests. An API route uses Console credits/billing; do not assume a Claude chat subscription provides unlimited API usage. Some eligible plans can claim API credits in a linked Console organization.
4. In the personal dashboard, open **Settings → Claude & AI → API key**. Paste your own key there and select **Save**. Do not use an organization Admin API key.
5. Choose Claude for chat/import, try a small request and verify usage in your own Console. The saved key takes precedence over the CLI route; saving an empty key removes the local saved key. Check any independently configured environment key if it still appears connected.

See [API-key authentication](https://platform.claude.com/docs/en/manage-claude/authentication) and [eligible plan credits](https://platform.claude.com/docs/en/about-claude/api-credits-for-subscribers). This is optional: a working chosen Claude Code route does not require manually copying an API key. Do not paste keys into chat, commit them or place them in the public sample files. AI chat/import sends the selected question/document/context to your configured provider. Explicitly requested supported dashboard edits have Undo; they never place broker orders.

## OpenAI / ChatGPT plan

1. Enable AI in personal **Setup & help**, save/restart, and open **Settings → Claude & AI**.
2. Find **ChatGPT plan** and select **Connect**. The chat/import OpenAI controls can also offer **Continue with ChatGPT**.
3. Complete the OpenAI browser login and consent yourself. Return to the local dashboard; leave it running while the local callback completes.
4. Verify that the plan connection shows connected. Choose OpenAI for **Chat with** and/or **Read imports with**, then **Save choices**.
5. Under **OpenAI models**, choose an available chat/import model or keep the account default. The small chat and Import switches can change the provider for those workflows.
6. Try a short question and check **Usage**. A connected identity or model list alone is not proof that your account can run that request.

This is a ChatGPT-plan sign-in route, not the API-key route. Eligible Plus/Pro accounts can use plan access where the provider permits it; workspace policies, models and preview limits still apply. The app does not silently switch to paid OpenAI API billing. Do not generate or purchase an OpenAI API key for this feature. See the [official sign-in quickstart](https://developers.openai.com/siwc/quickstart) and [preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations).

If sign-in opens but does not finish, confirm the local app is running, complete the browser consent, and retry from the same profile. If a request is refused, keep the exact error with tokens/identifiers removed. Reconnect or choose another available model; eligibility failures may require a different supported provider chosen by you.

Use your own account, not the author's login or a shared token. You can disconnect it in Settings. Windows credentials use local OS protection; on other systems keep credential files and their containing folder private. Signing in does not grant this dashboard access to your ChatGPT conversation history.

## Ollama

1. Install [Ollama](https://ollama.com/download) and start its local service.
2. Follow the [official quickstart](https://docs.ollama.com/quickstart) to download/run a **local** model suitable for your hardware. A cloud model is a different choice and should not be described as local processing.
3. Confirm a model appears with `ollama list`. Model downloads use disk space and an internet connection; inference needs suitable memory/compute.
4. Enable AI in personal Setup, restart, then select the model under Settings' local-AI controls.
5. Test a small supported categorisation/classification task and check the result.

The included adapter expects Ollama on `http://127.0.0.1:11434`. In Settings, select a local model for small tasks. This is not a substitute for a live research source or a guarantee that chat/import supports every local model. Check classifications and extracted figures. Local-model availability can be seen in Settings; the demo never discovers or uses your local model automatically.

## SEC EDGAR and research coverage

1. Enable public data in personal mode.
2. In **Settings → Public data** / **Connections**, enter the contact identification SEC requires.
3. Explicitly allow that identifying contact email to be sent with SEC requests.
4. Refresh research and inspect filing/report dates and coverage.

SEC data is disclosure data: institutional holdings are delayed, insider forms need classification, and non-US coverage can be missing. Absence of a record is not proof that no event occurred. Read [INTELLIGENCE.md](../INTELLIGENCE.md) for sources and calculation conventions. Public ECB, OECD, BIS, AFM and other adapters need no private-bank login; optional providers may need their own account.

## Supabase cloud copy

Local use does not require Supabase. If you choose it, the configured portfolio/history/payment/receipt metadata is copied to your own hosted project; raw local source files are not automatically made public.

### Create your own project

1. Open [Supabase Dashboard](https://supabase.com/dashboard), sign in and create a **dedicated empty project** for your own dashboard. Complete any project/plan/terms decisions yourself.
2. Choose your organization, a clear project name and an appropriate region. Keep any database password in your own password manager; this application uses its REST interface and does not ask for that password.
3. Wait for the project to finish provisioning. Do not reuse a production database from another application.

### Create the tables before connecting

Open **SQL Editor → New query** in that project. In your extracted application folder, open each file as text, copy its full contents into a query, run it, and check for a successful result before continuing. Use this order:

| Order | Repository file | Creates |
|---|---|---|
| 1 | `supabase-schema.sql` | Core accounts, institutions, holdings, instruments, history and portfolio backup |
| 2 | `supabase-history.sql` | Recorded account history and yearly flows |
| 3 | `supabase-spending.sql` | Payment accounts, categories, rules and transactions |
| 4 | `supabase-plans.sql` | Recurring investment plans and payment linking fields |
| 5 | `supabase-receipts.sql` | Invoice/product metadata and evidence links |

These are fresh-install scripts for this app's schema, not general migrations for an arbitrary existing database. They contain no destructive DROP TABLE commands. Keep RLS enabled; the views use the caller's security context and no public read policies are supplied. Do not add anonymous/public read policies just to fix an incorrect key.

### Find the two values the dashboard needs

1. In your project's **Connect** dialog, find the **Project URL**, shaped like `https://YOUR_PROJECT_REF.supabase.co`. This is not the dashboard page address and not a PostgreSQL connection string.
2. In **Settings → API Keys**, find or create a dedicated **server secret key**, beginning `sb_secret_`. Prefer this modern key for a new project. An existing legacy `service_role` key is a supported alternative while available; a publishable/anon key cannot perform this app's backend copy.
3. Keep the secret private. It has elevated database access and bypasses RLS. Do not send it to a setup assistant, commit it, embed it in frontend code, or share its screenshot. Only your own local Python backend uses the key saved through the local form. [Official key documentation](https://supabase.com/docs/guides/getting-started/api-keys).

### Connect and verify the first copy

1. In personal **Setup & help**, enable **Supabase**, then save/restart. Enabling it alone does not create a connection.
2. Open **Settings → Data → Cloud copy → Set up**.
3. Enter your **Project URL** and **Secret key** yourself in the local form.
4. Select **Connect and sync** only when you are ready to send the intended portfolio/history/payment/receipt metadata to your own project. This button tests access, saves the local configuration and starts the first copy; it is not a read-only test button.
5. Inspect the sync result, then open your own Supabase **Table Editor**. Verify the expected accounts, holdings and payments, and check receipt metadata where present. No rows on an empty personal workspace can be a correct result.
6. Later, **Sync now** requests another copy; automatic copying requires the app to remain running. **Disconnect** stops use of the saved connection but leaves the existing cloud rows in place.

This is a local-to-cloud copy, not a bank connector and not automatic two-way editing/restore. The spending sync replaces the dashboard's spending tables in that project; this is another reason to use a dedicated project. Local source documents are not uploaded as cloud file storage by this metadata sync.

### If it fails

| Message or symptom | Check |
|---|---|
| Project URL rejected | Use the HTTPS project URL, not the dashboard page or database connection string |
| Key rejected / 401 / 403 | Correct project, server secret, key not revoked, and personal cloud feature enabled |
| Tables missing | Run all five SQL files in the correct project; read the SQL result |
| Core rows copied but receipt metadata missing | Apply `supabase-receipts.sql`, then Sync now |
| No rows | Confirm there are real records in this personal workspace and inspect the sync result |
| Connection worked earlier | Confirm project availability/quota and your key's status in the provider dashboard |

Never use another person's project/key. Troubleshoot a redacted error without copying secrets or raw financial rows into public chats/issues.

Do not run the synthetic SQL seed against a personal project. `build_supabase_seed.py` is only for a separate empty **demo** project if you deliberately want to inspect example tables; it creates SQL locally and makes no connection. Never use a friend's/project author's secret key. GitHub never needs this key.

## OpenBB, Quiver and other optional sources

Most public features use the built-in sources. OpenBB is optional and is not installed by the basic installer. It is not preinstalled for the person downloading this repository.

### OpenBB: advanced, optional

Start the personal profile once so its folder exists. Use Python 3.10+ (3.11/3.12 recommended) and install the repository's v4 compatibility requirements in the private personal runtime. From the **project folder**, the Windows commands are:

```text
python -m venv .personal-runtime/.openbb-env
.\.personal-runtime\.openbb-env\Scripts\python.exe -m pip install -r requirements-openbb.txt
```

On macOS/Linux:

```text
python3 -m venv .personal-runtime/.openbb-env
.personal-runtime/.openbb-env/bin/python -m pip install -r requirements-openbb.txt
```

The adapter detects that runtime-local environment. Restart the personal app and check **Data connections & coverage → OpenBB**. The supplied adapter uses a v4-compatible layout; upgrading major versions can require code/configuration changes. Try supported public data first; additional providers have their own entitlements and private settings. No author credentials are installed.

 Follow `INTELLIGENCE.md` and `requirements-openbb.txt`, use a separate OpenBB environment, and configure its Python/provider path in Connections. Provider entitlements and returned datasets vary; missing data remains unavailable.

### Quiver: advanced, optional

Open [Quiver API setup](https://www.quiverquant.com/api-setup/), sign into your own account and check that your entitlement covers the datasets you want. Obtain your own token, enable public data in personal mode, then use **Data connections & coverage → Quiver API key** and **Save connections**. Refresh a supported dataset and inspect its source/coverage or failure. A saved key is not proof of entitlement.

For Quiver, add your own key in Settings only if your subscription supplies the desired dataset. It is not necessary for the core dashboard. You can remove optional keys without losing your local financial records.

## Other built-in public sources: no extra key checklist

The current adapters include selected ECB, Eurostat/CBS, World Bank, OECD, BIS, FRED chart CSV, AFM disclosures, GLEIF, OpenFIGI identifier candidates, GDELT, openFDA, ClinicalTrials.gov, USAspending and Kraken public-market history. Use public-data mode and the supported query controls in Connections/research tools. Coverage and public rate limits vary; an available adapter is not a promise that every query succeeds.

You do not need a separate key for each of these included public adapters. The FRED adapter uses selected public CSV downloads, not every keyed FRED API function. Kraken public candles do not use your exchange account or permit trading. OpenFIGI returns identifier candidates for review, not proof that a security match is correct. None of these connects to your bank or uploads your ledger as a public-data search query.

## GitHub and updates

GitHub distributes the code, not your finances. Downloading a ZIP requires no Git login. Cloning/pulling requires Git; a private fork requires your own GitHub authentication. Keep runtime folders ignored. Source-update checks do not upload your local finances. Read the installation update steps before replacing code.

## Backups and moving computers

Use a portable encrypted backup with a password you keep separately. Preview the restore and recover into a new/isolated workspace before replacing the old one. Windows-local keys are tied to that OS user; do not assume copying a credential blob is a portable login. Sign in to providers again on the new machine. The demo's sample files and reset backups are distinct from your personal records.
