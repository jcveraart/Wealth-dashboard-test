# Setup checklist: accounts, keys and what to connect

Start with the demo. You do not need to collect keys before trying it. In personal mode, **local imports + public data + one chosen AI provider** are a useful first setup. Supabase and advanced data providers can wait.

An **API key** is a secret that lets an application use a service. A **project URL** is the address of your database. **Sign-in** means completing the provider's browser login; you do not copy its tokens yourself.

Use the [installation guide](INSTALLATION.md) to download/start the app, [connection instructions](CONNECTIONS.md) for each feature, and the [setup-assistant prompt](ASSISTED_SETUP.md) if you want ChatGPT or Claude to walk you through it.

## Choose your setup

| What you want | What to connect | What to collect |
|---|---|---|
| Try the dashboard | Nothing | Python and the extracted download |
| See your own finances locally | Personal profile and your own imports | Bank/broker exports; no bank password |
| Public prices, research and savings comparisons | Live public data | Optional packages; no default market API key |
| Chat/import with Claude on your plan | Claude Code CLI and your own login | Eligible Claude access; no manually copied API key for this route |
| Chat/import with OpenAI | ChatGPT-plan sign-in | Eligible ChatGPT account; no OpenAI API key |
| Claude through its API instead | Anthropic API | Your own API key and usable Console credits/billing |
| Small AI tasks on your computer | Ollama | A downloaded local model; no cloud key |
| US filings, insiders and investor disclosures | SEC EDGAR | App/contact identification and consent; no SEC API key |
| Keep a cloud copy | Supabase | Your own dedicated project URL + server secret key |
| More research datasets | Optional OpenBB / Quiver | Optional environment; provider keys only for datasets you select |

“Everything” does not mean every paid service. Connect only the features you want. Enabling public data does not connect a bank or copy its transactions.

## Before touching accounts

- Download and extract the whole repository; verify the demo works on port 8051.
- Choose **Use my own data → Start my personal workspace**. Its default port is 8052.
- Confirm the bar says **Personal · your local data** and the workspace contains no demo balances.
- From the extracted project folder, install optional features with `python install.py` (or `python3 install.py` on macOS/Linux), then restart the personal launcher.
- In personal **Setup & help**, choose Live public data, AI and/or Supabase, and select **Save choices & restart this workspace**.
- Configure the chosen accounts in **Settings**. These checkboxes enable features; they do not perform provider sign-in.

## Complete key and account inventory

| Item | Needed when | Where to obtain it | Where this app uses it |
|---|---|---|---|
| Supabase project URL | You choose cloud copy | Your project's **Connect** dialog | Settings → Data → Cloud copy → Set up → Project URL |
| Supabase server secret (`sb_secret_…`) | You choose cloud copy | Project **Settings → API Keys**; create a dedicated secret if needed | The local Secret key field, then the private Python backend |
| Legacy Supabase `service_role` | Only for an existing legacy setup | Project Settings → API Keys | Supported alternative to the modern secret; use the modern secret for new setups |
| Anthropic API key | You choose the Claude API route | Claude Console **Settings → API keys → Create key** | Settings → Claude & AI → API key |
| Claude Code login | You choose the subscription/CLI route | Run `claude` after installing the CLI and complete your own login | Detected by the dashboard after restarting it |
| ChatGPT login | You choose OpenAI in this app | Settings → Claude & AI → ChatGPT plan → Connect; complete browser consent | Stored by the app's local sign-in flow; do not copy tokens into a field |
| SEC contact identification | You choose SEC requests | An email/contact identification you are willing to send to SEC | Settings → Public data; research Data connections & coverage |
| Quiver API token | You choose supported Quiver datasets | [Quiver API setup](https://www.quiverquant.com/api-setup/) and your entitled account | Data connections & coverage → Quiver API key |
| Other OpenBB provider credentials | Only a chosen provider needs them | That provider's official account/developer console | Its private OpenBB settings, not this repo or frontend |
| Portable-backup password | You create an encrypted portable backup | Choose your own password and store it separately | Backups → portable password-protected backup |

The app currently needs **no OpenAI API key**, Supabase database password, Supabase personal-access token or GitHub personal-access token for these ordinary workflows. A ZIP download needs no GitHub login. Do not buy an API key to make a ChatGPT-plan sign-in work.

A Supabase publishable/anon key is not sufficient for this app's backend copy. The database connection string (`postgresql://…`) and the Supabase dashboard page URL are also not the Project URL this form expects. See [Supabase's key documentation](https://supabase.com/docs/guides/getting-started/api-keys).

## Collect information without collecting secrets in chat

Keep this non-secret checklist in your own notes:

```text
Computer/OS:
Extracted application folder:
Demo opens: yes / no
Personal opens and is empty: yes / no
Optional packages installed: yes / no
Public data: enabled / not wanted
AI route: Claude Code / ChatGPT plan / Anthropic API / none
AI sign-in or key entered locally: ready / not ready / not wanted
SEC identification consent: yes / no
Supabase project created for this app only: yes / no / not wanted
Supabase five schema files applied: yes / no / not wanted
Supabase URL and secret entered locally: ready / not ready / not wanted
Quiver/OpenBB: not wanted / chosen and configured
Small import totals checked:
Portable backup verified:
```

Write **ready**, not the actual key. Enter secrets yourself in your own local dashboard's fields. Never paste them into ChatGPT/Claude, a GitHub issue, a screenshot or a shared prompt. Supabase/Anthropic settings are local private files, not a general-purpose secret vault; keep the computer/account and personal folder private. ChatGPT credentials have a separate local store and Windows OS protection where available.

## What to verify after connecting

| Feature | A useful first check | What it does not prove |
|---|---|---|
| Public data | A public ticker/rate has a source and retrieval date | A listing is not a live bank connection or guaranteed real-time data |
| AI | A short question succeeds with the selected provider | Being signed in or seeing a model list does not guarantee every model/request is allowed |
| Import | A small supported export imports; totals and account match; Undo is available | Unavailable return metrics should not be filled with guesses |
| SEC | A requested disclosure is returned with its filing date | Coverage can be delayed or incomplete, especially outside the US |
| Supabase | Own project receives the intended rows after Connect and sync | It is a cloud copy, not automatic account login or two-way restore |
| Local AI | Settings discovers your model and a small supported task works | Full chat/import and live web research are not guaranteed by Ollama |
| Backup | Restore verification opens an isolated recovery copy | A copied Windows credential file is not a portable provider login |

Ask your setup assistant for a final **working / skipped / unavailable** report. A failed sign-in or missing provider entitlement should stay visible; switching to a paid alternative is your choice.
