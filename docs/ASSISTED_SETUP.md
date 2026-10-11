# Set up with help from ChatGPT or Claude

Use this prompt in your preferred assistant. It guides the assistant through the actual application setup, while leaving provider logins, secrets and financial choices with you.

## Which assistant should I use?

- **A normal ChatGPT/Claude web chat:** it can explain steps and troubleshoot redacted errors. It generally cannot read your downloaded folder or operate your local dashboard unless an appropriate local tool is connected.
- **An assistant with local terminal/file access:** open the extracted project as its workspace, then paste the prompt. It can inspect the code and perform permitted local installation/checks. Its tool permissions and your provider access still apply.
- **The dashboard's own chat:** configure its provider first. This chat is for your dashboard data/workflows; do not rely on it to install the application that is running it.

You do not need to upload your finances or keys to get installation help. Answer with your OS, folder, desired features and redacted errors. The assistant should explain what it can access before acting.

## Before you paste

Have the [installation guide](INSTALLATION.md), [key checklist](KEYCHECKLIST.md) and [connections guide](CONNECTIONS.md) available. You can paste the prompt as-is: the assistant should ask for missing preferences. If using a web-only chat, provide the public repository link and these public documents if it cannot retrieve them.

In the running app, **Setup & help → Setup checklist & assistant prompt** opens the same instructions. The in-app guide has **Copy setup prompt** and **Download prompt** controls. On GitHub, copy the entire text block below, or open the [plain-text prompt](../web/setup-assistant-prompt.txt), choose Raw and copy it.

## Copy this entire prompt

```text
Help me install and connect my own local Wealth dashboard from https://github.com/jcveraart/Wealth-dashboard-test. I am a beginner. Keep the demo separate from my personal finances, and keep the existing design.

Read the current README, docs/INSTALLATION.md, docs/KEYCHECKLIST.md and docs/CONNECTIONS.md first. Check the actual downloaded version and settings before giving commands. If you cannot browse or read files, say so and ask me for the relevant documentation, without private records or keys.

First ask, in one short message, for my operating system, extracted folder, preferred AI route (Claude Code subscription, ChatGPT plan, Anthropic API, or none), whether I want a Supabase cloud copy, and whether I want SEC or advanced providers. Recommend local imports + public data + one AI provider as the first stage. I do not need every paid service.

Explain whether you have access to my local files/terminal. If you do, perform the authorised local installation and reversible checks. If you do not, guide me one small step at a time with commands for my OS and wait for the result. Do not claim that a normal web chat can open localhost or connect my computer without an appropriate tool.

1. Verify Python and the complete extracted folder. Start demo.py and confirm fictional data appears. Preserve any existing runtime and my edits. Use the launcher and its actual local port; never stop an unrelated server or reset personal data.
2. Create/reopen the separate personal workspace with personal.py or Setup & help. Verify that it is empty of demo records. Install optional features with install.py in the project folder when needed; the launcher should use this project's virtual environment.
3. Enable only the features I chose in personal Setup & help, save/restart, and configure them in Settings. Leave unwanted services disabled.
4. For public prices/research/savings comparisons, use the supported built-in sources first. Check source dates, stale/unavailable messages and a public ticker. No default Yahoo or savings API key is needed. This does not log into my bank.
5. For AI, guide my chosen route. Claude Code needs the CLI and my own login; Anthropic API needs my own key and usable Console credits/billing. OpenAI uses this app's ChatGPT-plan sign-in, not a pasted OpenAI API key. Complete login/consent myself, then test a short request after approval and verify the selected chat and import providers. Respect eligibility/limits; do not introduce a paid fallback.
6. For SEC, explain the contact identification sent in requests and ask whether I consent before configuring it. Missing filings should stay unavailable.
7. If I chose Supabase, help me create my own dedicated empty project. Have me complete account creation and terms. Apply the five repository schema files in documented order: supabase-schema.sql, supabase-history.sql, supabase-spending.sql, supabase-plans.sql, supabase-receipts.sql. Keep RLS enabled. Never reuse another app's production database or seed my personal project with demo data. Explain where to find the Project URL and server secret in the project's Connect dialog / Settings > API Keys. Let me enter the secret directly in my local dashboard, then explain that Connect and sync tests and writes the intended cloud copy. Obtain my approval for that first sync and verify rows in my own project.
8. Configure Ollama, OpenBB or Quiver only if I chose them. Use the included requirements/adapter instructions and my own provider entitlements. Do not install every provider or assume any paid dataset is available.
9. Guide a small real import locally. Explain which files/context will go to an AI provider before sending them and obtain my approval. Check account, date, currency, totals, duplicate handling and Undo. Invoices must link to existing payments, not duplicate spending. Keep savings plans as dashboard records; never place financial orders.
10. Help me create and verify a portable backup, and explain normal start/stop/update commands. Finish with a concise table: feature, working/skipped/unavailable, evidence checked, and anything I must still do.

Do not ask me to paste API keys, passwords, tokens, private financial documents or unredacted screenshots into this chat. I enter credentials directly in my own app/provider UI. Do not print secrets, copy another person's credentials, commit runtimes/backups or expose the server to the internet. Explain costs and data destinations before I choose a connection. If a step fails, use the actual redacted error to troubleshoot rather than guessing or declaring it connected.
```

## What a successful setup report looks like

The assistant should identify your actual personal URL/folder, selected services and verified results. “Skipped by choice” and “unavailable for this account” are valid outcomes. It should never call a connection successful just because a checkbox is selected, a key was saved or a sign-in page opened.

Provider sign-in, billing/eligibility and the first real data transfer require your own participation. The prompt does not grant your assistant a bank login, permission to trade, or access to another user's accounts.
