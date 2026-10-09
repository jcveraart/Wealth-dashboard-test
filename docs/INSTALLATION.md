# Installation and first use

This guide starts with a disconnected demo, then creates a separate workspace for your own records. You do not need a GitHub account, bank login, AI account or Supabase project to try the demo.

## 1. Download and extract

1. Open the [public repository](https://github.com/jcveraart/Wealth-dashboard-test).
2. Select **Code → Download ZIP**.
3. On Windows, right-click the ZIP and choose **Extract All**. On macOS/Linux, extract it normally.
4. Open the extracted project folder. Run the files from this folder, not from inside the ZIP.
5. Install [Python](https://www.python.org/downloads/) if you do not have it. Python 3.11 or 3.12 is recommended. The offline demo supports Python 3.9+. On Windows, include Python in PATH when offered.

Keep the whole folder together. `web/`, `workspace/`, `intelligence/` and the launcher files are part of the application.

## 2. Try the demo

| Computer | Start |
|---|---|
| Windows | Double-click `start-demo-windows.bat` |
| macOS | Open Terminal in this folder and run `sh start-demo-mac.command` |
| Linux | Run `sh start-demo-linux.sh` |
| Any terminal | Run `python demo.py` or `python3 demo.py` |

The browser opens [http://127.0.0.1:8051](http://127.0.0.1:8051). The normal launcher starts the server in the background; you may close its launcher terminal after it reports success. For a visible development server, use `python demo.py --foreground` and keep that terminal open.

The blue **Demo · fictional data** bar identifies this workspace. It contains invented investments, payment accounts, savings, debt, plans, an invoice and about five years of history. It does not connect to a bank, AI provider, local model or cloud database. Company figures, prices, headlines and comparison rates in demo mode are examples, not current financial information.

Start with the [screenshot walkthrough](SCREENSHOTS.md). Try account filters, historical graphs, price/date sorting, savings-rate comparisons and debt scenarios. Demo chat returns clearly labelled saved examples. To try a deterministic import, download the **DEMO ONLY** sample CSV from **Setup & help** and upload it on Import.

### Stop, reopen or reset

```text
python launch.py demo --command stop
python demo.py
python launch.py demo --command restart
```

On Windows, `stop-demo-windows.bat` stops this profile. If you used foreground mode, press Ctrl+C in its terminal.

To reset demo edits, first stop it, then run `python demo.py --reset`. The old demo is preserved in the ignored `backups/` folder before a new sample dataset is created. This never resets the personal profile. An interrupted first setup or an old unmarked demo folder is also preserved rather than deleted.

If port 8051 is busy, use `python demo.py --port 8053`. Do not stop an unrelated application just to free a port.

## 3. Switch to your own data

1. In the demo, select **Use my own data** in the top bar, or open **Setup & help**.
2. Select **Start my personal workspace**.
3. Your browser opens the separate workspace at [http://127.0.0.1:8052/#setup](http://127.0.0.1:8052/#setup).
4. Check that the top bar says **Personal · your local data**.
5. The personal workspace starts empty. Sample balances, transactions, invoices, history, settings and connections are not carried over.

Alternatively, double-click `start-personal-windows.bat`, run the corresponding macOS/Linux launcher, or run `python personal.py`.

| Profile | Local folder | Default port | Initial state |
|---|---|---:|---|
| Demo | `.demo-runtime/` | 8051 | Fictional data; external services blocked |
| Personal | `.personal-runtime/` | 8052 | Empty; optional connections disabled |

Returning to the demo does not merge it with personal data. Restarting personal mode preserves your records. There is deliberately no personal-data reset button in the demo launcher.

## 4. Install optional features

The basic demo uses Python's built-in libraries. Live prices, AI authentication, Excel/PDF processing, encrypted-backup support and optional tray features use packages listed in `requirements.txt`.

1. Stop the personal workspace if it is running.
2. From the extracted **project folder**, run `python install.py` (`python3 install.py` on macOS/Linux), or double-click `install-optional-windows.bat`.
3. This creates `.venv/` in this project and installs its dependencies. It does not install OpenBB or connect any accounts.
4. Start `personal.py` again. The launcher uses this virtual environment automatically.

You can also install manually with `python -m venv .venv`, activate it, then run `python -m pip install -r requirements.txt`. Run commands in the same Python environment used to start the dashboard.

## 5. Choose your connections

In personal mode, open **Setup & help**. Enable only what you want:

- **Live public data:** quotes, company research, public filings where configured, and flexible-savings comparisons.
- **AI:** your configured Claude, eligible ChatGPT-plan connection, or local model.
- **Supabase:** your separately configured cloud copy.

Select **Save choices & restart this workspace**. After restart, configure the relevant provider in Settings. A choice enables the feature; it does not sign in, create a financial account, buy anything or copy someone else's credentials. If the browser reloads before restart finishes, wait a few seconds and refresh.

Follow [Connections](CONNECTIONS.md) for exact instructions, costs, data sharing and limitations. Every connection is optional. The public app has no developer-supplied keys and no shared financial database.

## 6. Import real records

Do this in **personal mode**:

1. Begin with a recent bank export in CSV/TXT format where supported. Check its account, currency and date range.
2. Recognised bank CSVs apply immediately and return a summary with Undo. Check imported totals, duplicates and internal transfers. For flows that offer a preview, inspect it before applying.
3. Import current broker holdings and a complete execution/export history. Supported Trade Republic CSVs are calculated deterministically; other statements or screenshots may need AI.
4. Upload invoices or receipts to clarify the products behind existing bank payments. An invoice is evidence, not a second payment. Confirm matching and allocation in Receipts.
5. Enter confirmed flexible-savings balances/rates and debt terms. Leave unknown information empty rather than guessing.
6. Review account links, investment regions, savings-plan schedules and the review inbox.
7. Use **Undo** if an applied import or chat edit is wrong.

No direct ABN AMRO, DEGIRO, Raisin or Trade Republic account-login connector is bundled. Bank/broker exports and documents provide your private records. Public quote/rate sources are separate from account access. The dashboard is EUR-based; verify conversions and imported financial totals.

Return metrics need dated values and complete external cash flows. Missing execution, deposit, withdrawal, fee or FX evidence can leave a metric unavailable. Do not mark coverage complete merely to make a number appear.

## 7. Backups and sharing

Before a major update or moving computers, use **Settings → Backups**. Choose a portable password-protected backup and keep the password separately. Test its restore preview. Some optional cryptographic features require the installed packages.

The personal runtime contains your records, statements, cache, settings and credentials. It is Git-ignored. Financial backups can contain settings/keys; treat them as private. OpenAI refresh credentials are not part of a financial backup, so sign in again after moving computers. Windows-protected credentials/local backup keys may not work under another Windows account; use portable backups for migration.

Share this repository, its Download ZIP link or the screenshot guide. Never share `.personal-runtime/`, real exports, attachments, local settings, credentials, logs or financial backups. Nothing in the demo requires publishing your own data.

## 8. Update the application

**Git checkout:** stop the relevant profile, run `git pull --ff-only`, then restart its launcher. The launcher copies updated code into the runtime while preserving personal records. If Git reports local code changes, review them; do not force-reset your work.

**ZIP installation:** stop the profile, make a portable backup, and extract the new ZIP beside the old folder. Start a fresh personal workspace in the new folder and restore your verified backup using the documented restore workflow, or carefully keep the old hidden personal folder when replacing code in place. Do not overwrite personal runtime files with demo fixtures. Keep the old folder until you have verified the new copy.

After updating, press Ctrl+F5 once in the browser to reload scripts and styles. Existing demo edits remain; resetting the demo is optional and preserves a backup. Older installations containing personal files directly in the project root are not automatically migrated: back them up and import/restore confirmed records into the personal profile.

## Troubleshooting

| Problem | What to do |
|---|---|
| `python` or `py` not found | Install Python, reopen the terminal, then try `py -3 --version` or `python3 --version`. On Windows, check PATH. |
| Double-clicking closes immediately | Open a terminal in the extracted folder and run `python demo.py`; read the displayed error. |
| Website not reachable | Start the correct profile. Use its printed 127.0.0.1 URL and port. Check that another app does not own that port. |
| Port busy | Choose another port, e.g. `python personal.py --port 8054`. Each profile keeps its own port. |
| Old first-launch/demo-marker error | Stop the old process and use the new launcher. It preserves an unmarked demo folder. Do not delete a folder containing real data. |
| Personal folder has no marker | It is preserved and refused. Back it up and move it aside before creating a clean profile; restore/import deliberately. |
| Missing packages | Run `install.py` from the project folder, then restart the personal launcher. |
| Scripts/styles look old | Ctrl+F5 after a source update. |
| AI cannot answer | Enable AI in personal Setup, restart, connect the provider, and check its allowance/authentication. No automatic paid fallback is used for the ChatGPT-plan connection. |
| No live quotes/rates | Enable public data, install optional packages and restart. Some sources can be unavailable or stale; inspect source dates. |
| No bank transactions | Import your own supported export in personal mode. Enabling public data does not log into your bank. |
| No investment-return metric | Check coverage and the complete cash-flow/valuation history. Unknown figures stay unknown. |
| Supabase errors | Use your own dedicated project, apply all five schema files, check URL and server secret key, and inspect Settings status. |
| Background start failed | Read the selected profile's `cache/server-error.log`. Do not post logs publicly without checking for private information. |

For development: `python demo.py --foreground --no-browser`; run tests with `python -m unittest discover -s tests`. The server binds only to loopback. This is a local single-user application, not an internet-hosted service.
