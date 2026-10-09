"""Checks for the calculations behind the dashboard. Run: python -m unittest discover tests"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
import spending  # noqa: E402


class TempData(unittest.TestCase):
    """Each test gets its own spending.json, so real data is never touched."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.old = spending.FILE
        spending.FILE = self.tmp / "spending.json"

    def tearDown(self):
        spending.FILE = self.old
        shutil.rmtree(self.tmp)

    def add(self, rows):
        return spending.import_transactions("test.csv", rows)


def row(date, amount, desc, account="NL91ABNA0417164300", iban=""):
    return {"date": date, "amount": amount, "description": desc, "counterparty": "", "counter_iban": iban, "account": account}


class Debts(unittest.TestCase):
    def test_interest_only_without_a_payment(self):
        self.assertAlmostEqual(app.debt_balance(10000, 3.0, 0, 365.25), 10000 * 1.03, delta=2)

    def test_payment_brings_the_balance_down(self):
        after_year = app.debt_balance(10000, 3.0, 200, 365.25)
        self.assertTrue(10000 - 12 * 200 < after_year < 10000 - 12 * 200 + 400)

    def test_paid_off_stays_zero(self):
        self.assertEqual(app.debt_balance(500, 2.0, 200, 400), 0.0)


class Splits(TempData):
    def test_split_must_add_up_and_counts_per_category(self):
        self.add([row("2026-03-02", -100.0, "BEA, Apple Pay Bol.com,PAS123 NR:AB, 02.03.26/12:00 UTRECHT")])
        t = spending.load()["transactions"][0]
        with self.assertRaises(ValueError):
            spending.edit({"action": "split", "id": t["id"], "parts": [{"category": "home", "amount": -60}, {"category": "gifts", "amount": -30}]})
        spending.edit({"action": "split", "id": t["id"], "parts": [{"category": "home", "amount": -60}, {"category": "gifts", "amount": -40}]})
        t = spending.load()["transactions"][0]
        self.assertEqual([p["category"] for p in spending.parts(t)], ["home", "gifts"])
        self.assertEqual(sum(p["amount"] for p in spending.parts(t)), -100.0)
        spending.edit({"action": "split", "id": t["id"], "parts": []})
        self.assertNotIn("splits", spending.load()["transactions"][0])


class Tags(TempData):
    def test_hashtags_in_a_message_become_tags(self):
        self.assertEqual(spending.tags_in("dinner for the #Wedding and #holiday-spain"), {"wedding", "holiday-spain"})
        self.add([row("2026-03-02", -40.0, "BEA, Apple Pay Cafe,PAS123 NR:AB, 02.03.26/20:00 UTRECHT")])
        t = spending.load()["transactions"][0]
        spending.edit({"action": "note", "id": t["id"], "text": "drinks #birthday"})
        self.assertEqual(spending.load()["transactions"][0]["tags"], ["birthday"])


class Tikkies(TempData):
    def test_money_from_friends_is_never_spending(self):
        self.add([row("2026-09-02", 31.0, "/TRTP/iDEAL/NAME/AAB INZ TIKKIE/REMI/Tikkie ID 123 Pizza"),
                  row("2026-09-03", -26.33, "/TRTP/iDEAL/NAME/Hr J van Elderen via ING Betaalverzoek/REMI/Etentje")])
        d = spending.load()
        got = {t["amount"]: t["category"] for t in d["transactions"]}
        self.assertEqual(got, {31.0: "from-people", -26.33: "people"})
        kinds = {c["id"]: c["kind"] for c in d["categories"]}
        self.assertEqual((kinds["from-people"], kinds["people"]), ("income", "expense"))
        # a choice made earlier, before the rule, is turned around too
        t = next(t for t in d["transactions"] if t["amount"] > 0)
        t["category"] = "people"
        spending.save(d)
        self.assertEqual(next(t for t in spending.load()["transactions"] if t["amount"] > 0)["category"], "from-people")


class AccountKinds(unittest.TestCase):
    def test_payment_savings_and_deposits(self):
        k = app.account_kind
        self.assertEqual(k({"name": "Current account", "bank": "ABN AMRO", "rate_pct": 0.01}), "payment")
        self.assertEqual(k({"name": "Spaarrekening", "rate_pct": 2.5}), "savings")
        self.assertEqual(k({"name": "Raisin 1 year", "rate_pct": 3.1, "maturity": "2027-01-01"}), "deposit")
        self.assertEqual(k({"name": "Spaarrekening", "rate_pct": 0}), "payment")
        self.assertEqual(k({"name": "Current account", "kind": "savings"}), "savings")


class Budgets(TempData):
    def test_budget_set_and_removed(self):
        self.add([row("2026-03-02", -40.0, "BEA, Apple Pay Albert Heijn,PAS123 NR:AB, 02.03.26/20:00 UTRECHT")])
        spending.edit({"action": "budget", "key": "group:Food and drink", "amount": 400})
        self.assertEqual(spending.load()["budgets"], {"group:Food and drink": 400.0})
        spending.edit({"action": "budget", "key": "group:Food and drink", "amount": None})
        self.assertEqual(spending.load()["budgets"], {})

    def test_subscription_status(self):
        self.add([row("2026-03-05", -12.99, "/TRTP/SEPA Incasso/IBAN/IE29AIBK93115212345678/NAME/Spotify/REMI/abonnement")])
        spending.edit({"action": "subscription", "key": "spotify", "status": "cancelled"})
        self.assertEqual(spending.load()["subscriptions"]["spotify"]["status"], "cancelled")


class Excluded(TempData):
    def test_left_out_payments_are_kept_but_flagged(self):
        self.add([row("2026-03-02", -40.0, "BEA, Apple Pay Cafe,PAS123 NR:AB, 02.03.26/20:00 UTRECHT")])
        t = spending.load()["transactions"][0]
        spending.edit({"action": "exclude", "ids": [t["id"]], "excluded": True})
        self.assertTrue(spending.load()["transactions"][0]["excluded"])
        spending.edit({"action": "exclude", "ids": [t["id"]], "excluded": False})
        self.assertNotIn("excluded", spending.load()["transactions"][0])


class ExcludedMerchant(TempData):
    def test_merchant_left_out_now_and_on_later_imports(self):
        self.add([row("2026-03-02", -40.0, "PayPal Europe S.a.r.l. et Cie", account="NL01ABNA0000000001")])
        t = spending.load()["transactions"][0]
        spending.edit({"action": "exclude-merchant", "key": t["key"], "excluded": True})
        self.assertTrue(spending.load()["transactions"][0]["excluded"])
        self.add([row("2026-04-02", -25.0, "PayPal Europe S.a.r.l. et Cie", account="NL01ABNA0000000001")])
        self.assertTrue(all(x.get("excluded") for x in spending.load()["transactions"]))
        self.assertNotIn("PayPal", spending.summary_text().split("Top merchants")[1])
        spending.edit({"action": "exclude-merchant", "key": t["key"], "excluded": False})
        self.assertFalse(any(x.get("excluded") for x in spending.load()["transactions"]))


class Effort(unittest.TestCase):
    def test_levels_and_changes(self):
        import ai
        self.assertEqual(ai.pick_level("How much did I spend on groceries?"), "quick")
        self.assertEqual(ai.pick_level("Should I sell ASML?"), "normal")
        self.assertEqual(ai.pick_level("hi", "deep"), "deep")
        self.assertTrue(ai.wants_change("I sold my Intel shares yesterday"))
        self.assertTrue(ai.wants_change("add a to do: call the bank"))
        self.assertFalse(ai.wants_change("Should I buy more ASML?"))
        self.assertEqual(ai.cli_model("quick"), ["--model", "haiku"])
        self.assertNotIn("output_config", ai.api_params("quick"))


class News(unittest.TestCase):
    def test_both_yahoo_shapes(self):
        import extras
        old = [{"uuid": "a", "title": "ASML beats", "publisher": "Reuters", "link": "https://x.com/a", "providerPublishTime": 1760000000}]
        new = [{"id": "b", "content": {"title": "ASML guidance", "pubDate": "2026-10-05T10:00:00Z", "provider": {"displayName": "Bloomberg"},
                                       "canonicalUrl": {"url": "https://y.com/b"}, "clickThroughUrl": None}},
               {"id": "c", "content": {"title": "No link"}}]
        got = extras.parse_news(old, "ASML") + extras.parse_news(new, "ASML")
        self.assertEqual([g["source"] for g in got], ["Reuters", "Bloomberg"])
        self.assertEqual(got[1]["date"], "2026-10-05T10:00:00")


class PublicData(unittest.TestCase):
    def test_ecb_csv_and_inflation(self):
        import public
        text = "KEY,FREQ,TIME_PERIOD,OBS_VALUE\nICP.M.NL,M,2026-01,3.0\nICP.M.NL,M,2025-12,2.0\nICP.M.NL,M,2026-02,NaN\n"
        self.assertEqual(public.parse_ecb_csv(text), [("2025-12", 2.0), ("2026-01", 3.0)])
        econ = {"inflation_nl_history": [(f"2025-{m:02d}", 2.4) for m in range(1, 13)]}
        self.assertAlmostEqual(public.inflation_between(econ, "2025-01"), 0.024, places=3)

    def test_company_figures(self):
        import public
        def facts(vals, unit="USD"):
            return {"units": {unit: [{"form": "10-K", "fp": "FY", "start": f"{y}-01-01", "end": f"{y}-12-31", "val": v} for y, v in vals]}}
        f = {"us-gaap": {"Revenues": facts([(2022, 100), (2023, 110), (2024, 121), (2025, 133.1)]), "NetIncomeLoss": facts([(2025, 13.31)]),
                         "StockholdersEquity": facts([(2025, 50)])},
             "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [{"form": "10-K", "fp": "FY", "end": "2025-12-31", "val": 10}]}}}}
        s = public.summarize(f)
        self.assertEqual((s["revenue_growth_pct"], s["revenue_cagr3_pct"], s["net_margin_pct"]), (10.0, 10.0, 10.0))
        v = public.with_valuation(s, price_eur=20, usd_per_eur=1.0)
        self.assertEqual((v["pe"], v["pb"]), (15.0, 4.0))
        self.assertTrue(public.same_company("ASML", "ASML HOLDING NV"))
        self.assertFalse(public.same_company("BYD", "Boyd Gaming Corp"))

    def test_local_model_falls_back(self):
        import local
        local._state.update(checked=__import__("time").time(), models=[])
        self.assertIsNone(local.wanted("categorise"))


class Opportunities(unittest.TestCase):
    def test_dip_target_and_watch_signals(self):
        import extras, ideas
        from datetime import date, timedelta
        days = [(date.today() - timedelta(days=200 - i)).isoformat() for i in range(200)]
        closes = [100.0] * 100 + [70.0] * 100
        orig = extras.read
        extras.read = lambda path, default: {"dates": days, "close": closes, "fetched": date.today().isoformat()} if str(path).endswith(".json") and "history" in str(path) else orig(path, default)
        try:
            state = {"positions": [{"name": "Chipco", "isin": "X1", "category": "Stock", "value": 700.0},
                                   {"name": "World", "isin": "X2", "category": "Broad ETF", "value": 9300.0}],
                     "targets": {"X1": 20}, "watchlist": [{"name": "Chipco", "symbol": "CHIP", "buy_below": 80}]}
            got = {s["kind"] for s in ideas.signals(state, {"X1": "CHIP"}, {})}
        finally:
            extras.read = orig
        self.assertEqual(got, {"dip", "target", "watch"})


class OpenSignals(unittest.TestCase):
    def test_bonds_and_insiders(self):
        import ideas
        state = {"positions": [{"name": "Intel", "isin": "US1", "category": "Stock", "value": 500.0}], "savings": [{"name": "Spaar", "rate_pct": 1.5, "invest": False}]}
        figs = {"US1": {"company": "INTEL CORP", "insiders": {"days": 120, "buys_usd": 250000, "sells_usd": 0, "buyers": ["A. Director"]}}}
        got = {s["kind"] for s in ideas.signals(state, {}, {"bond2": 2.1, "bond10": 2.8}, figs)}
        self.assertEqual(got, {"insider", "rates"})


class Research(unittest.TestCase):
    def test_industry_pe_page(self):
        import public
        html = """<table><tr><td>Industry Name</td><td>Number of firms</td><td>Current PE</td><td>Trailing PE</td><td>Forward PE</td><td>Expected growth - next 5 years</td></tr>
        <tr><td>Semiconductor</td><td>68</td><td>35.20</td><td>38.1</td><td>28.4</td><td>18.50%</td></tr>
        <tr><td>Banks (Regional)</td><td>560</td><td>NA</td><td>11.3</td><td>10.2</td><td>6.10%</td></tr>
        <tr><td>Total Market</td><td>6000</td><td>22</td><td>23</td><td>20</td><td>10%</td></tr></table>"""
        got = public.parse_industry_pe(html)
        self.assertEqual(set(got), {"Semiconductor", "Banks (Regional)"})
        self.assertEqual((got["Semiconductor"]["pe"], got["Semiconductor"]["growth_pct"]), (35.2, 18.5))
        self.assertEqual(got["Banks (Regional)"]["pe"], 11.3)

    def test_fund_moves_and_signal(self):
        import public, ideas
        xml = lambda rows: '<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">' + "".join(
            f"<infoTable><nameOfIssuer>{n}</nameOfIssuer><cusip>{c}</cusip><value>{v}</value><shrsOrPrnAmt><sshPrnamt>{s}</sshPrnamt></shrsOrPrnAmt></infoTable>"
            for n, c, v, s in rows) + "</informationTable>"
        before = public.parse_13f(xml([("APPLE INC", "A", 100, 10), ("OXY", "O", 50, 10), ("GONE CO", "G", 5, 1)]))
        now = public.parse_13f(xml([("APPLE INC", "A", 100, 7), ("OXY", "O", 80, 15), ("ASML HOLDING", "S", 20, 2)]))
        moves = {m["name"]: m["move"] for m in public.compare_13f(now, before)}
        self.assertEqual(moves, {"ASML HOLDING": "new", "OXY": "added", "APPLE INC": "reduced", "GONE CO": "sold"})
        research = {"funds": [{"name": "Some Fund", "quarter": "2026-06-30", "moves": [{"name": "ASML HOLDING", "move": "new", "share_pct": 10, "yours": True},
                                                                                       {"name": "OXY", "move": "added", "share_pct": 40}]}]}
        got = [s for s in ideas.signals({"positions": []}, {}, {}, None, research) if s["kind"] == "fund"]
        self.assertEqual(len(got), 1)


class Countries(TempData):
    def test_country_from_bank_text_and_home(self):
        self.add([row("2026-07-10", -40.0, "BEA, Betaalpas Bar,PAS1 NR:X, 10.07.26/20:15 PORTO, Land: PRT"),
                  row("2026-07-11", -5.0, "BEA, Apple Pay AH,PAS1 NR:X, 11.07.26/10:00 UTRECHT"),
                  row("2026-07-12", -30.0, "ZARA BARCELONA ES", account="Creditcard ICS")])
        got = {t["description"][:20]: t["country"] for t in spending.load()["transactions"]}
        self.assertEqual(sorted(got.values()), ["ES", "NL", "PT"])


class Zips(unittest.TestCase):
    """A zip is opened before anything is routed, so a folder of exports can be dropped in at once."""

    @staticmethod
    def zipped(members, name="bundle.zip"):
        import base64
        import io
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for member, data in members:
                zf.writestr(member, data)
        return {"name": name, "media_type": "application/zip", "data": base64.b64encode(buf.getvalue()).decode()}

    def test_members_come_out_and_junk_stays_in(self):
        out = app.expand_archives([self.zipped([("exports/jan.csv", "a,b\n1,2\n"), ("exports/shot.png", b"\x89PNG"),
                                                ("notes.pdf", b"%PDF-1.4"), ("exports/sub/", ""),
                                                ("__MACOSX/._jan.csv", "junk"), (".DS_Store", "junk")])])
        self.assertEqual(sorted(f["name"] for f in out), ["jan.csv", "notes.pdf", "shot.png"])
        kinds = {f["name"]: f["media_type"] for f in out}
        self.assertEqual(kinds["shot.png"], "image/png")
        self.assertEqual(kinds["notes.pdf"], "application/pdf")
        self.assertEqual(kinds["jan.csv"], "")  # read by its name, not by what the computer calls a csv

    def test_other_files_pass_through_untouched(self):
        import base64
        plain = {"name": "x.csv", "media_type": "text/csv", "data": base64.b64encode(b"a,b").decode()}
        self.assertEqual(app.expand_archives([plain]), [plain])

    def test_a_zip_inside_a_zip(self):
        import base64
        inner = base64.b64decode(self.zipped([("deep.csv", "x,y\n")])["data"])
        out = app.expand_archives([self.zipped([("inner.zip", inner)], "outer.zip")])
        self.assertEqual([f["name"] for f in out], ["deep.csv"])

    def test_a_zipped_bank_export_is_still_read_by_code(self):
        import base64
        csv = ("Date,Amount,Description,Counterparty\n"
               "2026-09-03,-12.45,Card payment,ALBERT HEIJN 1234 AMSTERDAM\n"
               "2026-09-06,1500.00,Salary,SOME EMPLOYER BV\n")
        out = app.expand_archives([self.zipped([("september/abn.csv", csv)])])
        rows = spending.parse_known(out[0]["name"], base64.b64decode(out[0]["data"]))
        self.assertEqual([r["amount"] for r in rows], [-12.45, 1500.0])

    def test_a_zip_that_cannot_be_used_says_why(self):
        import base64
        for bad in [{"name": "broken.zip", "data": base64.b64encode(b"not a zip").decode()},
                    self.zipped([]),
                    self.zipped([("__MACOSX/._a", "junk")])]:
            with self.assertRaises(ValueError):
                app.expand_archives([bad])

    def test_too_much_is_refused(self):
        many = [("f%d.csv" % i, "a") for i in range(app.ARCHIVE_MAX_FILES + 5)]
        with self.assertRaises(ValueError):
            app.expand_archives([self.zipped(many)])


class ConcurrentWrites(unittest.TestCase):
    """Ten imports at once each write these files from their own thread."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_many_threads_writing_one_file_never_fail(self):
        import extras
        import threading
        path, errors = self.tmp / "busy.json", []

        def work(n):
            for r in range(15):
                try:
                    extras.write(path, [{"thread": n, "round": r, "pad": "x" * 300}])
                except Exception as e:  # a shared temporary name fails here on Windows
                    errors.append("%s: %s" % (type(e).__name__, e))

        threads = [threading.Thread(target=work, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertTrue(json.loads(path.read_text(encoding="utf-8")))
        self.assertEqual(list(self.tmp.glob("*.tmp")), [])

    def test_questions_asked_at_the_same_time_are_all_kept(self):
        import threading
        old = app.INBOX
        app.INBOX = self.tmp / "inbox.json"
        try:
            threads = [threading.Thread(target=app.ask_owner, args=("import-%d" % i, "question %d" % i))
                       for i in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            got = json.loads(app.INBOX.read_text(encoding="utf-8"))
            self.assertEqual(sorted(i["source"] for i in got), sorted("import-%d" % i for i in range(8)))
        finally:
            app.INBOX = old


class Advice(unittest.TestCase):
    def test_example_portfolio_gives_ranked_advice(self):
        cfg = json.loads((ROOT / "portfolio.example.json").read_text())
        state = app.compute_state(cfg, record=False)
        for r in state["advice"]:
            self.assertIn("effort", r)
            self.assertTrue(r.get("impact_eur") is None or r["impact_eur"] >= 0)


if __name__ == "__main__":
    unittest.main()
