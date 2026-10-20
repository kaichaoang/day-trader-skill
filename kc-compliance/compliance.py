#!/usr/bin/env python3
"""KC's compliance gate. Every suggested order passes through here before it
reaches KC, and a BLOCK is final.

  python3 compliance.py                              # trader/orders.json vs trader/funds.json
  python3 compliance.py --orders my.json --json
  python3 compliance.py check SOXX buy --usd 300     # one order, quick
  python3 compliance.py --today 2026-10-20           # pin the date for staleness

KC's rules (from his employer's personal-trading policy, as KC stated them):
  1. Funds and indexes: at least 30 constituents AND no constituent above
     20% weight at the point of trade.
  2. Individual commodities and commodity trackers (GLDM, SLV) are allowed.
  3. Any Singapore security needs pre-clearance before trading.
  4. Individual non-Singapore stocks are not allowed.
Plus KC's own house rules: DBS cannot be traded at all; SLV is exited and is
not bought back; London lines (SPYL.L) trade in whole units; you cannot sell
more than a sleeve holds.

Verdicts: PASS, PRECLEAR (allowed only after pre-clearance), BLOCK.
Exit code: 0 all PASS, 3 something needs pre-clearance, 4 something BLOCKed.
"""

import argparse
import datetime
import json
import os
import sys

MIN_CONSTITUENTS = 30
MAX_TOP_WEIGHT = 20.0


def read_json(path, default=None):
    if not os.path.exists(path):
        if default is not None:
            return default
        raise SystemExit("error: %s not found" % path)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def held(portfolio, ticker, sleeve):
    for p in (portfolio or {}).get("positions", []):
        if p["ticker"].upper() == ticker.upper() and p.get("sleeve", "kc") == sleeve:
            return p["units"]
    return 0.0


def check_order(order, funds, portfolio=None, today=None):
    """-> (verdict, [reasons], [warnings])"""
    today = today or datetime.date.today()
    t = str(order.get("ticker", "")).upper()
    side = str(order.get("side", "")).lower()
    sleeve = order.get("sleeve", "kc")
    reasons, warns = [], []
    if side not in ("buy", "sell"):
        return "BLOCK", ["side must be buy or sell"], warns
    if not t:
        return "BLOCK", ["no ticker"], warns
    info = funds.get("instruments", {}).get(t)
    if info is None:
        return "BLOCK", ["%s is not in funds.json: add it with verified type, constituents and top weight first" % t], warns
    kind = info.get("type")

    if info.get("tradable") is False:
        reasons.append("%s cannot be traded by KC (%s)" % (t, info.get("why", "hold only")))
    if side == "buy" and info.get("no_rebuy"):
        reasons.append("%s was exited; KC does not buy it back" % t)

    if kind == "stock":
        if info.get("sg_security"):
            pass  # handled below as pre-clearance
        else:
            reasons.append("rule 4: individual non-Singapore stocks are not allowed")
    elif kind == "fund":
        n, top = info.get("constituents"), info.get("top_weight_pct")
        if n is None or top is None:
            reasons.append("rule 1: constituents/top weight unknown for %s; verify first" % t)
        else:
            if n < MIN_CONSTITUENTS:
                reasons.append("rule 1: %s has %d constituents (< %d)" % (t, n, MIN_CONSTITUENTS))
            if top > MAX_TOP_WEIGHT:
                reasons.append("rule 1: %s top constituent %.2f%% (> %.0f%%)" % (t, top, MAX_TOP_WEIGHT))
            if top > MAX_TOP_WEIGHT - 3:
                warns.append("%s top weight %.2f%% is close to the 20%% cap" % (t, top))
            if n < MIN_CONSTITUENTS + 5:
                warns.append("%s has only %d constituents; a reshuffle could breach 30" % (t, n))
        checked = info.get("verified_on")
        max_age = info.get("max_age_days", 30)
        if checked:
            age = (today - datetime.date.fromisoformat(checked)).days
            if age > max_age:
                msg = "%s holdings data is %d days old (limit %d): re-verify at the point of trade" % (t, age, max_age)
                (reasons if info.get("strict") else warns).append(msg)
        else:
            reasons.append("%s has no verified_on date" % t)
    elif kind == "commodity":
        pass  # rule 2
    else:
        reasons.append("unknown instrument type %r for %s" % (kind, t))

    units = order.get("units")
    if units is not None and info.get("whole_units") and abs(units - round(units)) > 1e-9:
        reasons.append("%s trades in whole units only (got %s)" % (t, units))
    if side == "sell" and units is not None and portfolio is not None:
        h = held(portfolio, t, sleeve)
        if units > h + 1e-9:
            reasons.append("sell %s %s but sleeve %s holds %s" % (units, t, sleeve, h))

    if reasons:
        return "BLOCK", reasons, warns
    if info.get("sg_security"):
        return "PRECLEAR", ["rule 3: Singapore security: get pre-clearance before trading"], warns
    return "PASS", [], warns


def run(orders, funds, portfolio, today):
    out = []
    for o in orders:
        v, r, w = check_order(o, funds, portfolio, today)
        out.append(dict(o, verdict=v, reasons=r, warnings=w))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default="trader")
    ap.add_argument("--orders")
    ap.add_argument("--funds")
    ap.add_argument("--today")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("quick", nargs="*", help="check TICKER SIDE")
    ap.add_argument("--units", type=float)
    ap.add_argument("--usd", type=float)
    ap.add_argument("--sleeve", default="kc")
    a = ap.parse_args(argv)
    today = datetime.date.fromisoformat(a.today) if a.today else datetime.date.today()
    here = os.path.dirname(os.path.abspath(__file__))
    funds_path = a.funds or os.path.join(a.dir, "funds.json")
    if not os.path.exists(funds_path):
        funds_path = os.path.join(here, "funds.example.json")
    funds = read_json(funds_path)
    portfolio = read_json(os.path.join(a.dir, "portfolio.json"), {}) or None
    if a.quick:
        if len(a.quick) != 3 or a.quick[0] != "check":
            raise SystemExit("usage: compliance.py check TICKER buy|sell [--units N | --usd N]")
        orders = [{"ticker": a.quick[1], "side": a.quick[2], "units": a.units, "usd": a.usd, "sleeve": a.sleeve}]
    else:
        doc = read_json(a.orders or os.path.join(a.dir, "orders.json"))
        orders = doc.get("orders", doc) if isinstance(doc, dict) else doc
    res = run(orders, funds, portfolio, today)
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        for r in res:
            size = ("%s units" % r["units"]) if r.get("units") is not None else ("$%s" % r.get("usd"))
            print("%-8s %-4s %-6s %-12s %s" % (r["verdict"], r["side"], r["ticker"], size,
                                              "; ".join(r["reasons"]) or "ok"))
            for w in r["warnings"]:
                print("         warning: " + w)
    verdicts = {r["verdict"] for r in res}
    return 4 if "BLOCK" in verdicts else 3 if "PRECLEAR" in verdicts else 0


if __name__ == "__main__":
    sys.exit(main())
