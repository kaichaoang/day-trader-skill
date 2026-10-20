"""Offline tests for the KC branch: the book, the compliance gate, the tranche planner.

Every holding, cost and amount here is made up. Real figures live only in the
git-ignored trader/ folder. Prices are illustrative too.
"""

import contextlib
import datetime
import io
import json
import math
import os
import shutil
import tempfile
import unittest

from _load import load, ROOT

pf = load("kc-portfolio", "portfolio")
cp = load("kc-compliance", "compliance")
tr = load("kc-tranches", "tranches")

FX = 1.28
BOOK = {
    "fx": {"USDSGD": FX},
    "sleeves": {"kc": {"label": "KC"}, "family": {"label": "Family", "invested_usd": 3000.0}},
    "positions": [
        {"ticker": "D05.SI", "name": "DBS", "currency": "SGD", "group": "sg_bank", "sleeve": "kc", "units": 100, "avg_cost": 60.0},
        {"ticker": "GLDM", "group": "gold", "sleeve": "kc", "units": 200, "avg_cost": 90.0},
        {"ticker": "QQQM", "group": "nasdaq100", "sleeve": "kc", "units": 5, "avg_cost": 300.0},
        {"ticker": "SOXX", "group": "semis", "sleeve": "kc", "units": 4, "avg_cost": 600.0},
        {"ticker": "VOO", "group": "sp500", "sleeve": "kc", "units": 4, "avg_cost": 650.0},
        {"ticker": "SPYL.L", "name": "SPYL", "group": "sp500", "sleeve": "kc", "units": 20, "avg_cost": 19.5},
        {"ticker": "GLDM", "group": "gold", "sleeve": "family", "units": 30, "avg_cost": 92.0},
    ],
    "ledger": [],
}
QUOTES = {"GLDM": (80.0, 80.5), "QQQM": (300.0, 297.0), "SOXX": (500.0, 495.0),
          "VOO": (700.0, 697.0), "SPYL.L": (19.0, 19.05), "D05.SI": (75.0, 74.5)}


def book():
    return json.loads(json.dumps(BOOK))


def quotes():
    return {k: {"price": p, "prev_close": c} for k, (p, c) in QUOTES.items()}


def cfg():
    with open(os.path.join(ROOT, "kc-tranches", "tranche-config.example.json")) as fh:
        return json.load(fh)


def funds():
    with open(os.path.join(ROOT, "kc-compliance", "funds.example.json")) as fh:
        return json.load(fh)


def kc_values():
    """Expected KC-sleeve values in USD, worked out by hand from BOOK and QUOTES."""
    v = {"D05.SI": 100 * 75.0 / FX, "GLDM": 200 * 80.0, "QQQM": 5 * 300.0, "SOXX": 4 * 500.0,
         "VOO": 4 * 700.0, "SPYL.L": 20 * 19.0}
    return v, sum(v.values())


class Book(unittest.TestCase):
    def test_buy_blends_the_average(self):
        b = book()
        p = pf.apply_trade(b, "buy", "GLDM", 50, 80.0)
        self.assertAlmostEqual(p["units"], 250)
        self.assertAlmostEqual(p["avg_cost"], (200 * 90.0 + 50 * 80.0) / 250, places=5)

    def test_sell_keeps_the_average(self):
        b = book()
        p = pf.apply_trade(b, "sell", "GLDM", 6.25, 80.0)
        self.assertAlmostEqual(p["units"], 193.75)
        self.assertEqual(p["avg_cost"], 90.0)
        self.assertEqual(b["ledger"][-1]["sleeve"], "kc")

    def test_trades_are_kcs_own_unless_said_otherwise(self):
        b = book()
        pf.apply_trade(b, "sell", "GLDM", 1, 80)
        self.assertEqual(pf.find(b, "GLDM", "family")["units"], 30)
        pf.apply_trade(b, "buy", "VOO", 1, 700, sleeve="family")
        self.assertEqual(pf.find(b, "VOO", "family")["units"], 1)
        self.assertEqual(pf.find(b, "VOO", "kc")["units"], 4)

    def test_cannot_oversell_a_sleeve(self):
        with self.assertRaises(pf.BookError):
            pf.apply_trade(book(), "sell", "GLDM", 31, 80, sleeve="family")

    def test_split_scales_units_and_cost(self):
        b = book()
        pf.apply_split(b, "SOXX", 2)
        p = pf.find(b, "SOXX", "kc")
        self.assertEqual(p["units"], 8)
        self.assertAlmostEqual(p["avg_cost"], 300.0)

    def test_dividend_estimate_after_withholding(self):
        est = pf.dividend_estimate(book(), "VOO", 2.0, 700)
        self.assertEqual(len(est), 1)
        self.assertAlmostEqual(est[0]["new_units"], 2.0 * 4 * 0.7 / 700, places=5)

    def test_valuation(self):
        v = pf.valuation(book(), quotes(), FX)
        vals, total = kc_values()
        kc = v["sleeves"]["kc"]
        self.assertAlmostEqual(kc["total_usd"], total, delta=0.05)
        self.assertAlmostEqual(kc["group_weights"]["gold"], vals["GLDM"] / total * 100, delta=0.02)
        self.assertAlmostEqual(kc["group_weights"]["sp500"], (vals["VOO"] + vals["SPYL.L"]) / total * 100, delta=0.02)
        fam = v["sleeves"]["family"]
        self.assertAlmostEqual(fam["total_usd"], 2400.0)
        self.assertAlmostEqual(fam["pnl_vs_invested_pct"], -20.0)
        dbs = next(r for r in v["positions"] if r["ticker"] == "D05.SI")
        self.assertAlmostEqual(dbs["value_usd"], vals["D05.SI"], delta=0.01)

    def test_prices_file_in_either_shape(self):
        d = tempfile.mkdtemp()
        try:
            a = os.path.join(d, "a.json")
            with open(a, "w") as fh:
                json.dump({"prices": {"GLDM": 80.0}, "detail": {"GLDM": {"prev_close": 80.5}}}, fh)
            self.assertEqual(pf.load_prices(a)["GLDM"], {"price": 80.0, "prev_close": 80.5})
            with open(a, "w") as fh:
                json.dump({"GLDM": {"price": 80.0}}, fh)
            self.assertEqual(pf.load_prices(a)["GLDM"]["price"], 80.0)
        finally:
            shutil.rmtree(d)


class Compliance(unittest.TestCase):
    TODAY = datetime.date(2026, 10, 20)

    def v(self, **o):
        return cp.check_order(o, funds(), book(), self.TODAY)

    def test_the_four_rules(self):
        self.assertEqual(self.v(ticker="GLDM", side="sell", units=6.25)[0], "PASS")         # rule 2
        self.assertEqual(self.v(ticker="SPYL.L", side="buy", units=34)[0], "PASS")         # rule 1
        self.assertEqual(self.v(ticker="TSLA", side="buy", units=1)[0], "BLOCK")           # rule 4
        f = funds()
        f["instruments"]["ES3.SI"] = {"type": "fund", "sg_security": True, "constituents": 30,
                                      "top_weight_pct": 15, "verified_on": "2026-10-19"}
        self.assertEqual(cp.check_order({"ticker": "ES3.SI", "side": "buy", "usd": 100}, f, None,
                                        self.TODAY)[0], "PRECLEAR")                          # rule 3

    def test_thin_or_concentrated_funds_are_blocked(self):
        f = funds()
        f["instruments"]["SOXX"].update(constituents=29)
        self.assertEqual(cp.check_order({"ticker": "SOXX", "side": "buy", "usd": 1}, f, None, self.TODAY)[0], "BLOCK")
        f["instruments"]["SOXX"].update(constituents=34, top_weight_pct=20.5)
        self.assertEqual(cp.check_order({"ticker": "SOXX", "side": "buy", "usd": 1}, f, None, self.TODAY)[0], "BLOCK")

    def test_stale_soxx_data_blocks(self):
        later = datetime.date(2026, 11, 2)
        self.assertEqual(cp.check_order({"ticker": "SOXX", "side": "buy", "usd": 1}, funds(), None, later)[0], "BLOCK")

    def test_house_rules(self):
        self.assertEqual(self.v(ticker="D05.SI", side="sell", units=10)[0], "BLOCK")
        self.assertEqual(self.v(ticker="SLV", side="buy", units=1)[0], "BLOCK")
        self.assertEqual(self.v(ticker="SPYL.L", side="buy", units=3.5)[0], "BLOCK")
        self.assertEqual(self.v(ticker="GLDM", side="sell", units=300)[0], "BLOCK")
        self.assertEqual(self.v(ticker="CNDX.L", side="buy", units=1)[0], "BLOCK")   # not verified yet


class Tranches(unittest.TestCase):
    def setUp(self):
        self.val = pf.valuation(book(), quotes(), FX)
        with open(os.path.join(ROOT, "kc-tranches", "events.example.json")) as fh:
            self.events = json.load(fh)["events"]
        c = cfg()
        self.slice = c["gold"]["slice_usd"]
        self.weekly = c["gold"]["weekly_sell_usd"]
        self.new_money = c["new_money_sgd_per_week"] / FX

    def plan(self, day, b=None):
        return tr.build(self.val, cfg(), self.events, b or book(), datetime.date.fromisoformat(day))

    def test_a_tuesday_with_gold_far_above_target(self):
        p = self.plan("2026-10-20")
        self.assertTrue(p["gold"]["sell_needed"])
        self.assertEqual(p["verdict"]["call"], "GO")
        tue = p["rows"][1]
        sell, buy = tue["actions"]
        self.assertEqual((sell["ticker"], sell["usd"], sell["units"]), ("GLDM", self.slice, round(self.slice / 80.0, 2)))
        self.assertEqual((buy["ticker"], buy["units"]), ("SPYL.L", math.floor((self.slice + self.new_money) / 19.0)))
        self.assertIn("23:30", buy["window"])
        thu = p["rows"][3]
        self.assertEqual(thu["actions"][1]["units"], math.floor(self.slice / 19.0))
        self.assertTrue(any("jobless" in n for n in thu["notes"]))
        self.assertEqual(p["rows"][2]["actions"], [])

    def test_sales_already_done_are_not_repeated(self):
        b = book()
        b["ledger"].append({"date": "2026-10-20", "side": "sell", "ticker": "GLDM", "units": 6.25,
                            "price": 80.0, "sleeve": "kc"})
        p = self.plan("2026-10-22", b)
        sells = [a for r in p["rows"] for a in r["actions"] if a["side"] == "sell"]
        left = self.weekly - 6.25 * 80.0
        self.assertEqual(len(sells), int(math.ceil(left / self.slice)))
        self.assertAlmostEqual(sum(a["usd"] for a in sells), left, places=1)

    def test_fomc_night_pauses_and_slices_move(self):
        p = self.plan("2026-10-28")
        self.assertEqual(p["verdict"]["call"], "PAUSE")
        self.assertEqual([r["day"] for r in p["rows"] if r["actions"]], ["Thu", "Fri"])

    def test_clock_changes(self):
        self.assertEqual(tr.windows(datetime.date(2026, 10, 23))["london_close"], "23:30")
        self.assertEqual(tr.windows(datetime.date(2026, 10, 26))["london_close"], "00:30")
        self.assertEqual(tr.windows(datetime.date(2026, 10, 26))["us_open"], "21:30")
        self.assertEqual(tr.windows(datetime.date(2026, 11, 2))["us_open"], "22:30")

    def test_big_move_halves_the_slice(self):
        q = quotes()
        q["GLDM"]["prev_close"] = 83.0   # -3.6% overnight
        self.val = pf.valuation(book(), q, FX)
        p = self.plan("2026-10-20")
        self.assertEqual(p["verdict"]["call"], "ADJUST")
        self.assertEqual(p["rows"][1]["actions"][0]["usd"], self.slice / 2)

    def test_no_gold_sale_once_gold_is_near_target(self):
        b = book()
        pf.find(b, "GLDM", "kc")["units"] = 20
        self.val = pf.valuation(b, quotes(), FX)
        p = self.plan("2026-10-20")
        self.assertFalse(p["gold"]["sell_needed"])
        acts = [a for r in p["rows"] for a in r["actions"]]
        self.assertEqual([a["side"] for a in acts], ["buy"])   # just the weekly new money
        self.assertNotIn("D05.SI", [a["ticker"] for a in acts])


class Cli(unittest.TestCase):
    def test_pipeline_end_to_end(self):
        d = tempfile.mkdtemp()
        try:
            with open(os.path.join(d, "portfolio.json"), "w") as fh:
                json.dump(book(), fh)
            prices = quotes()
            prices["SGD=X"] = {"price": FX}
            with open(os.path.join(d, "prices.json"), "w") as fh:
                json.dump(prices, fh)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(pf.main(["--dir", d, "value", "--prices", os.path.join(d, "prices.json"), "--write"]), 0)
                self.assertEqual(tr.main(["--dir", d, "--date", "2026-10-20", "--write"]), 0)
                self.assertEqual(cp.main(["--dir", d, "--today", "2026-10-20"]), 0)
            self.assertIn("TODAY: GO", out.getvalue())
            with open(os.path.join(d, "orders.json")) as fh:
                self.assertEqual(len(json.load(fh)["orders"]), 2)
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
