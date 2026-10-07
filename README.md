# Wealth Dashboard Demo

The full local wealth dashboard, with invented data you can safely share. Includes the latest Investments overhaul: asset-class filters, account drill-downs, performance charts and a grouped holdings list. Overview, spending, savings, debt, history, planning, taxes, advice and imports use the same application as the personal version.

Every balance, payment, account, profile, conversation and market price in `demo_data/` is synthetic. There are no real bank exports, credentials, personal notes or original Git history in this repository.

## Run it

Install **Python 3.9 or newer**. The default demo needs no third-party packages, account, API key or Supabase project.

- **Windows:** double-click `start-demo-windows.bat`.
- **macOS:** run `python3 demo.py` in this folder, or `sh start-demo-mac.command`.
- **Linux:** run `python3 demo.py`, or `sh start-demo-linux.sh`.
- **Any terminal:** `python demo.py`.

Open **http://127.0.0.1:8051**. The demo uses a different port from the personal dashboard. Keep the terminal running; press Ctrl+C there to stop it.

On first launch, the demo generates dated sample data from a fixed seed in `.demo-runtime/`. It copies the same application code into that isolated folder. Your demo edits are kept between launches. Restart after changing code to load the changes.

If a first launch was interrupted, retry the start file. The launcher preserves the incomplete folder in `backups/` and finishes a fresh setup automatically. It builds new data in a temporary folder before putting the runtime into place.

If port 8051 is busy: `python demo.py --port 8052`.

## What's included

- Two broker accounts, a crypto account and a managed portfolio, with ETFs, stocks, bonds and crypto.
- Current and travel accounts, emergency savings, a fixed deposit and two loans.
- Five years of daily wealth, account and synthetic investment price history.
- Two years of fictional income and payments, subscriptions, refunds, transfers, Tikkies, split payments, trips, tags and an item to review.
- Goals, pots, recurring investment plans, an example watchlist, sample conversation and pinned introduction.
- The original Supabase schema and optional synthetic database seed.

The demo is clearly labelled. News and fresh AI answers require their own services; the default demo does not pretend to generate them. Public-data values are also synthetic in offline mode. Default launch disables automatic use of any Claude Code installation, environment API key, Ollama server or Supabase connection.

## Reset the demo

Stop it, then run `python demo.py --reset`. This backs up the existing demo data into the ignored `backups/` folder before regenerating sample data. The original templates in `demo_data/` remain unchanged.

To regenerate the versioned fixtures intentionally: `python generate_demo.py --output demo_data --date 2026-10-07`.

## Optional connections

Install the original optional dependencies with `python -m pip install -r requirements.txt`.

- **Yahoo prices:** `python demo.py --live-prices` uses genuine quotes for the invented holdings.
- **AI / Ollama / Supabase:** `python demo.py --connect-services` allows your own separate setup. Use Settings in the demo; credentials stay in `.demo-runtime/settings.json`, excluded from Git. AI replies and AI imports need Claude Code or an Anthropic API key. Known bank CSV formats still import without AI.
- **Supabase:** use a **new, empty demo project**. Run `supabase-schema.sql`, `supabase-history.sql`, `supabase-spending.sql` and `supabase-plans.sql` in that order. Run `python build_supabase_seed.py` locally, then paste the generated `cache/demo-supabase-seed.sql` into that project's SQL Editor. The first schema resets the dashboard tables, so do not run it against a database containing real data. Row-level security remains enabled; use your own project URL and server secret key locally. The seed includes no credentials.

## Working on it

Tests: `python -m unittest discover tests`. Additional demo checks cover sample-data generation, isolation and offline APIs. The application guide is in `docs/APP_GUIDE.md`; the data format is documented in `DATA.md`.

Keep `.demo-runtime/`, root data files, exports, backups and credentials out of Git. Only the generated fixtures in `demo_data/` should be shared. Versioned transactions are split by month and CSV history by quarter, with indexes in `demo_data/manifest.json`; SQL seed chunks are in `demo_data/sql/`. The runtime regenerates the normal single-file data layout automatically.
