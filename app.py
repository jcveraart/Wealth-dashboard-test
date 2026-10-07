"""
the owner's wealth dashboard.

Run:      python app.py              (opens http://wealth.localhost)
Import:   python app.py import-tr Transaction_export.csv
Offline:  python app.py --offline    (no price fetching, uses last known prices)
"""
import csv
import json
import math
import shutil
import sys
import threading
import time
import webbrowser
from datetime import date, datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "portfolio.json"
SETTINGS = HERE / "settings.json"
BACKUPS = HERE / "backups"
CACHE = HERE / "cache"
PRICES = CACHE / "prices.json"
TICKERS = CACHE / "tickers.json"
PROXY = CACHE / "managed_proxy.json"
HISTORY = HERE / "history.csv"
HISTORY_FIELDS = ["date", "net_worth", "gross", "managed", "savings", "self_directed", "debt",
                  "etf", "stocks", "bonds", "other_inv", "cash", "invest_profit"]
ACCOUNT_HISTORY = HERE / "history_accounts.csv"  # value per account per day, for the account pages
PORT = 80
HOSTNAME = "wealth.localhost"  # browsers send any *.localhost name to this computer
TOLERANCE = 0.35  # a ticker is accepted if its EUR price is within 35% of the last known price
MAX_UPLOAD = 60 * 1024 * 1024

OFFLINE = False
lock = threading.Lock()
cfg_lock = threading.Lock()
wake = threading.Event()
status = {"last_refresh": None, "errors": [], "refreshing": False}


# ---------- config and cache ----------
def load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(path, data):
    import extras
    extras.atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False))


NOTES = HERE / "notes.md"
SPENDING = HERE / "spending.json"
# files covered by backups and Undo: (live file, backup prefix, suffix)
BACKED_UP = [(CONFIG, "portfolio", ".json"), (NOTES, "notes", ".md"), (SPENDING, "spending", ".json")]


def backup_now():
    """Copy the data files to backups/. Returns the backup id (used for Undo)."""
    import spending
    BACKUPS.mkdir(exist_ok=True)
    bid = f"{datetime.now():%Y%m%d-%H%M%S-%f}"
    with spending.lock:
        for live, prefix, suffix in BACKED_UP:
            if live.exists():
                shutil.copy2(live, BACKUPS / f"{prefix}-{bid}{suffix}")
    for _, prefix, suffix in BACKED_UP:
        for f in sorted(BACKUPS.glob(f"{prefix}-*{suffix}"))[:-100]:
            f.unlink()
    return bid


def save_config(cfg):
    """Save portfolio.json, keeping a copy of the previous version. Returns the backup id."""
    bid = backup_now()
    save(CONFIG, cfg)
    return bid


def check_config(cfg):
    """Raise if a changed portfolio.json would break the dashboard."""
    for k in ("accounts", "managed", "savings", "debts"):
        if k not in cfg:
            raise ValueError(f"'{k}' is missing")
    for a in cfg["accounts"]:
        for p in a["positions"]:
            if not isinstance(p.get("units"), (int, float)) or not isinstance(p.get("ref_price_eur"), (int, float)):
                raise ValueError(f"holding {p.get('name')} in {a.get('name')} needs units and ref_price_eur")
    compute_state(cfg, record=False)


progress = {}  # request id -> {"steps": [...], "done": bool}; what the AI is doing, polled by the page
progress_lock = threading.Lock()


def progress_start(pid):
    """Returns a function the agent calls with each new step."""
    if not pid:
        return None
    with progress_lock:
        progress[pid] = {"steps": [], "done": False}
        for old in list(progress)[:-20]:
            del progress[old]

    def step(text):
        with progress_lock:
            item = progress.get(pid)
            if item is not None and (not item["steps"] or item["steps"][-1] != text):
                item["steps"].append(text)
                del item["steps"][:-40]
    return step


def progress_done(pid):
    with progress_lock:
        if pid in progress:
            progress[pid]["done"] = True


def dedupe_config(cfg):
    """Safety net after AI edits: one row per account and date in the history, one row per account and year in the
    yearly flows (later values win), one entry per holding within an account, no repeated to dos."""
    hist = {}
    for r in cfg.get("account_history", []):
        hist[(r.get("date"), r.get("account"))] = r
    if "account_history" in cfg:
        cfg["account_history"] = sorted(hist.values(), key=lambda r: (str(r.get("date")), str(r.get("account"))))
    flows = {}
    for r in cfg.get("yearly_flows", []):
        k = (r.get("year"), r.get("account"))
        flows[k] = {**flows[k], **{f: v for f, v in r.items() if v is not None}} if k in flows else r
    if "yearly_flows" in cfg:
        cfg["yearly_flows"] = list(flows.values())
    for container in cfg["accounts"] + [cfg["managed"]]:
        if container.get("positions"):
            seen = {}
            for p in container["positions"]:
                seen[p.get("isin") or p["name"].strip().lower()] = p
            container["positions"] = list(seen.values())
    if "todos" in cfg:
        texts, todos = set(), []
        for t in cfg["todos"]:
            if t["text"].strip().lower() not in texts:
                texts.add(t["text"].strip().lower())
                todos.append(t)
        cfg["todos"] = todos
    return cfg


def agent_files():
    """The data files the AI may edit, as {name: text}."""
    import spending
    return {"portfolio.json": CONFIG.read_text(encoding="utf-8"), "notes.md": read_notes(),
            "spending_rules.json": spending.rules_file_text(), "spending_new.json": "[]\n",
            "spending_transactions.csv": spending.transactions_csv()}  # read only: changes to it are ignored


def commit_ai_changes(originals, changed):
    """Save what the AI changed, after checking it. Returns the backup id for Undo, or None if nothing changed."""
    import spending
    editable = ("portfolio.json", "notes.md", "spending_rules.json", "spending_new.json")
    changed = {k: v for k, v in changed.items() if k in editable and v.strip() != originals[k].strip()}
    if not changed:
        return None
    with cfg_lock:
        if CONFIG.read_text(encoding="utf-8") != originals["portfolio.json"]:
            raise ValueError("Your data changed while the AI was working. Nothing was saved; please try again.")
        try:
            cfg = json.loads(changed["portfolio.json"]) if "portfolio.json" in changed else None
            if cfg is not None:
                check_config(dedupe_config(cfg))
            if "spending_rules.json" in changed:
                json.loads(changed["spending_rules.json"])
            new_tx = spending_rows_from_ai(changed["spending_new.json"]) if "spending_new.json" in changed else []
        except Exception as e:
            raise ValueError(f"The AI made a change that would break the dashboard ({e}). Nothing was saved.")
        bid = backup_now()
        if cfg is not None:
            save(CONFIG, cfg)
        if "notes.md" in changed:
            NOTES.write_text(changed["notes.md"], encoding="utf-8")
        if "spending_rules.json" in changed:
            spending.apply_rules_file(changed["spending_rules.json"])
        if new_tx:
            for acc, rows in group_by(new_tx, "account").items():
                spending.import_transactions(f"from a document ({acc})", rows)
            spending.categorize_in_background(ai_claude_code(), api_key())
    wake.set()
    cloud_sync_soon()
    return bid


def group_by(rows, key):
    out = {}
    for r in rows:
        out.setdefault(r[key], []).append(r)
    return out


def spending_rows_from_ai(text):
    """Transactions the AI found in documents (spending_new.json), checked and normalised."""
    import spending
    rows = []
    for r in json.loads(text):
        d, amt = spending.parse_date(str(r.get("date", ""))), r.get("amount")
        if not d or not isinstance(amt, (int, float)):
            raise ValueError("every new transaction needs a date and a numeric amount")
        rows.append({"date": d, "amount": round(float(amt), 2), "description": str(r.get("description", ""))[:300],
                     "counterparty": str(r.get("counterparty", "")), "counter_iban": "",
                     "account": str(r.get("account") or "Other payment account")})
    return rows


def undo(bid):
    import spending
    if not any((BACKUPS / f"{prefix}-{bid}{suffix}").exists() for _, prefix, suffix in BACKED_UP):
        raise ValueError("That change can no longer be undone.")
    with cfg_lock, spending.lock:
        backup_now()
        for live, prefix, suffix in BACKED_UP:
            src = BACKUPS / f"{prefix}-{bid}{suffix}"
            if src.exists():
                shutil.copy2(src, live)
            elif live is SPENDING and live.exists():
                live.unlink()  # there was no spending data yet at that point
        spending.status["changed"] = time.time()
    wake.set()
    cloud_sync_soon()


INBOX = HERE / "inbox.json"
inbox_lock = threading.Lock()


def ask_jan(source, text):
    """Queue a question for the owner; it appears in Ask Claude. An unanswered question from the same source is replaced.

    Under the lock, because ten imports at once each read, change and write this file, and without it
    the last writer wins and the others' questions are never seen.
    """
    import uuid
    with inbox_lock:
        items = [i for i in load(INBOX, []) if not (i["source"] == source and not i["seen"])]
        items.append({"id": uuid.uuid4().hex[:12], "source": source, "text": text,
                      "created": datetime.now().isoformat(timespec="seconds"), "seen": False})
        save(INBOX, items[-50:])


def api_key():
    import os
    return load(SETTINGS, {}).get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY")


_claude_code = []


def ai_claude_code():
    """Cached lookup of the Claude Code program."""
    if not _claude_code:
        import ai
        _claude_code.append(ai.find_claude_code())
    return _claude_code[0]


def pid(p):
    """Stable id for a position: its ISIN, or its name when no ISIN is known."""
    return p.get("isin") or "n:" + p["name"].strip().lower()


# ---------- prices ----------
_fx = {}


def fx_to_eur(currency, yf):
    """Return a function that converts a price in `currency` to EUR."""
    if currency in (None, "", "EUR"):
        return lambda p: p
    divisor = 1.0
    if currency in ("GBp", "GBX"):
        currency, divisor = "GBP", 100.0
    if currency not in _fx or time.time() - _fx[currency][1] > 600:
        rate = yf.Ticker(f"EUR{currency}=X").fast_info["last_price"]
        _fx[currency] = (float(rate), time.time())
    rate = _fx[currency][0]
    return lambda p: p / divisor / rate


def quote(symbol, yf):
    fi = yf.Ticker(symbol).fast_info
    last, prev, cur = fi["last_price"], fi["previous_close"], fi["currency"]
    if last is None or (isinstance(last, float) and math.isnan(last)):
        raise ValueError("no price")
    conv = fx_to_eur(cur, yf)
    return {"price": conv(float(last)), "prev": conv(float(prev)) if prev else None, "currency": cur}


def resolve(pos, yf):
    """Find a Yahoo symbol for this position. A ticker written in portfolio.json is trusted, because it was put
    there on purpose; a symbol guessed from a search is only accepted when its price matches the last known one."""
    for s in pos.get("tickers", []):
        try:
            quote(s, yf)
            return s
        except Exception:
            continue
    tried = list(pos.get("tickers", []))
    for query in filter(None, [pos.get("isin"), pos["name"]]):
        try:
            for q in yf.Search(query, max_results=8, news_count=0, lists_count=0, raise_errors=False).quotes:
                s = q.get("symbol")
                if s and s not in tried:
                    tried.append(s)
        except Exception:
            pass
    ref = pos.get("ref_price_eur")
    for s in tried:
        try:
            q = quote(s, yf)
        except Exception:
            continue
        if ref and abs(q["price"] / ref - 1) <= TOLERANCE:
            return s
    return None


def refresh_prices(cfg):
    import yfinance as yf

    tickers = load(TICKERS, {})
    prices = load(PRICES, {})
    errors = []
    for pos in all_priced_positions(cfg):
        key = pid(pos)
        sym = tickers.get(key)
        if not sym:
            sym = resolve(pos, yf)
            if sym:
                tickers[key] = sym
                save(TICKERS, tickers)
            else:
                errors.append(f"{pos['name']}: no matching ticker found, using the last known price")
                continue
        try:
            q = quote(sym, yf)
            prices[key] = {**q, "symbol": sym, "time": datetime.now().isoformat(timespec="seconds")}
        except Exception as e:
            errors.append(f"{pos['name']} ({sym}): {e}")
    save(PRICES, prices)
    if not cfg["managed"].get("positions"):
        update_proxy(cfg, yf, errors)
    with lock:
        status["errors"] = errors
        status["last_refresh"] = datetime.now().isoformat(timespec="seconds")


def update_proxy(cfg, yf, errors):
    """Managed account estimate: move the last real value with a proxy ETF mix."""
    m = cfg["managed"]
    proxy = load(PROXY, {})
    key = f"{m['value_date']}|" + ",".join(f"{p['symbol']}:{p['weight']}" for p in m["proxy"])
    if proxy.get("key") != key:
        base = {}
        d = datetime.strptime(m["value_date"], "%Y-%m-%d").date()
        for p in m["proxy"]:
            try:
                h = yf.Ticker(p["symbol"]).history(start=d - timedelta(days=7), end=d + timedelta(days=1))
                base[p["symbol"]] = float(h["Close"].iloc[-1])
            except Exception as e:
                errors.append(f"Managed proxy {p['symbol']}: {e}")
        proxy = {"key": key, "base": base, "now": {}}
    for p in m["proxy"]:
        try:
            proxy["now"][p["symbol"]] = float(yf.Ticker(p["symbol"]).fast_info["last_price"])
        except Exception as e:
            errors.append(f"Managed proxy {p['symbol']}: {e}")
    save(PROXY, proxy)


def price_loop(minutes):
    while True:
        with lock:
            status["refreshing"] = True
        try:
            refresh_prices(load(CONFIG, None))
        except Exception as e:
            with lock:
                status["errors"] = [f"Refresh failed: {e}"]
        with lock:
            status["refreshing"] = False
        if cloud_due():
            _quiet(cloud_sync)
        wake.wait(minutes * 60)
        wake.clear()


# ---------- calculations ----------
def all_priced_positions(cfg):
    seen = {}
    for p in [p for a in cfg["accounts"] for p in a["positions"]] + cfg["managed"].get("positions", []):
        if p.get("manual_price_eur") is None and pid(p) not in seen:
            seen[pid(p)] = p
    return list(seen.values())


def days_between(a, b):
    return (b - a).days


def price_position(p, account, prices):
    q = prices.get(pid(p))
    if p.get("manual_price_eur") is not None:
        px, prev, live, src = p["manual_price_eur"], p["manual_price_eur"], False, "manual"
    elif q:
        px, prev, live, src = q["price"], q.get("prev") or q["price"], True, q["symbol"]
    else:
        px, prev, live, src = p["ref_price_eur"], p["ref_price_eur"], False, "last known"
    value, prev_value = p["units"] * px, p["units"] * prev
    profit = value + p["net_cashflow_eur"] if p.get("net_cashflow_eur") is not None else None
    return {
        "name": p["name"], "isin": p.get("isin"), "account": account, "category": p.get("category", "Other"),
        "units": p["units"], "price": px, "value": value, "day_change": value - prev_value,
        "since_buy_pct": (value / p["cost_eur"] - 1) * 100 if p.get("cost_eur") else None,
        "cost": p.get("cost_eur"), "profit": profit, "live": live, "source": src,
        "maturity": p.get("maturity"), "price_time": q.get("time") if q and live else None,
        "region": p.get("region"), "sector": p.get("sector"), "currency": p.get("currency"), "trades": p.get("trades") or [],
        "net_cashflow": p.get("net_cashflow_eur"),
    }


def compute_state(cfg, record=True):
    prices = load(PRICES, {})
    today = date.today()
    out = {"accounts": [], "positions": [], "generated": datetime.now().isoformat(timespec="seconds")}
    total_invest_value = total_day = 0.0

    for acc in cfg["accounts"]:
        a_val = a_prev = 0.0
        a_profit = acc.get("profit_extra_eur", 0.0) + acc.get("closed_cashflow_eur", 0.0)
        for p in acc["positions"]:
            r = price_position(p, acc["name"], prices)
            out["positions"].append(r)
            if r["profit"] is not None:
                a_profit += r["profit"]
            a_val += r["value"]
            a_prev += r["value"] - r["day_change"]
        cash = acc.get("cash_eur", 0.0)
        out["accounts"].append({
            "name": acc["name"], "value": a_val, "cash": cash, "day_change": a_val - a_prev,
            "profit": a_profit if acc.get("track_profit", True) else None, "positions": len(acc["positions"]),
            "since": acc.get("since"), "note": acc.get("note", ""), "updated": acc.get("updated"), "source": acc.get("source"),
            "money_in": -sum(p.get("net_cashflow_eur") or 0 for p in acc["positions"]) - acc.get("closed_cashflow_eur", 0.0),
        })
        total_invest_value += a_val + cash
        total_day += a_val - a_prev

    # managed account: live positions when known, otherwise the proxy estimate
    m = cfg["managed"]
    m_day = 0.0
    if m.get("positions"):
        rows = [price_position(p, m["name"], prices) for p in m["positions"]]
        for r in rows:
            r["managed"] = True
        out["positions"] += rows
        managed_value = sum(r["value"] for r in rows) + m.get("cash_eur", 0.0)
        m_day = sum(r["day_change"] for r in rows)
        mode = "positions"
    else:
        proxy = load(PROXY, {})
        factor, mode = 1.0, "last value"
        if proxy.get("base") and proxy.get("now") and len(proxy["base"]) == len(m["proxy"]):
            try:
                factor = sum(p["weight"] * proxy["now"][p["symbol"]] / proxy["base"][p["symbol"]] for p in m["proxy"])
                mode = "proxy"
            except (KeyError, ZeroDivisionError):
                factor = 1.0
        managed_value = m["value_eur"] * factor
    out["managed"] = {
        "name": m["name"], "value": managed_value, "last_real_value": m["value_eur"], "last_real_date": m["value_date"],
        "mode": mode, "profit": m["profit_at_value_date_eur"] + managed_value - m["value_eur"],
        "start_value": m["start_value_eur"], "start_date": m["start_date"], "fees_paid": m["fees_paid_eur"],
        "cash": m.get("cash_eur", 0.0), "day_change": m_day, "proxy": m["proxy"],
        "positions": len(m.get("positions", [])),
    }
    total_day += m_day

    # savings with simple daily accrual
    savings = []
    for s in cfg["savings"]:
        snap = datetime.strptime(s["snapshot_date"], "%Y-%m-%d").date()
        accrued = s.get("accrued_at_snapshot_eur", 0.0) + s["principal_eur"] * (s.get("rate_pct") or 0) / 100 * max(0, days_between(snap, today)) / 365
        kind = invest_kind(s)
        savings.append({**s, "value": s["principal_eur"] + accrued, "accrued": accrued, "invest": bool(kind), "invest_unknown": kind is None,
                        "kind": account_kind(s)})
    savings_total = sum(s["value"] for s in savings)

    # debts grow with interest from the last snapshot, and shrink with the monthly payment when one is known
    debts = []
    for d in cfg["debts"]:
        snap = datetime.strptime(d["snapshot_date"], "%Y-%m-%d").date()
        debts.append({**d, "balance": debt_balance(d["balance_eur"], d.get("rate_pct") or 0, d.get("monthly_payment_eur") or 0,
                                                   max(0, days_between(snap, today)))})
    debt_total = sum(d["balance"] for d in debts if not d.get("expected_gift"))

    gross = total_invest_value + managed_value + savings_total
    kinds = {"etf": 0.0, "stocks": 0.0, "bonds": 0.0, "other_inv": 0.0}
    for p in out["positions"]:
        if not p.get("managed"):
            kinds[HISTORY_KIND.get(p["category"], "other_inv")] += p["value"]
    out["savings"] = savings
    out["debts"] = debts
    out["todos"] = cfg.get("todos", [])
    out["totals"] = {
        "self_directed": total_invest_value, "managed": managed_value, "savings": savings_total,
        "gross": gross, "debt": debt_total, "net_worth": gross - debt_total, "day_change": total_day,
        "investing_profit": sum(a["profit"] for a in out["accounts"] if a["profit"] is not None) + out["managed"]["profit"],
        **kinds, "cash": savings_total + sum(a["cash"] for a in out["accounts"]),
        # everything the owner counts as invested: broker accounts with their cash, the managed portfolio, and the
        # savings accounts and deposits he sees as investments
        "invested": sum(a["value"] + a["cash"] for a in out["accounts"]) + managed_value
                    + sum(x["value"] for x in savings if x["invest"]),
        "invested_savings": sum(x["value"] for x in savings if x["invest"]),
    }
    with lock:
        out["status"] = dict(status)
    out["status"]["live_positions"] = sum(1 for p in out["positions"] if p["live"])
    out["status"]["total_positions"] = len(out["positions"])
    out["status"]["has_api_key"] = bool(api_key())
    import spending
    out["status"]["spending"] = dict(spending.status)
    spending.on_unclear = ask_jan
    out["inbox"] = [i for i in load(INBOX, []) if not i["seen"]]
    out["status"]["ai_mode"] = "api" if api_key() else "claude_code" if ai_claude_code() else None
    conf = cloud_config()
    out["status"]["cloud"] = {"connected": bool(conf), "url": conf[0] if conf else "", **cloud_status}
    out["history"] = record_history(out["totals"], out) if record else []
    out["account_history"] = cfg.get("account_history", [])
    out["savings_plans"] = [{**x, "next": next_execution(x), "per_month": monthly_amount(x)} for x in cfg.get("savings_plans", [])]
    out["yearly_flows"] = cfg.get("yearly_flows", [])
    try:
        out["spend_month"] = monthly_spending()
    except Exception:
        out["spend_month"] = None
    out["advice"] = advice(out, cfg)
    out["advice_dismissed"] = cfg.get("advice_dismissed", [])
    for k, empty in (("profile", {}), ("goals", []), ("pots", []), ("targets", {}), ("tax", {}), ("advice_done", []), ("watchlist", [])):
        out[k] = cfg.get(k, empty)
    return out


PAYMENT_WORDS = ("current", "betaal", "payment", "checking", "lopende", "giro", "everyday", "girorekening")


def account_kind(s):
    """payment (day to day money), savings or deposit. the owner's own choice when he made one, otherwise a guess:
    a maturity date makes a deposit, a name like 'current account' or no interest at all makes a payment account."""
    if s.get("kind") in ("payment", "savings", "deposit"):
        return s["kind"]
    if s.get("maturity"):
        return "deposit"
    text = f"{s.get('name', '')} {s.get('bank', '')}".lower()
    if any(w in text for w in PAYMENT_WORDS) or (not s.get("rate_pct") and s.get("invest") is not True):
        return "payment"
    return "savings"


def invest_kind(s):
    """Does a savings account count as an investment? the owner's own choice when he made one. Otherwise a deposit with a
    maturity does, an account without interest (a current account) does not, and anything else is asked (None)."""
    if isinstance(s.get("invest"), bool):
        return s["invest"]
    if s.get("maturity"):
        return True
    if not s.get("rate_pct"):
        return False
    return None


def debt_balance(balance, rate_pct, payment, days):
    """Balance after `days`: monthly interest added and the monthly payment taken off, the rest of a month as interest only.
    Without a payment it grows with yearly interest, as before."""
    if not payment:
        return balance * (1 + rate_pct / 100) ** (days / 365)
    months, rest = divmod(days, 30.4375)
    r = rate_pct / 100 / 12
    for _ in range(int(months)):
        balance = max(0.0, balance * (1 + r) - payment)
        if balance == 0:
            return 0.0
    return balance * (1 + rate_pct / 100) ** (rest / 365)


def monthly_spending():
    """Average spending per month over the last six full months, from the payment accounts. None without data."""
    import spending
    d = spending.load()
    kinds = {c["id"]: c["kind"] for c in d["categories"]}
    this = date.today().isoformat()[:7]
    by = {}
    for t in d["transactions"]:
        if t.get("excluded") or t["date"][:7] >= this:
            continue
        for r in spending.parts(t):
            if kinds.get(r.get("category"), "expense" if r["amount"] < 0 else "income") == "expense":
                by[t["date"][:7]] = by.get(t["date"][:7], 0.0) - r["amount"]
    months = sorted(by)[-6:]
    return sum(by[m] for m in months) / len(months) if months else None


def advice(out, cfg):
    """Recommendations: rules on the numbers plus ones added in the chat, minus dismissed and done ones. Each has what
    it is worth a year (impact_eur, when it can be worked out), the effort, why it matters and where to act."""
    recs = []
    t, m = out["totals"], out["managed"]
    rates = [s["rate_pct"] for s in out["savings"] if s.get("rate_pct") and not s.get("maturity")]
    best = max(rates + [(cfg.get("profile") or {}).get("compare_rate_pct") or 0], default=0)
    spend = monthly_spending()
    for a in out["accounts"]:
        if a["cash"] < -1:
            recs.append({"topic": "investing", "id": f"debit:{a['name']}", "title": f"Clear the {fmt_eur(-a['cash'])} debit balance at {a['name']}",
                         "detail": "Negative cash is a loan from the broker and costs interest (around 7% at DEGIRO). "
                                   "Moving the amount from savings that earn less stops that.",
                         "why": "Borrowing at 7% while savings earn 2 to 3% costs you the difference every year.",
                         "impact_eur": -a["cash"] * (0.07 - best / 100), "effort": "5 minutes", "action": {"kind": "page", "page": "accounts"},
                         "todo": f"Clear the {fmt_eur(-a['cash'])} debit balance at {a['name']}"})
    if m["mode"] != "positions":
        recs.append({"topic": "investing", "id": "managed-import", "title": "Import the holdings of the managed portfolio",
                     "detail": f"Its {fmt_eur(m['value'])} is now an estimate based on the value of {m['last_real_date']}. "
                               "With the holdings imported (screenshots on the Import page) every fund is priced live.",
                     "why": "Estimates drift. With the real holdings, its value, costs and risk are exact.",
                     "impact_eur": None, "effort": "10 minutes", "action": {"kind": "page", "page": "import"},
                     "todo": "Import the holdings of the ABN AMRO managed portfolio"})
    years = max(0.5, (date.today() - datetime.strptime(m["start_date"], "%Y-%m-%d").date()).days / 365)
    per_year = m["fees_paid"] / years
    if m["value"] and per_year / m["value"] > 0.005:
        recs.append({"topic": "investing", "id": "managed-fees", "title": f"The managed portfolio costs about {fmt_eur(per_year)} a year",
                     "detail": f"That is roughly {per_year / m['value'] * 100:.1f}% of its value every year. A low cost index mix "
                               "costs around 0.2%. Ask ABN AMRO for the risk profile, the stock and bond split and the full fee "
                               "breakdown, and compare.",
                     "why": "Costs compound like returns do: over 20 years one percent a year takes roughly a fifth of the result.",
                     "impact_eur": per_year - m["value"] * 0.002, "effort": "an hour",
                     "action": {"kind": "chat", "text": "Compare my managed portfolio with a low cost index mix: costs, risk and what I would keep."},
                     "todo": "Ask ABN AMRO for the managed portfolio risk profile, split and fee breakdown"})
    for s in out["savings"]:
        if not s.get("rate_pct") and s["principal_eur"] > 1000 and "current" not in s["name"].lower():
            recs.append({"topic": "money", "id": f"rate:{s['name']}", "title": f"Set the interest rate of {s['name']}",
                         "detail": f"{fmt_eur(s['value'])} with no rate recorded, so its interest is not counted. "
                                   "If it pays little, a fixed deposit or a DUO repayment may earn more.",
                         "why": "Without the rate the app can't tell whether this money is working.",
                         "impact_eur": None, "effort": "2 minutes", "action": {"kind": "page", "page": "cash"},
                         "todo": f"Look up and set the interest rate of {s['name']}"})
        if s.get("maturity") and len(s["maturity"]) >= 7:
            mat = datetime.strptime(s["maturity"] if len(s["maturity"]) == 10 else s["maturity"][:7] + "-28", "%Y-%m-%d").date()
            if 0 <= (mat - date.today()).days <= 92:
                recs.append({"topic": "money", "id": f"maturity:{s['name']}:{s['maturity'][:7]}", "title": f"{s['name']} matures on {mat.day} {mat:%B}",
                             "detail": f"Decide where the {fmt_eur(s['value'])} goes next before it lands in the overnight account.",
                             "why": "Money that falls back into a low rate account earns little until you move it.",
                             "impact_eur": s["value"] * max(0.0, (s.get("rate_pct") or 0) - 0.5) / 100, "effort": "15 minutes",
                             "action": {"kind": "page", "page": "cash"}, "todo": f"Decide what to do with {s['name']} when it matures"})
    # money sitting in a current account beyond a couple of months of spending
    if spend and best:
        for s in out["savings"]:
            if not (s.get("rate_pct") or 0) < best - 1:
                continue
            if "current" in s["name"].lower() or not s.get("rate_pct"):
                idle = s["value"] - 2 * spend
                if idle > 1000:
                    recs.append({"id": f"idle:{s['name']}", "title": f"Move about {fmt_eur(idle)} from {s['name']} to savings",
                                 "detail": f"You keep {fmt_eur(s['value'])} there while you spend about {fmt_eur(spend)} a month. "
                                           f"Two months of spending is plenty for day to day; the rest could earn {best:.2f}%.",
                                 "why": "Cash above what you need for the month earns nothing in a current account.",
                                 "impact_eur": idle * (best - (s.get("rate_pct") or 0)) / 100, "effort": "5 minutes",
                                 "action": {"kind": "page", "page": "cash"}, "todo": f"Move {fmt_eur(idle)} from {s['name']} to savings"})
    # a buffer for surprises
    if spend:
        liquid = sum(s["value"] for s in out["savings"] if not s.get("maturity"))
        if liquid < 3 * spend:
            recs.append({"id": "emergency-fund", "title": f"Build a buffer of {fmt_eur(3 * spend)}",
                         "detail": f"Money you can reach today is {fmt_eur(liquid)}, about {liquid / spend:.1f} months of your spending. "
                                   "Three months is a common minimum.",
                         "why": "A buffer means a broken laptop or a gap between jobs never forces you to sell investments at a bad moment.",
                         "impact_eur": None, "effort": "a few months", "action": {"kind": "page", "page": "plan"}, "todo": f"Build a {fmt_eur(3 * spend)} buffer"})
    # expensive debt while savings earn less
    for d in out["debts"]:
        if d.get("expected_gift") or not d.get("rate_pct") or d["balance"] < 500:
            continue
        spare = t["savings"] - 3 * (spend or 0)
        if d["rate_pct"] > best + 0.75 and spare > 1000:
            amount = min(spare, d["balance"])
            recs.append({"id": f"repay:{d['name']}", "title": f"Repaying {fmt_eur(amount)} of {d['name']} saves about {fmt_eur(amount * (d['rate_pct'] - best) / 100)} a year",
                         "detail": f"It costs {d['rate_pct']:.2f}% while your best savings rate is {best:.2f}%.",
                         "why": "Paying off debt is a guaranteed return equal to its interest rate.",
                         "impact_eur": amount * (d["rate_pct"] - best) / 100, "effort": "15 minutes",
                         "action": {"kind": "chat", "text": f"Should I repay part of {d['name']} early? Walk me through it."},
                         "todo": f"Decide on repaying {d['name']} early", "topic": "money"})
    small = [p for p in out["positions"] if p["value"] < 250 and p["category"] != "Bond"]
    if len(small) >= 3:
        recs.append({"topic": "investing", "id": "small-positions", "title": f"{len(small)} holdings are worth less than €250",
                     "detail": ", ".join(sorted(p["name"] for p in small)) + ". Small positions add tracking work but "
                               "barely move your results.",
                     "why": "Fewer, larger positions are easier to follow and cheaper to rebalance.",
                     "impact_eur": None, "effort": "30 minutes", "action": {"kind": "page", "page": "holdings"},
                     "todo": "Consider tidying up very small positions"})
    seen = {}
    for p in out["positions"]:
        seen.setdefault(p.get("isin") or p["name"], []).append(p["account"])
    doubles = [(k, v) for k, v in seen.items() if len(v) > 1]
    if doubles:
        names = [next(p["name"] for p in out["positions"] if (p.get("isin") or p["name"]) == k) for k, _ in doubles]
        recs.append({"topic": "investing", "id": "same-holding-twice", "title": f"{len(doubles)} holdings sit in more than one account",
                     "detail": ", ".join(names) + ". Holding them in one place keeps things simpler and can save costs.",
                     "why": "Two accounts for the same fund means two sets of fees and more to keep track of.",
                     "impact_eur": None, "effort": "30 minutes", "action": {"kind": "page", "page": "holdings"}, "todo": None})
    gift = [d for d in out["debts"] if d.get("expected_gift")]
    if gift:
        recs.append({"topic": "money", "id": "duo-gift", "title": f"Check that DUO turns the {fmt_eur(gift[0]['balance'])} performance grant into a gift",
                     "detail": "DUO converts it in January for diplomas from the year before. If that already should "
                               "have happened, contact DUO.",
                     "why": "If the conversion is missed, the grant stays a loan.",
                     "impact_eur": None, "impact_once_eur": gift[0]["balance"], "effort": "15 minutes",
                     "action": {"kind": "page", "page": "cash"}, "todo": "Check the DUO prestatiebeurs conversion status"})
    if out["status"]["errors"]:
        recs.append({"topic": "investing", "id": "pricing", "title": f"{len(out['status']['errors'])} holdings have no live price",
                     "detail": "They use the last known price. See Settings for which ones.", "why": "Old prices make your net worth less accurate.",
                     "impact_eur": None, "effort": "5 minutes", "action": {"kind": "page", "page": "settings"}, "todo": None})
    recs += [{"todo": None, "impact_eur": None, "effort": None, **r, "custom": True} for r in cfg.get("advice_custom", [])]
    hidden = {d["id"] for d in cfg.get("advice_dismissed", [])} | {d["id"] for d in cfg.get("advice_done", [])}
    for r in recs:
        if r.get("impact_eur") is not None:
            r["impact_eur"] = round(max(0.0, r["impact_eur"]), 0)
    return [r for r in recs if r["id"] not in hidden]


def fmt_eur(x):
    return f"€{x:,.0f}"


HISTORY_KIND = {"Broad ETF": "etf", "Tech ETF": "etf", "Stock": "stocks", "Bond": "bonds", "Bond fund": "bonds"}


def record_history(t, state=None):
    rows = {}
    if HISTORY.exists():
        with HISTORY.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows[r["date"]] = r
    today = date.today().isoformat()
    rows[today] = {"date": today, **{k: f"{t[k if k != 'invest_profit' else 'investing_profit']:.2f}" for k in HISTORY_FIELDS[1:]}}
    with HISTORY.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HISTORY_FIELDS, extrasaction="ignore")
        w.writeheader()
        for k in sorted(rows):
            w.writerow(rows[k])
    if state:
        record_account_history(today, state)
    num = lambda v: float(v) if v not in (None, "") else None
    return [{"date": k, **{f: num(rows[k].get(f)) for f in HISTORY_FIELDS[1:]}} for k in sorted(rows)]


def record_account_history(today, state):
    """Today's value of every account, savings account and debt (one row each, the last write of the day wins)."""
    values = {a["name"]: a["value"] + a["cash"] for a in state["accounts"]}
    values[state["managed"]["name"]] = state["managed"]["value"]
    values.update({s["name"]: s["value"] for s in state["savings"]})
    values.update({d["name"]: -d["balance"] for d in state["debts"]})
    rows = []
    if ACCOUNT_HISTORY.exists():
        with ACCOUNT_HISTORY.open(encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r["date"] != today]
    rows += [{"date": today, "account": k, "value": f"{v:.2f}"} for k, v in values.items()]
    with ACCOUNT_HISTORY.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "account", "value"])
        w.writeheader()
        w.writerows(rows)


def account_history(name):
    """[{date, value}] for one account from the daily file; with name "*" a dict of every account."""
    if not ACCOUNT_HISTORY.exists():
        return {} if name == "*" else []
    with ACCOUNT_HISTORY.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if name == "*":
        out = {}
        for r in rows:
            out.setdefault(r["account"], []).append({"date": r["date"], "value": float(r["value"])})
        return out
    return [{"date": r["date"], "value": float(r["value"])} for r in rows if r["account"] == name]


# ---------- edits from the website ----------
def num_or_none(x):
    if x in (None, ""):
        return None
    return float(x)


EDITABLE = {
    "savings": {"name": str, "bank": str, "principal_eur": float, "rate_pct": num_or_none,
                "accrued_at_snapshot_eur": float, "snapshot_date": str, "maturity": lambda x: x or None,
                "invest": lambda x: None if x in (None, "", "auto") else bool(x) if not isinstance(x, str) else x == "true",
                "kind": lambda x: x if x in ("payment", "savings", "deposit") else None},
    "debts": {"name": str, "balance_eur": float, "rate_pct": num_or_none, "snapshot_date": str,
              "expected_gift": bool, "monthly_payment_eur": num_or_none},
    "todos": {"text": str, "done": bool},
    "advice_dismissed": {"id": str, "title": str, "reason": str},
    "savings_plans": {"account": str, "instrument": str, "isin": str, "amount_eur": float, "frequency": str,
                      "day": lambda x: int(x) if x not in (None, "") else None, "active": bool},
    "managed": {"value_eur": float, "value_date": str, "profit_at_value_date_eur": float, "fees_paid_eur": float,
                "cash_eur": float},
    "account": {"cash_eur": float, "profit_extra_eur": float},
    "goals": {"name": str, "target_eur": float, "date": str, "source": str, "pot": str, "saved_eur": num_or_none},
    "pots": {"name": str, "target_eur": num_or_none, "saved_eur": float, "account": str},
    "advice_done": {"id": str, "title": str, "impact_eur": num_or_none, "date": str},
    "profile": {"birth_year": lambda x: int(x) if x not in (None, "") else None, "household": str, "risk": str,
                "goals_text": str, "home_country": str, "benchmark": str, "compare_rate_pct": num_or_none,
                "retire_age": lambda x: int(x) if x not in (None, "") else None,
                "horizon_years": num_or_none, "buffer_months": num_or_none, "monthly_invest_eur": num_or_none},
    "position": {"region": str, "sector": str, "currency": str, "industry": str},
    "watchlist": {"name": str, "symbol": lambda x: str(x).strip().upper(), "added": str, "buy_below": num_or_none, "note": str},
}
LISTS = ("savings", "debts", "todos", "advice_dismissed", "savings_plans", "goals", "pots", "advice_done", "watchlist")


def clean(section, fields):
    spec = EDITABLE[section]
    return {k: spec[k](v) for k, v in fields.items() if k in spec}


def apply_edit(cfg, e):
    section, action = e["section"], e.get("action", "update")
    if section in LISTS:
        items = cfg.setdefault(section, [])
        if action == "add":
            new = clean(section, e["fields"])
            if section == "savings":
                new = {"name": "", "bank": "", "principal_eur": 0.0, "rate_pct": None, "accrued_at_snapshot_eur": 0.0,
                       "snapshot_date": date.today().isoformat(), "maturity": None, **new}
            elif section == "debts":
                new = {"name": "", "balance_eur": 0.0, "rate_pct": 0.0, "expected_gift": False,
                       "snapshot_date": date.today().isoformat(), **new}
            elif section == "savings_plans":
                new = {"account": "Trade Republic", "instrument": "", "amount_eur": 0.0, "frequency": "monthly", "day": 1,
                       "active": True, "since": date.today().isoformat()[:7], "source": "manual", **new}
            elif section == "advice_dismissed":
                new = {"id": "", "title": "", "reason": "", **new}
            elif section == "goals":
                new = {"name": "", "target_eur": 0.0, "date": "", "source": "net_worth", **new}
            elif section == "pots":
                new = {"name": "", "target_eur": None, "saved_eur": 0.0, "account": "", **new}
            elif section == "watchlist":
                new = {"name": "", "symbol": "", "added": date.today().isoformat(), "buy_below": None, "note": "", **new}
                if not new["symbol"]:
                    raise ValueError("A watchlist item needs its ticker")
                if any(w.get("symbol") == new["symbol"] for w in items):
                    raise ValueError(f"{new['symbol']} is already on your watchlist")
            elif section == "advice_done":
                new = {"id": "", "title": "", "impact_eur": None, "date": date.today().isoformat(), **new}
            else:
                new = {"text": "", "done": False, **new}
            items.append(new)
        elif action == "delete":
            items.pop(int(e["index"]))
        else:
            items[int(e["index"])].update(clean(section, e["fields"]))
            if section == "savings" and items[int(e["index"])].get("invest", 0) is None:
                items[int(e["index"])].pop("invest")  # back to the automatic choice
            if section == "savings_plans":
                items[int(e["index"])]["source"] = "manual"
    elif section == "managed":
        cfg["managed"].update(clean("managed", e["fields"]))
    elif section == "account":
        acc = next(a for a in cfg["accounts"] if a["name"] == e["name"])
        acc.update(clean("account", e["fields"]))
    elif section == "profile":
        cfg.setdefault("profile", {}).update(clean("profile", e["fields"]))
    elif section == "targets":  # {position id: percent}, None removes
        t = cfg.setdefault("targets", {})
        for k, v in e["fields"].items():
            if v in (None, ""):
                t.pop(k, None)
            else:
                t[k] = float(v)
    elif section == "tax":  # free form: parameters per year, partner, checklist ticks
        cfg.setdefault("tax", {}).update({k: v for k, v in e["fields"].items() if k in ("params", "partner", "checklist")})
    elif section == "position":
        every = [p for a in cfg["accounts"] for p in a["positions"]] + cfg["managed"].get("positions", [])
        for p in every:
            if pid(p) == e["id"]:
                p.update(clean("position", e["fields"]))
    else:
        raise ValueError("unknown section")


def apply_import(cfg, imp):
    """Apply a reviewed screenshot import. Returns a list of plain sentences describing the changes."""
    done = []
    as_of = imp.get("as_of") or date.today().isoformat()
    h = imp.get("holdings")
    if h and h.get("items"):
        done += apply_holdings(cfg, h, as_of, imp.get("account_totals"))
    for b in imp.get("balances", []):
        if not b.get("apply"):
            continue
        fields = {"principal_eur": float(b["amount_eur"]), "snapshot_date": as_of, "accrued_at_snapshot_eur": 0.0}
        if b.get("rate_pct") is not None:
            fields["rate_pct"] = float(b["rate_pct"])
        if b.get("maturity"):
            fields["maturity"] = b["maturity"]
        i = int(b.get("match_index", -1))
        if i >= 0:
            cfg["savings"][i].update(fields)
            done.append(f"Updated {cfg['savings'][i]['name']} to €{fields['principal_eur']:,.2f}.")
        else:
            cfg["savings"].append({"name": b["name"], "bank": b.get("bank", ""), "rate_pct": None, "maturity": None, **fields})
            done.append(f"Added savings account {b['name']}.")
    for d in imp.get("debts", []):
        if not d.get("apply"):
            continue
        fields = {"balance_eur": float(d["balance_eur"]), "snapshot_date": as_of}
        if d.get("rate_pct") is not None:
            fields["rate_pct"] = float(d["rate_pct"])
        i = int(d.get("match_index", -1))
        if i >= 0:
            cfg["debts"][i].update(fields)
            done.append(f"Updated {cfg['debts'][i]['name']} to €{fields['balance_eur']:,.2f}.")
        else:
            cfg["debts"].append({"name": d["name"], "rate_pct": 0.0, "expected_gift": False, **fields})
            done.append(f"Added debt {d['name']}.")
    t = imp.get("account_totals")
    if t and t.get("apply") and not (h and h.get("items") and h.get("target") == "__managed__"):
        done += apply_managed_totals(cfg, t, as_of, None)
    return done


def apply_managed_totals(cfg, t, as_of, positions_total):
    m = cfg["managed"]
    value = num_or_none(t.get("value_eur")) if t else None
    if value is None:
        value = positions_total
    if value is None:
        return []
    result = num_or_none(t.get("total_result_eur")) if t else None
    m["profit_at_value_date_eur"] = round(result if result is not None else m["profit_at_value_date_eur"] + value - m["value_eur"], 2)
    m["value_eur"] = round(value, 2)
    m["value_date"] = as_of
    fees = num_or_none(t.get("fees_eur")) if t else None
    if fees is not None:
        m["fees_paid_eur"] = fees
    return [f"Managed portfolio value set to €{value:,.2f} on {as_of}."]


def apply_holdings(cfg, h, as_of, totals):
    target = h["target"]
    if target == "__managed__":
        container, label = cfg["managed"], cfg["managed"]["name"]
        container.setdefault("positions", [])
    elif target.startswith("__new__:"):
        name = target[8:].strip() or "New account"
        container = {"name": name, "since": as_of[:7], "cash_eur": 0.0, "closed_cashflow_eur": 0.0,
                     "profit_extra_eur": 0.0, "note": "Added from a screenshot import.", "positions": []}
        cfg["accounts"].append(container)
        label = name
    else:
        container = next(a for a in cfg["accounts"] if a["name"] == target)
        label = target
    existing = container["positions"]
    by_isin = {p["isin"]: p for p in existing if p.get("isin")}
    by_name = {p["name"].strip().lower(): p for p in existing}
    out = [] if h.get("mode") == "replace" else list(existing)
    added = updated = 0
    positions_total = 0.0
    for it in h["items"]:
        units = num_or_none(it.get("units"))
        if not units:
            continue
        value = num_or_none(it.get("value_eur"))
        price = num_or_none(it.get("price"))
        if value is not None:
            ref = value / units
        elif price is not None and (it.get("price_currency") or "EUR").upper() == "EUR":
            ref = price
        else:
            continue
        positions_total += units * ref
        cost = num_or_none(it.get("cost_eur"))
        isin = (it.get("isin") or "").strip().upper() or None
        hint = (it.get("ticker_hint") or "").strip() or None
        match = (by_isin.get(isin) if isin else None) or by_name.get(it["name"].strip().lower())
        if match:
            match["units"] = round(units, 6)
            match["ref_price_eur"] = round(ref, 4)
            if isin and not match.get("isin"):
                match["isin"] = isin
            if cost is not None:
                old_cost = match.get("cost_eur") or 0.0
                if match.get("net_cashflow_eur") is not None:
                    match["net_cashflow_eur"] = round(match["net_cashflow_eur"] - (cost - old_cost), 2)
                else:
                    match["net_cashflow_eur"] = round(-cost, 2)
                match["cost_eur"] = round(cost, 2)
            if hint and hint not in match.setdefault("tickers", []):
                match["tickers"].insert(0, hint)
            if match.get("manual_price_eur") is not None:
                match["manual_price_eur"] = round(ref, 4)
            if it.get("maturity"):
                match["maturity"] = it["maturity"]
            if match not in out:
                out.append(match)
            updated += 1
        else:
            new = {"name": it["name"].strip(), "isin": isin, "category": it.get("category") or "Other",
                   "units": round(units, 6), "cost_eur": round(cost, 2) if cost is not None else None,
                   "net_cashflow_eur": round(-cost, 2) if cost is not None else None,
                   "ref_price_eur": round(ref, 4), "tickers": [hint] if hint else []}
            if not isin:
                new.pop("isin")
            if new["category"] == "Bond" and not hint:
                new["manual_price_eur"] = round(ref, 4)
            if it.get("maturity"):
                new["maturity"] = it["maturity"]
            out.append(new)
            added += 1
    container["positions"] = sorted(out, key=lambda x: x["name"].lower())
    cash = num_or_none(h.get("cash_eur"))
    if cash is not None:
        container["cash_eur"] = cash
    done = [f"{label}: {updated} holdings updated, {added} added."]
    if target == "__managed__":
        # the snapshot value must match the recorded holdings, so profit keeps counting from the right base
        total = sum(p["units"] * (p.get("manual_price_eur") or p["ref_price_eur"]) for p in container["positions"])
        total += container.get("cash_eur") or 0.0
        done += apply_managed_totals(cfg, totals if totals and totals.get("apply") else None, as_of, total)
    return done


# ---------- Trade Republic import ----------
def num(x):
    return float(x) if x not in (None, "", "nan") else 0.0


TR_COLUMNS = {"datetime", "type", "symbol", "shares", "amount", "fee", "tax"}


def tr_rows(text):
    """Rows of a Trade Republic transaction export, or None if the text is not one."""
    import io
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if not TR_COLUMNS.issubset(set(reader.fieldnames or [])):
        return None
    return list(reader)


def tr_positions_from_rows(rows):
    """Units, average cost and net cash flow per ISIN from a Trade Republic transaction export."""
    rows = sorted(rows, key=lambda r: r["datetime"])
    pos = {}
    for r in rows:
        isin, t = r.get("symbol"), r["type"]
        if not isin:
            continue
        p = pos.setdefault(isin, {"isin": isin, "name": r.get("name") or isin, "asset_class": r.get("asset_class"),
                                  "units": 0.0, "cost": 0.0, "cash": 0.0, "last_price": None, "trades": []})
        if r.get("name"):
            p["name"] = r["name"]
        sh, amt = num(r["shares"]), num(r["amount"]) + num(r["fee"]) + num(r["tax"])
        if r.get("price"):
            p["last_price"] = num(r["price"])
        if t in ("BUY", "SELL", "DIVIDEND", "DISTRIBUTION"):
            # kept per holding, for the buys on its price chart and its dividends
            p["trades"].append({"date": r["datetime"][:10], "type": t.lower(), "units": round(sh, 6), "amount": round(amt, 2),
                                "price": num(r["price"]) if r.get("price") else None})
        if t == "BUY":
            p["units"] += sh
            p["cost"] += -amt
            p["cash"] += amt
        elif t == "SELL":
            if p["units"] > 0:
                p["cost"] *= max(0.0, 1 - (-sh) / p["units"])
            p["units"] += sh
            p["cash"] += amt
        elif t in ("BONUS_ISSUE", "BONUS_ISSUE_CANCELLED"):
            p["units"] += sh
        elif t == "FINAL_MATURITY" and r["category"] == "CORPORATE_ACTION":
            p["units"] += sh
            p["cost"] = 0.0
        elif t in ("DIVIDEND", "DISTRIBUTION", "INTEREST_PAYMENT") or (t == "FINAL_MATURITY" and r["category"] == "CASH"):
            p["cash"] += amt
    for p in pos.values():
        if abs(p["units"]) < 1e-6:
            p["units"] = 0.0
    return pos


def import_tr(csv_path):
    cfg = load(CONFIG, None)
    rows = tr_rows(Path(csv_path).read_text(encoding="utf-8"))
    if rows is None:
        sys.exit("This is not a Trade Republic transaction export.")
    for line in import_tr_into(cfg, rows):
        print(line)
    save_config(cfg)


def import_tr_into(cfg, rows):
    acc = next(a for a in cfg["accounts"] if a["name"] == "Trade Republic")
    old = {p["isin"]: p for p in acc["positions"]}
    pos = tr_positions_from_rows(rows)
    new_positions, closed = [], 0.0
    for isin, p in pos.items():
        if p["units"] <= 0:
            closed += p["cash"]
            continue
        o = old.get(isin, {})
        ref = o.get("ref_price_eur") or (p["last_price"] or 1.0)
        entry = {
            "name": o.get("name", p["name"]), "isin": isin, "category": o.get("category", default_category(p["asset_class"])),
            "units": round(p["units"], 6), "cost_eur": round(p["cost"], 2), "net_cashflow_eur": round(p["cash"], 2),
            "ref_price_eur": ref, "tickers": o.get("tickers", []), "trades": p["trades"][-200:],
        }
        for k in ("region", "sector", "currency"):
            if o.get(k):
                entry[k] = o[k]
        if o.get("maturity"):
            entry["maturity"] = o["maturity"]
        if p["asset_class"] == "BOND":
            entry["manual_price_eur"] = o.get("manual_price_eur", p["last_price"])
        new_positions.append(entry)
    acc["positions"] = sorted(new_positions, key=lambda x: x["name"])
    acc["closed_cashflow_eur"] = round(closed, 2)
    acc["updated"], acc["source"] = date.today().isoformat(), "Trade Republic transaction export"
    added = [p["name"] for p in new_positions if p["isin"] not in old]
    gone = [o["name"] for i, o in old.items() if i not in {p["isin"] for p in new_positions}]
    out = [f"Imported {len(new_positions)} Trade Republic positions."]
    if added:
        out.append("New: " + ", ".join(added) + ".")
    if gone:
        out.append("Closed: " + ", ".join(gone) + ".")
    plans = detect_savings_plans(rows, {p["isin"]: p["name"] for p in new_positions})
    if plans is not None:
        manual = [x for x in cfg.get("savings_plans", []) if x.get("source") != "detected"]
        plans = [x for x in plans if x["isin"] not in {m.get("isin") for m in manual}]  # the owner's own edits win
        cfg["savings_plans"] = manual + plans
        running = [x for x in plans if x["active"]]
        if plans:
            out.append(f"Savings plans: {len(running)} running (€{sum(monthly_amount(x) for x in running):,.0f} a month)"
                       + (f", {len(plans) - len(running)} stopped." if len(plans) > len(running) else "."))
    return out


FREQ_DAYS = {"weekly": 7, "biweekly": 14, "monthly": 30.4, "quarterly": 91.3}


def monthly_amount(plan):
    return plan["amount_eur"] * 30.4 / FREQ_DAYS.get(plan.get("frequency"), 30.4)


def detect_savings_plans(rows, names):
    """Recurring buys in a Trade Republic export: same ISIN, same amount, regular interval."""
    from collections import Counter, defaultdict
    buys = defaultdict(list)
    for r in rows:
        if r.get("type") == "BUY" and r.get("symbol"):
            d = (r.get("datetime") or "")[:10]
            amt = round(abs(num(r["amount"])), 2)
            if d and amt:
                buys[(r["symbol"], amt)].append(d)
    if not buys:
        return None
    last_in_file = max(r["datetime"][:10] for r in rows if r.get("datetime"))
    plans = []
    for (isin, amt), dates in buys.items():
        dates = sorted(set(dates))
        if len(dates) < 3:
            continue
        gaps = sorted((date.fromisoformat(b) - date.fromisoformat(a)).days for a, b in zip(dates, dates[1:]))
        gap = gaps[len(gaps) // 2]
        freq = min(FREQ_DAYS, key=lambda f: abs(FREQ_DAYS[f] - gap))
        if abs(FREQ_DAYS[freq] - gap) > FREQ_DAYS[freq] * 0.35:
            continue
        idle = (date.fromisoformat(last_in_file) - date.fromisoformat(dates[-1])).days
        plans.append({"account": "Trade Republic", "instrument": names.get(isin) or next(
                          (r.get("name") for r in rows if r.get("symbol") == isin and r.get("name")), isin),
                      "isin": isin, "amount_eur": amt, "frequency": freq,
                      "day": Counter(int(d[8:10]) for d in dates).most_common(1)[0][0] if freq in ("monthly", "quarterly") else None,
                      "active": idle <= FREQ_DAYS[freq] * 1.5 + 5, "since": dates[0][:7], "last_execution": dates[-1],
                      "executions": len(dates), "source": "detected"})
    return sorted(plans, key=lambda x: (not x["active"], -monthly_amount(x)))


def next_execution(plan, today=None):
    today = today or date.today()
    if not plan.get("active"):
        return None
    if plan.get("frequency") in ("monthly", "quarterly") and plan.get("day"):
        step = 1 if plan["frequency"] == "monthly" else 3
        y, m = today.year, today.month
        for _ in range(13):
            import calendar
            d = date(y, m, min(plan["day"], calendar.monthrange(y, m)[1]))
            if d > today and (step == 1 or not plan.get("last_execution") or
                              (d.year * 12 + d.month - int(plan["last_execution"][:4]) * 12 - int(plan["last_execution"][5:7])) % 3 == 0):
                return d.isoformat()
            m += 1
            if m > 12:
                y, m = y + 1, 1
        return None
    if plan.get("last_execution"):
        d = date.fromisoformat(plan["last_execution"])
        while d <= today:
            d += timedelta(days=round(FREQ_DAYS.get(plan["frequency"], 30.4)))
        return d.isoformat()
    return None


def default_category(asset_class):
    return {"FUND": "Broad ETF", "STOCK": "Stock", "BOND": "Bond", "CRYPTO": "Crypto"}.get(asset_class, "Other")


# ---------- web server ----------
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(HERE / "web"), **k)

    def log_message(self, *a):
        pass

    def send_json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return True

    def send_download(self, body, name, ctype):
        body = body.encode() if isinstance(body, str) else body
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return True

    def end_headers(self):
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_GET(self):
        if self.path.startswith("/api/state"):
            return self.send_json(compute_state(load(CONFIG, None)))
        from urllib.parse import parse_qs, urlparse
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            got = self.extra_get(u.path, q)
        except Exception as e:
            return self.send_json({"error": friendly_error(e)}, 500)
        if got is not None:
            return got
        if self.path.startswith("/api/progress"):
            from urllib.parse import parse_qs, urlparse
            pid = (parse_qs(urlparse(self.path).query).get("id") or [""])[0]
            with progress_lock:
                return self.send_json(progress.get(pid) or {"steps": [], "done": False})
        if self.path.startswith("/api/spending"):
            import spending
            with spending.lock:
                d = spending.load()
            return self.send_json({**d, "status": dict(spending.status)})
        return super().do_GET()

    def extra_get(self, path, q):
        """The read endpoints of the newer pages. Returns None for paths that are not theirs."""
        import extras
        if path == "/api/ui":
            return self.send_json(extras.ui_state())
        if path == "/api/chats":
            return self.send_json(extras.chats_list(q.get("q", "")))
        if path == "/api/chats/get":
            return self.send_json(extras.chat_get(q.get("id", "")) or {"error": "That conversation is gone."})
        if path == "/api/briefing":
            state = compute_state(load(CONFIG, None))
            return self.send_json(extras.briefing(state, extras.ui_state()["prefs"], ai_claude_code(), api_key()))
        if path == "/api/prices/history":
            cfg = load(CONFIG, None)
            held = {pid(p) for p in all_priced_positions(cfg)}
            tickers = {k: v for k, v in load(TICKERS, {}).items() if k in held}
            return self.send_json(extras.price_history(cfg, tickers, OFFLINE))
        if path == "/api/opportunities":
            return self.send_json(opportunities())
        if path == "/api/economy":
            import public
            return self.send_json(public.economy(OFFLINE))
        if path == "/api/fundamentals":
            return self.send_json(fundamentals_now())
        if path == "/api/local-ai":
            import local
            return self.send_json(local.status())
        if path == "/api/news":
            cfg = load(CONFIG, None)
            held = {pid(p): p["name"] for p in all_priced_positions(cfg)}
            tickers = {k: v for k, v in load(TICKERS, {}).items() if k in held}
            return self.send_json(extras.news(tickers, held, OFFLINE))
        if path == "/api/holding-info":
            return self.send_json(extras.read(extras.INFO, {}).get(q.get("id", "")) or {})
        if path == "/api/imports":
            return self.send_json(extras.imports_list())
        if path == "/api/account-history":
            return self.send_json(account_history(q.get("name", "")))
        if path == "/api/ai-usage":
            return self.send_json(load(CACHE / "ai_usage.json", {}))
        if path == "/api/export":
            import spending
            what, stamp = q.get("what", "all"), date.today().isoformat()
            if what == "transactions":
                return self.send_download(spending.transactions_csv(), f"transactions-{stamp}.csv", "text/csv; charset=utf-8")
            if what == "holdings":
                import io
                out = io.StringIO()
                w = csv.writer(out)
                w.writerow(["account", "name", "isin", "type", "units", "price_eur", "value_eur", "cost_eur", "profit_eur"])
                for p in compute_state(load(CONFIG, None), record=False)["positions"]:
                    w.writerow([p["account"], p["name"], p.get("isin") or "", p["category"], p["units"], round(p["price"], 4),
                                round(p["value"], 2), p.get("cost") or "", "" if p.get("profit") is None else round(p["profit"], 2)])
                return self.send_download(out.getvalue(), f"holdings-{stamp}.csv", "text/csv; charset=utf-8")
            bundle = {"exported": datetime.now().isoformat(timespec="seconds"), "portfolio": load(CONFIG, None),
                      "spending": spending.load(), "notes": read_notes(), "interface": extras.ui_state(),
                      "chats": extras.read(extras.CHATS, []),
                      "history": HISTORY.read_text(encoding="utf-8") if HISTORY.exists() else ""}
            return self.send_download(json.dumps(bundle, ensure_ascii=False, indent=1), f"wealth-export-{stamp}.json",
                                      "application/json")
        return None

    def extra_post(self, body):
        """The write endpoints of the newer pages. Returns None for paths that are not theirs."""
        import extras
        if self.path == "/api/ui":
            return self.send_json(extras.ui_update(body))
        if self.path == "/api/chats/save":
            return self.send_json({"id": extras.chat_save(body)})
        if self.path == "/api/chats/delete":
            extras.chat_delete(body.get("id"))
            return self.send_json({"ok": True})
        if self.path == "/api/briefing":
            state = compute_state(load(CONFIG, None))
            return self.send_json(extras.briefing(state, extras.ui_state()["prefs"], ai_claude_code(), api_key(), force=True))
        if self.path == "/api/opportunities/refresh":
            if not (ai_claude_code() or api_key()):
                return self.send_json({"error": "Install Claude Code or add an API key in Settings first."}, 400)
            return self.send_json(opportunities(force=True))
        if self.path == "/api/news/picks":
            exe, key = ai_claude_code(), api_key()
            if not (exe or key):
                return self.send_json({"error": "Install Claude Code or add an API key in Settings first."}, 400)
            cfg = load(CONFIG, None)
            held = {pid(p): p["name"] for p in all_priced_positions(cfg)}
            tickers = {k: v for k, v in load(TICKERS, {}).items() if k in held}
            items = extras.news(tickers, held, OFFLINE)["items"]
            if not items:
                return self.send_json({"error": "No news yet. Try again in a minute."}, 400)
            return self.send_json(extras.news_picks(items, sorted(set(held.values())), exe, key))
        if self.path in ("/api/holding-info", "/api/classify"):
            exe, key = ai_claude_code(), api_key()
            if not (exe or key):
                return self.send_json({"error": "Install Claude Code or add an API key in Settings first."}, 400)
            cfg = load(CONFIG, None)
            if self.path == "/api/holding-info":
                info = extras.holding_info(cfg, body["id"], pid, exe, key, force=bool(body.get("force")))
                found = {body["id"]: {k: info[k] for k in ("region", "sector", "currency") if info.get(k)}}
            else:
                info, found = None, extras.classify(cfg, pid, exe, key)
            if found:
                with cfg_lock:
                    cfg = load(CONFIG, None)
                    for p in [p for a in cfg["accounts"] for p in a["positions"]] + cfg["managed"].get("positions", []):
                        for k, v in found.get(pid(p), {}).items():
                            p.setdefault(k, v)
                    save_config(cfg)
            return self.send_json(info if info is not None else {"done": len(found)})
        return None

    def do_POST(self):
        # only accept requests from this computer's own pages
        origin = self.headers.get("Origin", "")
        host = origin.split("//")[-1].split(":")[0]
        if origin and host not in ("localhost", "127.0.0.1", HOSTNAME):
            return self.send_json({"error": "forbidden"}, 403)
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD:
            return self.send_json({"error": "Upload too large. Use fewer or smaller screenshots."}, 413)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self.send_json({"error": "bad request"}, 400)
        try:
            got = self.extra_post(body)
            if got is not None:
                return got
            if self.path == "/api/refresh":
                wake.set()
                return self.send_json({"ok": True})
            if self.path == "/api/settings":
                s = load(SETTINGS, {})
                if "anthropic_api_key" in body:
                    s["anthropic_api_key"] = body["anthropic_api_key"].strip()
                if "contact_email" in body:
                    s["contact_email"] = str(body["contact_email"]).strip()[:120]
                save(SETTINGS, s)
                return self.send_json({"ok": True, "has_api_key": bool(api_key())})
            if self.path == "/api/import":
                pid = str(body.get("progress_id") or "")
                try:
                    return self.send_json(import_files(body.get("files") or [], body.get("note", ""), progress_start(pid)))
                finally:
                    progress_done(pid)
            if self.path == "/api/spending/categorize":
                import spending
                spending.set_category(body["ids"], body.get("category"), bool(body.get("learn")))
                cloud_sync_soon()
                return self.send_json({"ok": True})
            if self.path == "/api/spending/edit":
                import spending
                bid = backup_now() if body.get("action") in ("category-delete", "import-delete", "rule-delete") else None
                note_tx = spending.edit(body)
                if note_tx:
                    spending.note_in_background(note_tx, ai_claude_code(), api_key())
                cloud_sync_soon()
                return self.send_json({"ok": True, "undo": bid})
            if self.path == "/api/spending/places":
                import spending
                if body.get("again"):
                    # an answer of "cannot tell" is remembered so the same payment is not asked about
                    # twice; this forgets those, for when a later import gives the line better text
                    with spending.lock:
                        d = spending.load()
                        for t in d["transactions"]:
                            if t.get("country_source") == "ai" and not t.get("country"):
                                t["country_source"] = None
                        spending.save(d)
                if not spending.places_in_background(ai_claude_code(), api_key()):
                    return self.send_json({"error": "Install Claude Code or add an API key in Settings first."}, 400)
                return self.send_json({"ok": True})
            if self.path == "/api/spending/recategorize":
                import spending
                with spending.lock:
                    d = spending.load()
                    for t in d["transactions"]:
                        if t.get("category_source") == "unsure":
                            t["category_source"] = None
                    spending.save(d)
                spending.categorize_in_background(ai_claude_code(), api_key())
                return self.send_json({"ok": True})
            if self.path == "/api/inbox/seen":
                ids = set(body.get("ids", []))
                with inbox_lock:
                    items = load(INBOX, [])
                    for i in items:
                        if i["id"] in ids:
                            i["seen"] = True
                    save(INBOX, items)
                return self.send_json({"ok": True})
            if self.path == "/api/undo":
                undo(body["id"])
                return self.send_json({"ok": True})
            if self.path == "/api/edit":
                with cfg_lock:
                    cfg = load(CONFIG, None)
                    apply_edit(cfg, body)
                    bid = save_config(cfg)
                wake.set()
                cloud_sync_soon()
                return self.send_json({"ok": True, "undo": bid})
            if self.path == "/api/cloud":
                import cloud
                s = load(SETTINGS, {})
                url, key = body.get("url", "").strip(), body.get("key", "").strip()
                if not url and not key:
                    s.pop("supabase_url", None)
                    s.pop("supabase_key", None)
                    save(SETTINGS, s)
                    return self.send_json({"ok": True, "done": "Supabase disconnected."})
                if not url.startswith("https://"):
                    return self.send_json({"error": "The project URL should look like https://abcd.supabase.co"}, 400)
                key = key or s.get("supabase_key", "")
                cloud.test(url, key)
                s["supabase_url"], s["supabase_key"] = url, key
                save(SETTINGS, s)
                return self.send_json({"ok": True, "done": cloud_sync()})
            if self.path == "/api/chat":
                import ai
                msgs = [{"role": m["role"], "content": str(m["content"])} for m in body.get("messages", [])
                        if m.get("role") in ("user", "assistant") and m.get("content")]
                if not msgs or msgs[-1]["role"] != "user":
                    return self.send_json({"error": "No question."}, 400)
                msgs = msgs[-30:]
                if msgs[0]["role"] != "user":
                    # the conversation can start with Claude's own question after an import
                    msgs.insert(0, {"role": "user", "content": "(the owner opened the chat. You asked the next question yourself after an import.)"})
                key, exe = api_key(), ai_claude_code()
                attached = body.get("files") or []
                pid = str(body.get("progress_id") or "")
                step = progress_start(pid)
                try:
                    if attached and exe:
                        # attachments: bank exports are imported exactly first, the rest goes to Claude with the message
                        bid = backup_now()
                        if step:
                            step("Reading your files")
                        parts, rest = route_known_files(attached)
                        names = ", ".join(f.get("name") or "file" for f in attached)
                        note = f"\n\n(the owner attached: {names}." + (" The app already imported these exactly: " + " ".join(parts)
                                                                   if parts else "") + ")"
                        msgs[-1] = {"role": "user", "content": msgs[-1]["content"] + note}
                        files = agent_files()
                        reply, changed = ai.agent(msgs, full_system(compute_state(json.loads(files["portfolio.json"]))), exe,
                                                  files, uploads=rest or None, on_step=step)
                        changed_any = commit_ai_changes(files, changed) or parts
                        if changed_any:
                            import extras
                            extras.log_import(bid, attached, reply, "chat")
                        wake.set()
                        cloud_sync_soon()
                        return self.send_json({"reply": ("\n\n".join(parts) + "\n\n" if parts else "") + reply,
                                               "undo": bid if changed_any else None})
                    files = agent_files()
                    system = full_system(compute_state(json.loads(files["portfolio.json"])))
                    question = msgs[-1]["content"]
                    level = ai.pick_level(question, body.get("effort") or "auto")
                    # the data files and tools only when something has to change, or when the owner asked Claude to dig deep;
                    # a plain answer from the snapshot costs a fraction of that
                    if exe and (ai.wants_change(question) or ai.needs_detail(question) or level == "deep"):
                        reply, changed = ai.agent(msgs, system, exe, files, on_step=step, level=level)
                        return self.send_json({"reply": reply, "undo": commit_ai_changes(files, changed), "level": level})
                    if exe or key:
                        if step:
                            step("Thinking about your numbers")
                        return self.send_json({"reply": ai.chat(msgs, system, api_key=None if exe else key, exe=exe, level=level), "level": level})
                    return self.send_json({"error": "No AI available. Install Claude Code or add an API key in Settings."}, 400)
                finally:
                    progress_done(pid)
            if self.path == "/api/cloud/sync":
                return self.send_json({"ok": True, "done": cloud_sync()})
        except Exception as e:
            return self.send_json({"error": friendly_error(e)}, 500)
        return self.send_json({"error": "not found"}, 404)


def read_notes():
    return NOTES.read_text(encoding="utf-8") if NOTES.exists() else ""


_industry_day = {}


def industries_for_stocks():
    """Give every single stock an industry from Damodaran's list, once a day at most, in the background."""
    import public
    names = set(public.industries(OFFLINE))
    exe, key = ai_claude_code(), api_key()
    cfg = load(CONFIG, None)
    every = [p for a in cfg["accounts"] for p in a["positions"]] + cfg["managed"].get("positions", [])
    todo = {pid(p): {"name": p["name"], "isin": p.get("isin")} for p in every if p.get("category") == "Stock" and not p.get("industry")}
    import local
    if not names or not todo or _industry_day.get("d") == date.today() or not (exe or key or local.wanted("classify")):
        return
    _industry_day["d"] = date.today()

    def work():
        import extras
        try:
            found = extras.assign_industries(todo, names, exe, key)
        except Exception:
            return
        with cfg_lock:
            c = load(CONFIG, None)
            for p in [p for a in c["accounts"] for p in a["positions"]] + c["managed"].get("positions", []):
                if found.get(pid(p)):
                    p.setdefault("industry", found[pid(p)])
            save_config(c)
    threading.Thread(target=work, daemon=True).start()


def research():
    """The quiet research tools: your stocks against their industry, and what well known investors did."""
    import public
    inds = public.industries(OFFLINE)
    industries_for_stocks()
    figs = fundamentals_now()
    cfg = load(CONFIG, None)
    stocks = []
    for p in [p for a in cfg["accounts"] for p in a["positions"]] + cfg["managed"].get("positions", []):
        if p.get("category") != "Stock" or any(x["id"] == pid(p) for x in stocks):
            continue
        ind = inds.get(p.get("industry") or "")
        stocks.append({"id": pid(p), "name": p["name"], "industry": p.get("industry"), "pe": (figs.get(pid(p)) or {}).get("pe"),
                       "industry_pe": ind["pe"] if ind else None, "industry_growth_pct": ind.get("growth_pct") if ind else None})
    held = [p["name"] for p in [p for a in cfg["accounts"] for p in a["positions"]]] + [w.get("name", "") for w in cfg.get("watchlist", [])]
    funds = public.funds(OFFLINE)
    for f in funds:
        for m in f["moves"]:
            mine = next((h for h in held if public.same_company(h, m["name"])), None)
            m["yours"] = bool(mine)
            if mine:
                m["holding"] = mine
    return {"stocks": stocks, "funds": funds}


def opportunities(force=False):
    """Signals from the numbers, Claude's weekly ideas and the watchlist, for the Advice page."""
    import ideas
    import public
    state = compute_state(load(CONFIG, None), record=False)
    tickers = load(TICKERS, {})
    wl = state.get("watchlist") or []
    ideas.fetch_watchlist(wl, OFFLINE)
    sys_text = full_system(state)
    snapshot = sys_text[sys_text.find("# Background notes"):] if "# Background notes" in sys_text else sys_text
    try:
        figs = fundamentals_now()
    except Exception:
        figs = {}
    try:
        res = research()
    except Exception:
        res = {"stocks": [], "funds": []}
    return {"research": res, "signals": ideas.signals(state, tickers, public.economy(OFFLINE), figs, res),
            "ideas": ideas.claude_ideas(snapshot, ai_claude_code(), api_key(), force=force),
            "watchlist": ideas.watchlist(wl)}


def fundamentals_now(cfg=None):
    """Company figures for the single stocks you hold, with today's valuation."""
    import public
    cfg = cfg or load(CONFIG, None)
    tick = load(TICKERS, {})
    stocks = {}
    for p in [p for a in cfg["accounts"] for p in a["positions"]] + cfg["managed"].get("positions", []):
        if p.get("category") == "Stock":
            stocks[pid(p)] = (p["name"], ([tick[pid(p)]] if tick.get(pid(p)) else []) + p.get("tickers", []))
    for w in cfg.get("watchlist", []):  # watched US listed companies too, for their insider trades
        if w.get("symbol"):
            stocks["w:" + w["symbol"]] = (w.get("name") or w["symbol"], [w["symbol"]])
    figs = public.fundamentals(stocks, OFFLINE)
    prices = {pid(p): p.get("ref_price_eur") for p in [p for a in cfg["accounts"] for p in a["positions"]]}
    for k, v in load(PRICES, {}).items():
        if k in prices and v.get("price"):
            prices[k] = v["price"]
    usd = public.economy(OFFLINE).get("usd")
    out = {k: public.with_valuation(v, prices.get(k), usd) for k, v in figs.items() if not k.startswith("_")}
    if figs.get("_error"):
        out["_error"] = figs["_error"]
    # each stock's industry and what that industry trades at (Damodaran), also for stocks without SEC figures
    inds = public.industries(OFFLINE)
    for p in [p for a in cfg["accounts"] for p in a["positions"]] + cfg["managed"].get("positions", []):
        ind = inds.get(p.get("industry") or "")
        if ind:
            out.setdefault(pid(p), {}).update(industry=p["industry"], industry_pe=ind["pe"], industry_growth_pct=ind.get("growth_pct"))
    return out


def full_system(state):
    """Chat instructions with the live snapshot, background notes and the spending summary."""
    import ai
    import spending
    import extras
    text = ai.chat_system(state, read_notes())
    import public
    econ = public.economy(OFFLINE)
    bits = [f"ECB deposit rate {econ['ecb_rate']:.2f}%" if econ.get("ecb_rate") is not None else "",
            f"inflation in the Netherlands {econ['inflation_nl']:.1f}% over the last 12 months ({econ['inflation_nl_month']})" if econ.get("inflation_nl") is not None else "",
            f"euro area inflation {econ['inflation_ea']:.1f}%" if econ.get("inflation_ea") is not None else "",
            f"AAA euro government bonds pay {econ['bond2']:.2f}% for 2 years and {econ['bond10']:.2f}% for 10 years" if econ.get("bond2") is not None and econ.get("bond10") is not None else "",
            f"average rate {econ['savings_nl_area']} banks pay households on savings {econ['savings_nl']:.2f}% ({econ['savings_nl_month']})" if econ.get("savings_nl") is not None else ""]
    if any(bits):
        text += "\n\n# Economy (ECB data)\n" + "; ".join(b for b in bits if b) + "."
    try:
        figs = fundamentals_now()
    except Exception:
        figs = {}
    if figs:
        names = {pid(p): p["name"] for p in state["positions"]}
        lines = []
        for k, f in figs.items():
            parts = [f"revenue {f['currency']} {f['revenue'] / 1e9:.1f}bn" if f.get("revenue") else "",
                     f"growth {f['revenue_growth_pct']:+.0f}% on the year before" if f.get("revenue_growth_pct") is not None else "",
                     f"3 year growth {f['revenue_cagr3_pct']:+.0f}% a year" if f.get("revenue_cagr3_pct") is not None else "",
                     f"net margin {f['net_margin_pct']:.0f}%" if f.get("net_margin_pct") is not None else "",
                     f"price to earnings {f['pe']}" if f.get("pe") else "", f"price to book {f['pb']}" if f.get("pb") else "",
                     f"insiders bought ${f['insiders']['buys_usd']:,.0f} and sold ${f['insiders']['sells_usd']:,.0f} in the last {f['insiders']['days']} days" if f.get("insiders") else "",
                     f"its industry ({f['industry']}, US companies) trades at a price to earnings of {f['industry_pe']}" if f.get("industry_pe") else ""]
            lines.append(f"- {names.get(k, k)} (fiscal {f.get('year')}): " + ", ".join(x for x in parts if x))
        text += "\n\n# Company figures from annual reports filed with the SEC\n" + "\n".join(lines)
    for f in public.funds(OFFLINE):
        moves = [m for m in f["moves"] if m["move"] in ("new", "added")][:4]
        if moves:
            text += (f"\n\n# {f['name']} last quarter (to {f.get('quarter')}, SEC 13F): " if "# Well known" not in text else f"\n- {f['name']} (to {f.get('quarter')}): ")
            text += "; ".join(f"{'bought' if m['move'] == 'new' else 'added to'} {m['name']}" for m in moves)
    headlines = extras.news_text()
    if headlines:
        text += "\n\n# Recent news about the owner's investments (headline, source, link)\n" + headlines
    summary = spending.summary_text()
    return text + ("\n\n# Spending (payment accounts)\n" + summary if summary else "")


# a zip of a year of statements is normal; these keep one careless drop from filling the disk
ARCHIVE_MAX_FILES = 400
ARCHIVE_MAX_BYTES = 300 * 1024 * 1024


def expand_archives(files, depth=2):
    """Replace every zip with the files inside it, so a whole export folder can be imported at once.

    Members keep their own file name, so the Trade Republic and bank readers recognise them exactly
    as they would if the owner had dropped them in loose. Folders, hidden files and the metadata macOS
    adds are left out. Nested zips are opened too, but only a couple of levels deep.
    """
    import base64
    import io
    import mimetypes
    import zipfile
    from posixpath import basename

    out, seen_bytes = [], 0
    for f in files:
        name = f.get("name") or "file"
        if depth <= 0 or not name.lower().endswith(".zip"):
            out.append(f)
            continue
        try:
            zf = zipfile.ZipFile(io.BytesIO(base64.b64decode(f["data"])))
        except (zipfile.BadZipFile, ValueError):
            raise ValueError(f"{name} is not a zip file I can open.")
        inner = []
        for m in zf.infolist():
            short = basename(m.filename)
            if m.is_dir() or not short or short.startswith(".") or m.filename.startswith("__MACOSX/"):
                continue
            seen_bytes += m.file_size
            if len(inner) >= ARCHIVE_MAX_FILES or seen_bytes > ARCHIVE_MAX_BYTES:
                raise ValueError(f"{name} holds too much to import in one go. Unpack it and import the parts you need.")
            try:
                data = zf.read(m)
            except RuntimeError:
                raise ValueError(f"{name} is password protected, so its files cannot be read.")
            # only images and PDFs are read by their type; everything else goes by file name, and
            # Windows cheerfully calls a .csv an Excel file, so don't pass that guess on
            kind = mimetypes.guess_type(short)[0] or ""
            inner.append({"name": short, "media_type": kind if kind.startswith("image/") or kind == "application/pdf" else "",
                          "data": base64.b64encode(data).decode()})
        if not inner:
            raise ValueError(f"{name} has no files in it.")
        out.extend(expand_archives(inner, depth - 1))
    return out


def route_known_files(files):
    """Files code can read exactly (Trade Republic export, bank exports) are imported here. Returns (summaries, rest).
    A zip is opened first, so what comes out of it is routed the same way as anything else."""
    import base64
    import ai
    import spending
    parts, rest, spent = [], [], False
    for f in expand_archives(files):
        name, mt = f.get("name") or "file", f.get("media_type") or ""
        raw = base64.b64decode(f["data"])
        if mt.startswith("image/") or name.lower().endswith(".pdf"):
            rest.append(f)
            continue
        # a Trade Republic export: trades are calculated exactly, card payments go to Spending
        rows = tr_rows(ai.decode_text(raw)) if name.lower().endswith((".csv", ".txt")) else None
        if rows:
            with cfg_lock:
                cfg = load(CONFIG, None)
                done = import_tr_into(cfg, rows)
                save(CONFIG, cfg)
            parts.append("**Trade Republic investments** (calculated exactly):\n" + "\n".join("- " + x for x in done))
            card = spending.trade_republic_rows(rows)
            if card:
                r = spending.import_transactions(name, card)
                parts.append(spending_line(r))
                spent = True
            continue
        try:
            bank = spending.parse_known(name, raw)
        except Exception:
            bank = None
        if bank and len(bank) >= 3:
            r = spending.import_transactions(name, bank)
            parts.append(spending_line(r) + update_current_account(r))
            spent = True
            continue
        rest.append(f)
    if spent:
        spending.categorize_in_background(ai_claude_code(), api_key())
    return parts, rest


def import_files(files, note, step=None):
    """Import uploaded files straight into the data. One Undo reverts the whole import. Returns {"summary", "undo"}."""
    import base64
    import ai
    import spending

    if not files:
        raise ValueError("No files.")
    bid = backup_now()
    if step:
        step("Reading your files")
    parts, rest = route_known_files(files)
    if rest:
        exe, key = ai_claude_code(), api_key()
        if exe:
            files_now = agent_files()
            msg = "Import the uploaded files into my data." + (f" My note about them: {note}" if note else "")
            reply, changed = ai.agent([{"role": "user", "content": msg}],
                                      full_system(compute_state(json.loads(files_now["portfolio.json"]), record=False)),
                                      exe, files_now, uploads=rest, on_step=step, kind="import")
            commit_ai_changes(files_now, changed)
            reply, questions = ai.split_questions(reply)
            if questions:
                ask_jan("import", "About the files you just imported, a few things weren't clear:\n\n" + questions
                        + "\n\nAnswer here and I'll update your data.")
                reply += "\n\n**Claude has a question about this import.** Answer it in Ask Claude."
            parts.append(reply)
        elif key:
            draft = ai.extract(rest, note, load(CONFIG, None), key)
            with cfg_lock:
                cfg = load(CONFIG, None)
                done = apply_import(cfg, auto_import_payload(cfg, draft))
                save(CONFIG, cfg)
            parts.append(draft["summary"] + "\n\nChanges:\n" + "\n".join("- " + d for d in done))
        else:
            raise ValueError("No AI available. Install Claude Code or add an API key in Settings.")
    wake.set()
    cloud_sync_soon()
    import extras
    extras.log_import(bid, files, "\n\n".join(parts))
    return {"summary": "\n\n".join(parts), "undo": bid}


def spending_line(r):
    import spending
    label = spending.load()["accounts"].get(r["account"], {}).get("name", r["account"])
    extra = ""
    if r["account"] == spending.PAYPAL_ACCOUNT:
        extra = (" These are what you actually bought through PayPal. For the months they cover, the PayPal debits on "
                 "your bank account now count as moving money to PayPal instead of as spending, so nothing is counted twice.")
    return (f"**Spending, {label}** ({r['from']} to {r['to']}): {r['added']} new transactions"
            + (f", {r['duplicates']} already imported and skipped" if r["duplicates"] else "") + "."
            + extra + " "
            + ("Categorising the rest with AI in the background; check the To review tab on the Spending page." if r["pending"]
               else "All categorised."))


def update_current_account(r):
    """An ABN AMRO export tells the closing balance: keep the current account in Savings up to date."""
    import spending
    if r.get("end_balance") is None:
        return ""
    label = spending.account_label(r["account"])
    with cfg_lock:
        cfg = load(CONFIG, None)
        current = [s for s in cfg["savings"] if "current" in s["name"].lower()]
        if len(current) != 1 or not label.startswith(current[0].get("bank", "")[:3]) or r["end_date"] < current[0]["snapshot_date"]:
            return ""
        current[0].update(principal_eur=round(r["end_balance"], 2), snapshot_date=r["end_date"], accrued_at_snapshot_eur=0.0)
        save(CONFIG, cfg)
    return f" Current account balance updated to €{r['end_balance']:,.2f} ({r['end_date']})."


def auto_import_payload(cfg, d):
    """Turn an extracted draft into an import without a review step (API key mode)."""
    names = [a["name"] for a in cfg["accounts"]]
    target = d.get("holdings_target_guess") or ""
    if target not in names and target != "__managed__":
        target = "__new__:" + (d.get("institution") or "New account")

    def match(items, name):
        n = name.lower()
        return next((i for i, x in enumerate(items) if x["name"].lower() in n or n in x["name"].lower()), -1)

    as_of = d.get("as_of_date") or ""
    return {"as_of": as_of if len(as_of) == 10 else None,
            "holdings": {"target": target, "mode": "merge", "cash_eur": d.get("cash_eur"), "items": d.get("holdings", [])},
            "account_totals": {**(d.get("account_totals") or {}), "apply": target == "__managed__"},
            "balances": [{**b, "apply": True, "match_index": match(cfg["savings"], b["name"])} for b in d.get("balances", [])],
            "debts": [{**x, "apply": True, "match_index": match(cfg["debts"], x["name"])} for x in d.get("debts", [])]}


# ---------- Supabase copy ----------
cloud_lock = threading.Lock()
cloud_status = {"last_sync": None, "error": None}
CLOUD_EVERY = 15 * 60


def cloud_config():
    s = load(SETTINGS, {})
    return (s.get("supabase_url"), s.get("supabase_key")) if s.get("supabase_url") and s.get("supabase_key") else None


def cloud_sync():
    """Copy everything to Supabase now. Returns a sentence for the user; raises on failure."""
    import cloud
    conf = cloud_config()
    if not conf:
        raise ValueError("Supabase is not connected.")
    with cloud_lock:
        cfg = load(CONFIG, None)
        state = compute_state(cfg)
        with HISTORY.open(encoding="utf-8") as f:
            history = list(csv.DictReader(f))
        try:
            n = cloud.sync(conf[0], conf[1], state, cfg, history)
            import spending
            changed = spending.status["changed"]
            if changed != cloud_status.get("spending_synced"):
                with spending.lock:
                    d = spending.load()
                cloud.sync_spending(conf[0], conf[1], d)
                cloud_status["spending_synced"] = changed
        except Exception as e:
            cloud_status["error"] = str(e)
            raise
        cloud_status.update(last_sync=datetime.now().isoformat(timespec="seconds"), error=None)
    return (f"Synced {n['institutions']} institutions, {n['accounts']} accounts, {n['positions']} holdings "
            f"and {n['instruments']} instruments to Supabase.")


def cloud_sync_soon():
    if cloud_config():
        threading.Thread(target=lambda: _quiet(cloud_sync), daemon=True).start()


def _quiet(fn):
    try:
        fn()
    except Exception:
        pass


def cloud_due():
    last = cloud_status["last_sync"]
    return cloud_config() and (not last or (datetime.now() - datetime.fromisoformat(last)).total_seconds() > CLOUD_EVERY)


def friendly_error(e):
    name = type(e).__name__
    if name == "AuthenticationError":
        return "The API key was rejected. Check it in Settings."
    if name == "RateLimitError":
        return "Too many requests to the AI right now. Wait a minute and try again."
    if name == "APIConnectionError":
        return "Could not reach the AI service. Check your internet connection."
    if name == "BadRequestError":
        return f"The AI request was rejected: {getattr(e, 'message', e)}"
    return str(e) or name


def main():
    args = sys.argv[1:]
    if args[:1] == ["import-tr"]:
        import_tr(args[1])
        return
    cfg = load(CONFIG, None)
    if cfg is None:
        sys.exit("portfolio.json not found or invalid.")
    import spending
    spending.on_unclear = ask_jan
    global OFFLINE
    OFFLINE = "--offline" in args
    if "--offline" not in args:
        try:
            import yfinance  # noqa: F401
        except ImportError:
            sys.exit("yfinance is not installed. Run: pip install -r requirements.txt")
        threading.Thread(target=price_loop, args=(cfg.get("refresh_minutes", 5),), daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://{HOSTNAME}" + ("" if PORT == 80 else f":{PORT}")
    print(f"Dashboard running at {url}  (Ctrl+C to stop)")
    if "--no-browser" not in args:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
