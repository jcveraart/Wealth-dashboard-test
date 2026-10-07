"""Copies the dashboard data to your own Supabase database (PostgREST over HTTPS, no extra packages).

Tree: institutions -> accounts -> holdings -> instruments, plus daily history per level.
Rows are upserted, never deleted; anything no longer present is marked active = false so history stays intact.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone

TYPE_OF = {"Broad ETF": "ETFs", "Tech ETF": "ETFs", "Stock": "Stocks", "Bond": "Bonds", "Bond fund": "Bonds"}
BANK_OF = {"Savings platform": "Savings platform"}


class CloudError(Exception):
    pass


def _request(url, key, method, path, body=None, prefer=None):
    headers = {"apikey": key, "Content-Type": "application/json"}
    if not key.startswith("sb_"):
        headers["Authorization"] = "Bearer " + key  # legacy service_role JWT keys
    if prefer:
        headers["Prefer"] = prefer
    data = json.dumps(body, default=str).encode() if body is not None else None
    req = urllib.request.Request(url.rstrip("/") + "/rest/v1/" + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        if "PGRST205" in detail or "does not exist" in detail or "Could not find" in detail:
            raise CloudError("The tables don't exist yet. Run supabase-schema.sql in the Supabase SQL editor.")
        if e.code in (401, 403):
            raise CloudError("Supabase rejected the key. Use the secret key (or service_role key), not the publishable one.")
        raise CloudError(f"Supabase error {e.code}: {detail[:300]}")
    except urllib.error.URLError as e:
        raise CloudError(f"Could not reach Supabase: {e.reason}")


def test(url, key):
    _request(url, key, "GET", "institutions?select=id&limit=1")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "x"


def _upsert(url, key, table, rows, conflict="id"):
    if rows:
        _request(url, key, "POST", f"{table}?on_conflict={conflict}", rows,
                 prefer="resolution=merge-duplicates,return=minimal")


def _retire(url, key, table, now):
    """Mark rows that were not part of this sync as inactive."""
    _request(url, key, "PATCH", f"{table}?active=is.true&updated_at=lt.{urllib.parse.quote(now)}", {"active": False},
             prefer="return=minimal")


def sync_spending(url, key, d):
    """Replace the spending tables with the current spending.json."""
    accounts = [{"id": k, "name": v.get("name", k)} for k, v in d["accounts"].items()]
    cats = [{"id": c["id"], "name": c["name"], "grp": c["group"], "kind": c["kind"]} for c in d["categories"]]
    rules = [{"id": i, "match": r["match"], "type": r.get("type"), "category_id": r["category"], "label": r.get("label")}
             for i, r in enumerate(d["rules"])]
    txs = [{"id": t["id"], "date": t["date"], "amount": t["amount"], "description": t["description"], "merchant": t["merchant"],
            "account_id": t["account"], "category_id": t.get("category"), "category_source": t.get("category_source"),
            "note": t.get("note", ""), "linked_to": t.get("linked_to")} for t in d["transactions"]]
    for table, rows, pk in (("spending_transactions", txs, "id"), ("spending_rules", rules, "id"),
                            ("spending_categories", cats, "id"), ("spending_accounts", accounts, "id")):
        _request(url, key, "DELETE", f"{table}?{pk}=not.is.null")
        for i in range(0, len(rows), 1000):
            _request(url, key, "POST", table, rows[i:i + 1000], prefer="return=minimal")
    return len(txs)


def _institution_of(account_name):
    n = account_name.lower()
    if "abn" in n:
        return "ABN AMRO"
    return account_name


def sync(url, key, state, cfg, history_rows):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    today = date.today().isoformat()
    m = state["managed"]
    institutions, accounts, instruments, holdings = {}, {}, {}, {}

    def inst(name):
        iid = slug(name)
        institutions[iid] = {"id": iid, "name": name, "updated_at": now}
        return iid

    def account(name, institution, kind, **extra):
        aid = slug(name)
        row = {"id": aid, "institution_id": inst(institution), "name": name, "kind": kind, "opened": None,
               "interest_rate_pct": None, "maturity": None, "counted_in_net_worth": True, "value_eur": None,
               "cash_eur": None, "profit_eur": None, "fees_paid_eur": None, "active": True, "updated_at": now}
        row.update(extra)
        accounts[aid] = row
        return aid

    acc_ids = {}
    for a in state["accounts"]:
        acc_ids[a["name"]] = account(a["name"], _institution_of(a["name"]), "brokerage", opened=a.get("since"),
                                     value_eur=a["value"] + a["cash"], cash_eur=a["cash"], profit_eur=a["profit"])
    acc_ids[m["name"]] = account(m["name"], "ABN AMRO", "managed", opened=m["start_date"], value_eur=m["value"],
                                 cash_eur=m["cash"], profit_eur=m["profit"], fees_paid_eur=m["fees_paid"])
    for s in state["savings"]:
        kind = "deposit" if s.get("maturity") else "current" if "current" in s["name"].lower() else "savings"
        account(s["name"], s.get("bank") or s["name"], kind, interest_rate_pct=s.get("rate_pct"),
                maturity=s.get("maturity"), value_eur=s["value"])
    for d in state["debts"]:
        account(d["name"], "DUO" if "duo" in d["name"].lower() else d["name"], "loan",
                interest_rate_pct=d.get("rate_pct"), value_eur=d["balance"], counted_in_net_worth=not d.get("expected_gift"))

    for p in state["positions"]:
        nid = p.get("isin") or "n:" + p["name"].strip().lower()
        instruments[nid] = {"id": nid, "isin": p.get("isin"), "name": p["name"], "category": p["category"],
                            "asset_type": TYPE_OF.get(p["category"], p["category"] or "Other"),
                            "ticker": p["source"] if p["live"] else None, "price_eur": p["price"],
                            "price_live": p["live"], "updated_at": now}
        aid = acc_ids[p["account"]]
        hid = f"{aid}|{nid}"
        holdings[hid] = {"id": hid, "account_id": aid, "instrument_id": nid, "units": p["units"],
                         "cost_eur": p.get("cost"), "net_cashflow_eur": (p["profit"] - p["value"]) if p["profit"] is not None else None,
                         "value_eur": p["value"], "profit_eur": p["profit"], "day_change_eur": p["day_change"],
                         "return_pct": p.get("since_buy_pct"), "maturity": p.get("maturity"), "active": True, "updated_at": now}

    def num(x):
        return float(x) if x not in (None, "") else None

    net_worth = [{"date": r["date"], "net_worth": num(r.get("net_worth")), "assets": num(r.get("gross")),
                  "debt": num(r.get("debt")), "managed": num(r.get("managed")), "savings": num(r.get("savings")),
                  "self_directed": num(r.get("self_directed"))} for r in history_rows]
    account_daily = [{"date": today, "account_id": a["id"], "value_eur": a["value_eur"]} for a in accounts.values()]
    holding_daily = [{"date": today, "holding_id": h["id"], "units": h["units"], "price_eur": instruments[h["instrument_id"]]["price_eur"],
                      "value_eur": h["value_eur"]} for h in holdings.values()]
    todos = cfg.get("todos", [])
    plan = [{"id": i, "text": t["text"], "done": bool(t.get("done"))} for i, t in enumerate(todos)]

    # parents before children, so foreign keys always resolve
    _upsert(url, key, "institutions", list(institutions.values()))
    _upsert(url, key, "accounts", list(accounts.values()))
    _upsert(url, key, "instruments", list(instruments.values()))
    _upsert(url, key, "holdings", list(holdings.values()))
    _retire(url, key, "holdings", now)
    _retire(url, key, "accounts", now)
    _upsert(url, key, "net_worth_daily", net_worth, "date")
    _upsert(url, key, "account_daily", account_daily, "date,account_id")
    _upsert(url, key, "holding_daily", holding_daily, "date,holding_id")
    _upsert(url, key, "plan_items", plan)
    _request(url, key, "DELETE", f"plan_items?id=gte.{len(plan)}")
    _upsert(url, key, "portfolio_backup", [{"id": 1, "data": cfg, "updated_at": now}])
    plans = [{"id": i, "account": x.get("account"), "instrument": x.get("instrument"), "isin": x.get("isin"),
              "amount_eur": x.get("amount_eur"), "frequency": x.get("frequency"), "day": x.get("day"),
              "active": bool(x.get("active")), "since": x.get("since"), "last_execution": x.get("last_execution"),
              "source": x.get("source")} for i, x in enumerate(cfg.get("savings_plans", []))]
    _request(url, key, "DELETE", "savings_plans?id=not.is.null")
    if plans:
        _request(url, key, "POST", "savings_plans", plans, prefer="return=minimal")
    # history is small and edited by hand or by the AI, so it is replaced as a whole
    fields = ("deposits_eur", "withdrawals_eur", "invested_eur", "dividends_eur", "interest_received_eur",
              "interest_paid_eur", "fees_eur", "taxes_eur", "profit_eur", "return_pct", "note")
    ah = {f"{r['date']}|{r['account']}": {"id": f"{r['date']}|{r['account']}", "date": r["date"], "account": r["account"],
                                          "value_eur": r.get("value_eur"), "source": r.get("source")}
          for r in cfg.get("account_history", [])}
    yf = {(r["year"], r["account"]): {"year": r["year"], "account": r["account"], **{k: r.get(k) for k in fields}}
          for r in cfg.get("yearly_flows", [])}
    _request(url, key, "DELETE", "account_history?id=not.is.null")
    if ah:
        _request(url, key, "POST", "account_history", list(ah.values()), prefer="return=minimal")
    _request(url, key, "DELETE", "yearly_flows?year=not.is.null")
    if yf:
        _request(url, key, "POST", "yearly_flows", list(yf.values()), prefer="return=minimal")
    return {"positions": len(holdings), "accounts": len(accounts), "institutions": len(institutions),
            "instruments": len(instruments)}
