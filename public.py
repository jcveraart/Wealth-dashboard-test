"""
Official, free public data that makes the dashboard smarter without cluttering it:
  - the European Central Bank: its deposit rate, inflation (Netherlands and euro area), what Dutch banks pay on
    savings on average, and exchange rates (data-api.ecb.europa.eu, no key)
  - the US SEC: company figures from annual reports for stocks listed in the US (data.sec.gov, no key)
Everything is fetched in the background, cached for a day (company figures for a week) and used where it helps:
the chat, the briefing, the savings page, history and an investment's detail panel.
"""
import csv
import io
import json
import re
import threading
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
ECONOMY = CACHE / "economy.json"
FUNDAMENTALS = CACHE / "fundamentals.json"
ECB = "https://data-api.ecb.europa.eu/service/data/"
_busy = set()
_lock = threading.Lock()


def _read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write(path, data):
    import extras
    extras.atomic_write(path, json.dumps(data, ensure_ascii=False))


def user_agent():
    """The SEC asks every caller to say who they are, with an email address."""
    try:
        contact = json.loads((HERE / "settings.json").read_text(encoding="utf-8")).get("contact_email") or ""
    except (FileNotFoundError, json.JSONDecodeError):
        contact = ""
    return f"WealthDashboard/1.0 (personal finance app{'; ' + contact if contact else ''})"


def get(url, timeout=20):
    if "sec.gov/" in url:
        from intelligence.data import HTTP
        return HTTP.get(url,sec=True)
    req = urllib.request.Request(url, headers={"User-Agent": user_agent(), "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


# ---------- the European Central Bank ----------
def parse_ecb_csv(text):
    """[(period, value)] from the ECB's csvdata format (columns TIME_PERIOD and OBS_VALUE), oldest first."""
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        v = (r.get("OBS_VALUE") or "").strip()
        if r.get("TIME_PERIOD") and v not in ("", "NaN"):
            try:
                rows.append((r["TIME_PERIOD"], float(v)))
            except ValueError:
                continue
    return sorted(rows)


def ecb_series(key, last=None, start=None):
    q = "format=csvdata" + (f"&lastNObservations={last}" if last else "") + (f"&startPeriod={start}" if start else "")
    flow, rest = key.split(".", 1)
    return parse_ecb_csv(get(f"{ECB}{flow}/{rest}?{q}"))


SERIES = {
    "ecb_rate": ["FM.D.U2.EUR.4F.KR.DFR.LEV"],                       # deposit facility rate, by date of change
    "inflation_nl": ["ICP.M.NL.N.000000.4.ANR"],                     # HICP Netherlands, change on a year earlier
    "inflation_ea": ["ICP.M.U2.N.000000.4.ANR"],                     # HICP euro area
    # what Dutch banks pay households on savings: notice accounts first, then overnight deposits, then the euro area
    "savings_nl": ["MIR.M.NL.B.L23.D.R.A.2250.EUR.N", "MIR.M.NL.B.L21.Z.R.A.2250.EUR.O", "MIR.M.U2.B.L23.D.R.A.2250.EUR.N"],
    "usd": ["EXR.D.USD.EUR.SP00.A"],                                 # US dollars per euro
    # what the safest euro government bonds (AAA) pay, for 2 and 10 years
    "bond2": ["YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y"],
    "bond10": ["YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y"],
}


def _fetch_economy():
    out = _read(ECONOMY, {})
    for name, keys in SERIES.items():
        for key in keys:
            try:
                rows = ecb_series(key, start=(date.today() - timedelta(days=365 * 11)).isoformat()[:7] if "ICP" in key else None,
                                  last=None if "ICP" in key else 40)
            except Exception as e:
                out.setdefault("errors", {})[name] = str(e)[:160]
                continue
            if rows:
                out[name] = {"key": key, "rows": rows[-140:]}
                out.get("errors", {}).pop(name, None)
                break
    out["fetched"] = datetime.now().isoformat(timespec="seconds")
    _write(ECONOMY, out)


def economy(offline=False):
    """{ecb_rate, ecb_rate_since, ecb_rate_before, inflation_nl, inflation_nl_month, inflation_ea, inflation_nl_avg5,
    savings_nl, savings_nl_month, usd, fetched}: plain numbers, None when not known."""
    cache = _read(ECONOMY, {})
    stale = cache.get("fetched", "")[:10] != date.today().isoformat()
    if stale and not offline and "economy" not in _busy:
        _busy.add("economy")
        threading.Thread(target=lambda: (_fetch_economy(), _busy.discard("economy")), daemon=True).start()
    rows = lambda n: (cache.get(n) or {}).get("rows") or []
    out = {"fetched": cache.get("fetched"), "updating": "economy" in _busy}
    r = rows("ecb_rate")
    out["ecb_rate"] = r[-1][1] if r else None
    if r:
        change = next((i for i in range(len(r) - 1, 0, -1) if r[i][1] != r[i - 1][1]), None)
        out["ecb_rate_since"] = r[change][0] if change is not None else None
        out["ecb_rate_before"] = r[change - 1][1] if change is not None else None
    nl = rows("inflation_nl")
    out["inflation_nl"], out["inflation_nl_month"] = (nl[-1][1], nl[-1][0]) if nl else (None, None)
    five = [v for p, v in nl if p >= f"{date.today().year - 5}"]
    out["inflation_nl_avg5"] = sum(five) / len(five) if five else None
    out["inflation_nl_history"] = nl
    ea = rows("inflation_ea")
    out["inflation_ea"] = ea[-1][1] if ea else None
    s = rows("savings_nl")
    out["savings_nl"], out["savings_nl_month"] = (s[-1][1], s[-1][0]) if s else (None, None)
    out["savings_nl_area"] = "euro area" if (cache.get("savings_nl") or {}).get("key", "").startswith("MIR.M.U2") else "Netherlands"
    u = rows("usd")
    out["usd"] = u[-1][1] if u else None
    for k in ("bond2", "bond10"):
        b = rows(k)
        out[k] = round(b[-1][1], 2) if b else None
    return out


def inflation_between(econ, start_iso, end_iso=None):
    """How much prices rose between two dates (0.12 for 12%), from the monthly yearly rates, or None."""
    hist = econ.get("inflation_nl_history") or []
    if not hist:
        return None
    months = [v for p, v in hist if start_iso[:7] <= p <= (end_iso or "9999")[:7]]
    if len(months) < 6:
        return None
    factor = 1.0
    for v in months:
        factor *= (1 + v / 100) ** (1 / 12)
    return factor - 1


# ---------- company figures from the SEC ----------
CONCEPTS = {
    "revenue": [("us-gaap", "Revenues"), ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
                ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"),
                ("us-gaap", "SalesRevenueNet"), ("ifrs-full", "Revenue")],
    "net_income": [("us-gaap", "NetIncomeLoss"), ("ifrs-full", "ProfitLossAttributableToOwnersOfParent"), ("ifrs-full", "ProfitLoss")],
    "equity": [("us-gaap", "StockholdersEquity"), ("ifrs-full", "EquityAttributableToOwnersOfParent"), ("ifrs-full", "Equity")],
    # a company with several share classes reports the count per class, which the SEC's companyfacts
    # drops, so Alphabet and Nebius have no count at all; their diluted average is the whole company
    "shares": [("dei", "EntityCommonStockSharesOutstanding"),
               ("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding"),
               ("ifrs-full", "WeightedAverageNumberOfDilutedSharesOutstanding")],
}


def annual(facts, concepts):
    """Yearly values for one of these concepts: [(fiscal year end, value, unit)], oldest first.

    The one reporting the most recent year wins, rather than whichever is listed first. Companies
    leave old tags behind when the accounting standard moves on, and a company that changed
    reporting currency keeps filing both: Microsoft still carries "Revenues" up to 2010 beside the
    tag it uses today, and Nebius still carries Yandex's roubles up to 2023 beside its own dollars.
    """
    best = []
    for ns, name in concepts:
        units = ((facts.get(ns) or {}).get(name) or {}).get("units") or {}
        for unit, vals in units.items():
            years = {}
            for v in vals:
                if v.get("form") in ("10-K", "20-F", "40-F") and (v.get("fp") == "FY" or ns == "dei"):
                    end = v.get("end", "")
                    start = v.get("start")
                    if start and (date.fromisoformat(end) - date.fromisoformat(start)).days < 330:
                        continue  # a quarter inside the annual report
                    years[end] = (end, float(v["val"]), unit)
            series = sorted(years.values())
            if series and (not best or series[-1][0] > best[-1][0]):
                best = series
    return best


def summarize(facts):
    """The few numbers worth showing: last year's revenue and growth, profit margin, equity and shares."""
    rev, inc = annual(facts, CONCEPTS["revenue"]), annual(facts, CONCEPTS["net_income"])
    eq, sh = annual(facts, CONCEPTS["equity"]), annual(facts, CONCEPTS["shares"])
    if not rev and not inc:
        return None
    out = {"currency": (rev or inc)[-1][2].split("/")[0]}
    if rev:
        out["year"], out["revenue"] = rev[-1][0][:4], rev[-1][1]
        if len(rev) > 1 and rev[-2][1]:
            out["revenue_growth_pct"] = round((rev[-1][1] / rev[-2][1] - 1) * 100, 1)
        if len(rev) > 3 and rev[-4][1] > 0:
            out["revenue_cagr3_pct"] = round(((rev[-1][1] / rev[-4][1]) ** (1 / 3) - 1) * 100, 1)
    if inc:
        out["net_income"] = inc[-1][1]
        out.setdefault("year", inc[-1][0][:4])
        if rev and rev[-1][1]:
            out["net_margin_pct"] = round(inc[-1][1] / rev[-1][1] * 100, 1)
    if eq:
        out["equity"] = eq[-1][1]
    if sh:
        out["shares"] = sh[-1][1]
    return out


def _cik_map():
    """{ticker: (cik, company name)} from the SEC's own list."""
    data = json.loads(get("https://www.sec.gov/files/company_tickers.json"))
    return {v["ticker"].upper(): (int(v["cik_str"]), v["title"]) for v in data.values()}


def same_company(holding, title):
    """Only trust a ticker match when the holding's name and the SEC's company name share their first real word."""
    words = lambda s: [w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in ("the", "nv", "inc", "corp", "holding", "holdings", "plc", "sa", "ag")]
    a, b = words(holding), words(title)
    return bool(a and b and a[0] == b[0])


def parse_form4(xml):
    """Open market buys and sells in one insider filing: [(code, shares, price, date)]. P is a buy, S a sale."""
    import xml.etree.ElementTree as ET
    out = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return out
    owner = (root.findtext(".//reportingOwner/reportingOwnerId/rptOwnerName") or "").strip()
    for t in root.iter("nonDerivativeTransaction"):
        code = (t.findtext("transactionCoding/transactionCode") or "").strip()
        if code not in ("P", "S"):
            continue
        try:
            shares = float(t.findtext("transactionAmounts/transactionShares/value") or 0)
            price = float(t.findtext("transactionAmounts/transactionPricePerShare/value") or 0)
        except ValueError:
            continue
        out.append((code, shares, price, (t.findtext("transactionDate/value") or "")[:10], owner))
    return out


def insiders(cik, days=120, limit=25):
    """What a US company's directors and officers bought and sold on the open market lately (Form 4 filings)."""
    sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")).get("filings", {}).get("recent", {})
    cut = (date.today() - timedelta(days=days)).isoformat()
    buys = sells = 0.0
    buyers = set()
    seen = 0
    for form, when, acc, doc in zip(sub.get("form", []), sub.get("filingDate", []), sub.get("accessionNumber", []), sub.get("primaryDocument", [])):
        if form != "4" or when < cut or seen >= limit:
            continue
        seen += 1
        raw_doc = doc.split("/")[-1]  # the primary document points at a styled copy; the raw XML has the same name
        try:
            xml = get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{raw_doc}")
        except Exception:
            continue
        for code, shares, price, _, owner in parse_form4(xml):
            if code == "P":
                buys += shares * price
                buyers.add(owner)
            else:
                sells += shares * price
    return {"days": days, "buys_usd": round(buys), "sells_usd": round(sells), "buyers": sorted(b for b in buyers if b)[:5], "filings": seen}


def _fetch_fundamentals(stocks):
    cache = _read(FUNDAMENTALS, {})
    try:
        ciks = _cik_map()
    except Exception as e:
        cache["error"] = str(e)[:160]
        _write(FUNDAMENTALS, cache)
        return
    for pid, (name, tickers) in stocks.items():
        hit = None
        for t in tickers:
            base = t.split(".")[0].upper()
            if base in ciks and same_company(name, ciks[base][1]):
                hit = ciks[base]
                break
        if not hit:
            cache[pid] = {"fetched": date.today().isoformat(), "none": True}
            continue
        try:
            facts = json.loads(get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{hit[0]:010d}.json", timeout=40)).get("facts", {})
            cache[pid] = {"fetched": date.today().isoformat(), "company": hit[1], "cik": hit[0], **(summarize(facts) or {"none": True})}
            try:
                cache[pid]["insiders"] = insiders(hit[0])
            except Exception:
                pass
        except Exception as e:
            cache[pid] = {"fetched": date.today().isoformat(), "error": str(e)[:160]}
        _write(FUNDAMENTALS, cache)
    _write(FUNDAMENTALS, cache)


def fundamentals(stocks, offline=False):
    """{position id: figures} for single stocks listed in the US. stocks: {position id: (name, [tickers])}.

    When nothing could be fetched at all, the reason comes back under "_error" so the page can say
    why it is empty. A stock that simply files nothing with the SEC is left out silently, as before.
    """
    cache = _read(FUNDAMENTALS, {})
    week = (date.today() - timedelta(days=7)).isoformat()
    todo = {k: v for k, v in stocks.items() if (cache.get(k) or {}).get("fetched", "") < week}
    if todo and not offline and "sec" not in _busy:
        _busy.add("sec")
        threading.Thread(target=lambda: (_fetch_fundamentals(todo), _busy.discard("sec")), daemon=True).start()
    out = {k: v for k, v in cache.items() if k in stocks and not v.get("none") and not v.get("error")}
    if not out:
        why = cache.get("error") or next((v["error"] for k, v in cache.items() if k in stocks and v.get("error")), None)
        if why:
            # 403 means the SEC did not like the User-Agent, which needs contact_email in settings.json
            out["_error"] = {"message": why, "contact": "403" in why}
    return out


def with_valuation(figs, price_eur, usd_per_eur):
    """Add the price to earnings and price to book ratios, converting the company's currency to euros."""
    out = dict(figs)
    rate = 1.0 if figs.get("currency") == "EUR" else (1 / usd_per_eur if figs.get("currency") == "USD" and usd_per_eur else None)
    if rate and figs.get("shares") and price_eur:
        cap = figs["shares"] * price_eur
        out["market_cap_eur"] = cap
        if figs.get("net_income", 0) > 0:
            out["pe"] = round(cap / (figs["net_income"] * rate), 1)
        if figs.get("equity", 0) > 0:
            out["pb"] = round(cap / (figs["equity"] * rate), 1)
    return out


# ---------- industry valuations (Aswath Damodaran, NYU Stern, free) ----------
INDUSTRY = CACHE / "industries.json"
DAMODARAN_PE = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/pedata.html"


def parse_table_html(html):
    """Every table row as a list of cell texts, from a plain HTML page (standard library only)."""
    from html.parser import HTMLParser

    class P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows, self.row, self.cell = [], None, None

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self.row = []
            elif tag in ("td", "th") and self.row is not None:
                self.cell = []

        def handle_endtag(self, tag):
            if tag in ("td", "th") and self.cell is not None and self.row is not None:
                self.row.append(" ".join("".join(self.cell).split()))
                self.cell = None
            elif tag == "tr" and self.row is not None:
                if any(self.row):
                    self.rows.append(self.row)
                self.row = None

        def handle_data(self, data):
            if self.cell is not None:
                self.cell.append(data)
    p = P()
    p.feed(html)
    return p.rows


def parse_industry_pe(html):
    """{industry: {pe, forward_pe, growth_pct, firms}} from Damodaran's P/E by industry page."""
    rows = parse_table_html(html)
    head = next((i for i, r in enumerate(rows) if any("industry" in c.lower() for c in r) and any("pe" in c.lower() for c in r)), None)
    if head is None:
        return {}
    cols = [c.lower() for c in rows[head]]
    find = lambda *words: next((i for i, c in enumerate(cols) if all(w in c for w in words)), None)
    i_name, i_cur, i_fwd, i_trail = find("industry"), find("current", "pe"), find("forward", "pe"), find("trailing", "pe")
    i_growth, i_firms = find("growth"), find("number")
    num = lambda s: (lambda x: x if x == x else None)(float(s.replace("%", "").replace(",", ""))) if s and re.match(r"^-?[\d.,]+%?$", s) else None
    out = {}
    for r in rows[head + 1:]:
        if i_name is None or len(r) <= i_name or not r[i_name] or r[i_name].lower().startswith("total"):
            continue
        cell = lambda i: num(r[i]) if i is not None and i < len(r) else None
        pe = cell(i_cur) or cell(i_trail)
        if pe is None:
            continue
        g = cell(i_growth)
        out[r[i_name]] = {"pe": round(pe, 1), "forward_pe": cell(i_fwd), "growth_pct": round(g * 100, 1) if g is not None and abs(g) < 1 else g, "firms": cell(i_firms)}
    return out


def industries(offline=False):
    """Damodaran's P/E by industry (US companies), refreshed once a month."""
    cache = _read(INDUSTRY, {})
    month = date.today().isoformat()[:7]
    if cache.get("month") != month and not offline and "industry" not in _busy:
        _busy.add("industry")

        def work():
            try:
                data = parse_industry_pe(get(DAMODARAN_PE))
                if data:
                    _write(INDUSTRY, {"month": month, "source": DAMODARAN_PE, "industries": data})
            except Exception as e:
                c = _read(INDUSTRY, {})
                c["error"] = str(e)[:160]
                _write(INDUSTRY, c)
            finally:
                _busy.discard("industry")
        threading.Thread(target=work, daemon=True).start()
    return cache.get("industries") or {}


# ---------- what well known investors did last quarter (SEC 13F filings) ----------
FUNDS_FILE = CACHE / "funds.json"
FUNDS = [(1067983, "Berkshire Hathaway"), (1336528, "Pershing Square"), (1649339, "Scion Asset Management")]


def parse_13f(xml):
    """{cusip: {name, value, shares}} from a 13F information table (namespaces ignored)."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return {}
    local = lambda el: el.tag.rsplit("}", 1)[-1]
    out = {}
    for row in root.iter():
        if local(row) != "infoTable":
            continue
        f = {}
        for el in row.iter():
            if local(el) in ("nameOfIssuer", "cusip", "value", "sshPrnamt") and el.text:
                f[local(el)] = el.text.strip()
        if not f.get("cusip"):
            continue
        cur = out.setdefault(f["cusip"], {"name": f.get("nameOfIssuer", ""), "value": 0.0, "shares": 0.0})
        cur["value"] += float(f.get("value") or 0)
        cur["shares"] += float(f.get("sshPrnamt") or 0)
    return out


def compare_13f(now, before):
    """What changed between two quarters: new positions, bigger ones, smaller ones, sold out. Largest first."""
    total = sum(v["value"] for v in now.values()) or 1
    moves = []
    for k, v in now.items():
        b = before.get(k)
        if not b:
            moves.append({"name": v["name"], "move": "new", "share_pct": round(v["value"] / total * 100, 1), "value": v["value"]})
        elif b["shares"] and v["shares"] >= b["shares"] * 1.2:
            moves.append({"name": v["name"], "move": "added", "change_pct": round((v["shares"] / b["shares"] - 1) * 100), "share_pct": round(v["value"] / total * 100, 1), "value": v["value"]})
        elif b["shares"] and v["shares"] <= b["shares"] * 0.8:
            moves.append({"name": v["name"], "move": "reduced", "change_pct": round((v["shares"] / b["shares"] - 1) * 100), "share_pct": round(v["value"] / total * 100, 1), "value": v["value"]})
    for k, b in before.items():
        if k not in now:
            moves.append({"name": b["name"], "move": "sold", "value": b["value"]})
    order = {"new": 0, "added": 1, "reduced": 2, "sold": 3}
    return sorted(moves, key=lambda m: (order[m["move"]], -m["value"]))


def _infotable(cik, acc):
    folder = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/"
    items = json.loads(get(folder + "index.json")).get("directory", {}).get("item", [])
    xmls = [i["name"] for i in items if i["name"].lower().endswith(".xml") and "primary_doc" not in i["name"].lower()]
    return parse_13f(get(folder + xmls[0])) if xmls else {}


def _fetch_funds():
    out = {"fetched": date.today().isoformat(), "funds": []}
    for cik, name in FUNDS:
        try:
            sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")).get("filings", {}).get("recent", {})
            filings = [(a, d, p) for f, a, d, p in zip(sub.get("form", []), sub.get("accessionNumber", []), sub.get("filingDate", []), sub.get("reportDate", [])) if f == "13F-HR"][:2]
            if len(filings) < 2:
                continue
            now, before = _infotable(cik, filings[0][0]), _infotable(cik, filings[1][0])
            out["funds"].append({"name": name, "filed": filings[0][1], "quarter": filings[0][2], "moves": compare_13f(now, before)[:12],
                                 "top": [v["name"] for v in sorted(now.values(), key=lambda v: -v["value"])[:5]]})
        except Exception as e:
            out.setdefault("errors", {})[name] = str(e)[:160]
    _write(FUNDS_FILE, out)


def funds(offline=False):
    """The latest quarterly moves of a few well known investors, refreshed weekly."""
    cache = _read(FUNDS_FILE, {})
    if cache.get("fetched", "") < (date.today() - timedelta(days=7)).isoformat() and not offline and "funds" not in _busy:
        _busy.add("funds")
        threading.Thread(target=lambda: (_fetch_funds(), _busy.discard("funds")), daemon=True).start()
    return cache.get("funds") or []
