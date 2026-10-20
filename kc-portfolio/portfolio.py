#!/usr/bin/env python3
"""KC's portfolio book: holdings by sleeve, average-cost trades, splits,
reinvested dividends, and a valuation in USD and SGD.

Standard library only (Python 3.8+). Reads and writes trader/portfolio.json;
`value --write` also writes trader/valuation.json for kc-tranches.

  python3 portfolio.py value                       # live quotes (Yahoo chart JSON)
  python3 portfolio.py value --price GLDM=81.94 --prev GLDM=82.46 --fx 1.2801
  python3 portfolio.py value --prices trader/prices.json --write --json
  python3 portfolio.py trade buy SPYL.L 41 19.10            # KC's own by default
  python3 portfolio.py trade sell GLDM 7.3 81.90
  python3 portfolio.py trade buy VOO 1 700 --sleeve family   # only when KC says so
  python3 portfolio.py split SOXX 2 --date 2026-11-05
  python3 portfolio.py dividend VOO 1.8226 --reinvest-price 700         # preview only
  python3 portfolio.py dividend VOO 1.8226 --reinvest-price 700 --apply

Average cost, the way KC's broker does it: a buy blends the average (weighted
by units); a sell lowers units and leaves the average unchanged.
"""

import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (kc-portfolio; personal use)"
YAHOO_HOSTS = ("query2.finance.yahoo.com", "query1.finance.yahoo.com")
FX_SYMBOL = "SGD=X"   # Yahoo: SGD per 1 USD
DEFAULT_DIR = "trader"


class BookError(Exception):
    pass


# ---------------------------------------------------------------- files

def read_json(path, default=None):
    if not os.path.exists(path):
        if default is not None:
            return default
        raise BookError("%s not found (copy portfolio.example.json to start)" % path)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, doc):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------- book maths

def find(book, ticker, sleeve):
    for p in book.get("positions", []):
        if p["ticker"].upper() == ticker.upper() and p.get("sleeve", "kc") == sleeve:
            return p
    return None


def apply_trade(book, side, ticker, units, price, sleeve="kc", date=None, note=None, meta=None):
    """Average-cost update. Returns the position after the trade."""
    if units <= 0 or price <= 0:
        raise BookError("units and price must be positive")
    side = side.lower()
    if side not in ("buy", "sell"):
        raise BookError("side must be buy or sell")
    pos = find(book, ticker, sleeve)
    if side == "sell":
        if pos is None or pos["units"] + 1e-9 < units:
            held = pos["units"] if pos else 0
            raise BookError("cannot sell %s %s from sleeve %s: only %s held" % (units, ticker, sleeve, held))
        pos["units"] = round(pos["units"] - units, 6)
    else:
        if pos is None:
            pos = dict(meta or {}, ticker=ticker.upper(), sleeve=sleeve, units=0.0, avg_cost=0.0)
            book.setdefault("positions", []).append(pos)
        new_units = pos["units"] + units
        pos["avg_cost"] = round((pos["units"] * pos["avg_cost"] + units * price) / new_units, 6)
        pos["units"] = round(new_units, 6)
    book.setdefault("ledger", []).append({
        "date": date or datetime.date.today().isoformat(), "side": side, "ticker": ticker.upper(),
        "units": units, "price": price, "sleeve": sleeve, "note": note or ""})
    return pos


def apply_split(book, ticker, ratio, date=None):
    """A 2-for-1 split is ratio 2: units x2, average cost /2, for every sleeve."""
    if ratio <= 0:
        raise BookError("ratio must be positive")
    hit = []
    for p in book.get("positions", []):
        if p["ticker"].upper() == ticker.upper():
            p["units"] = round(p["units"] * ratio, 6)
            p["avg_cost"] = round(p["avg_cost"] / ratio, 6)
            hit.append(p)
    if not hit:
        raise BookError("no %s position to split" % ticker)
    book.setdefault("ledger", []).append({"date": date or datetime.date.today().isoformat(),
                                          "side": "split", "ticker": ticker.upper(), "ratio": ratio})
    return hit


def dividend_estimate(book, ticker, per_share, reinvest_price, withholding_pct=30.0):
    """Units each sleeve gains if the dividend is reinvested after withholding tax."""
    out = []
    for p in book.get("positions", []):
        if p["ticker"].upper() == ticker.upper() and p["units"] > 0:
            cash = per_share * p["units"] * (1 - withholding_pct / 100.0)
            out.append({"sleeve": p.get("sleeve", "kc"), "units_before": p["units"],
                        "cash_after_tax": round(cash, 4), "new_units": round(cash / reinvest_price, 6)})
    return out


# ---------------------------------------------------------------- quotes

def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except urllib.error.URLError as e:
        raise BookError("could not reach Yahoo: %s" % e.reason)


def parse_yahoo(text, sym):
    try:
        res = json.loads(text)["chart"]["result"]
        m = res[0]["meta"]
    except (ValueError, KeyError, TypeError, IndexError):
        raise BookError("Yahoo has no data for %s" % sym)
    price = m.get("regularMarketPrice")
    if price is None:
        raise BookError("Yahoo has no price for %s" % sym)
    t = m.get("regularMarketTime")
    return {"price": float(price),
            "prev_close": m.get("chartPreviousClose") or m.get("previousClose"),
            "currency": m.get("currency"),
            "time": datetime.datetime.fromtimestamp(t, datetime.timezone.utc).isoformat() if t else ""}


def fetch_quote(sym, offline=None):
    """Symbols are passed as-is (SPYL.L, D05.SI and SGD=X keep their suffix)."""
    if offline:
        path = os.path.join(offline, "yahoo-%s.json" % sym.replace("=", "_"))
        with open(path, encoding="utf-8") as fh:
            return parse_yahoo(fh.read(), sym)
    q = urllib.request.quote(sym, safe="")
    for host in YAHOO_HOSTS:
        code, text = _get("https://%s/v8/finance/chart/%s?range=5d&interval=1d" % (host, q))
        if code == 200:
            return parse_yahoo(text, sym)
        time.sleep(1)
    raise BookError("Yahoo did not answer for %s" % sym)


def parse_pairs(items, what):
    out = {}
    for it in items or []:
        if "=" not in it:
            raise BookError("%s needs SYMBOL=NUMBER, got %r" % (what, it))
        k, v = it.rsplit("=", 1)
        out[k.upper()] = float(v)
    return out


def load_prices(path):
    """Either {SYM: {price, prev_close}} or trader-alerts' {prices: {SYM: p}, detail: {SYM: {prev_close}}}."""
    doc = read_json(path, {})
    if isinstance(doc.get("prices"), dict):
        detail = doc.get("detail", {})
        return {k.upper(): {"price": v, "prev_close": (detail.get(k) or {}).get("prev_close")}
                for k, v in doc["prices"].items()}
    return {k.upper(): v for k, v in doc.items() if isinstance(v, dict) and "price" in v}


def gather_quotes(book, a):
    """Manual prices win, then a prices file, then live Yahoo quotes."""
    tickers = sorted({p["ticker"].upper() for p in book["positions"] if p["units"] > 0})
    manual = parse_pairs(a.price, "--price")
    prev = parse_pairs(a.prev, "--prev")
    filed = load_prices(a.prices) if a.prices else {}
    quotes, errors = {}, []
    for t in tickers:
        if t in manual:
            quotes[t] = {"price": manual[t], "prev_close": prev.get(t), "source": "manual"}
        elif t in filed:
            f = filed[t]
            quotes[t] = {"price": float(f["price"]), "prev_close": f.get("prev_close"), "source": "file"}
        else:
            try:
                q = fetch_quote(t, a.offline)
                q["source"] = "yahoo"
                quotes[t] = q
            except BookError as e:
                errors.append(str(e))
        if t in quotes and t in prev:
            quotes[t]["prev_close"] = prev[t]
    fx = a.fx
    if fx is None and FX_SYMBOL.upper() in filed:
        fx = float(filed[FX_SYMBOL.upper()]["price"])
    if fx is None:
        try:
            fx = fetch_quote(FX_SYMBOL, a.offline)["price"]
        except (BookError, OSError) as e:
            fx = book.get("fx", {}).get("USDSGD")
            errors.append("USD/SGD: %s; using the book's fallback %s" % (e, fx))
    if not fx:
        raise BookError("no USD/SGD rate: pass --fx")
    return quotes, float(fx), errors


# ---------------------------------------------------------------- valuation

def valuation(book, quotes, fx):
    rows = []
    for p in book["positions"]:
        if p["units"] <= 0:
            continue
        q = quotes.get(p["ticker"].upper())
        if not q:
            continue
        to_usd = (1.0 / fx) if p.get("currency", "USD") == "SGD" else 1.0
        price, prev = q["price"], q.get("prev_close")
        value = p["units"] * price * to_usd
        cost = p["units"] * p["avg_cost"] * to_usd
        rows.append({
            "ticker": p["ticker"], "name": p.get("name", p["ticker"]), "sleeve": p.get("sleeve", "kc"),
            "group": p.get("group", "other"), "currency": p.get("currency", "USD"),
            "units": p["units"], "avg_cost": p["avg_cost"], "price": price, "prev_close": prev,
            "value_usd": round(value, 2), "cost_usd": round(cost, 2),
            "day_usd": round(p["units"] * (price - prev) * to_usd, 2) if prev else None,
            "day_pct": round((price / prev - 1) * 100, 2) if prev else None,
            "pnl_usd": round(value - cost, 2), "pnl_pct": round((value / cost - 1) * 100, 2) if cost else None})
    sleeves = {}
    for s, meta in book.get("sleeves", {"kc": {}}).items():
        mine = [r for r in rows if r["sleeve"] == s]
        total = sum(r["value_usd"] for r in mine)
        cost = sum(r["cost_usd"] for r in mine)
        day = sum(r["day_usd"] or 0 for r in mine)
        groups = {}
        for r in mine:
            r["weight_pct"] = round(r["value_usd"] / total * 100, 2) if total else 0
            groups[r["group"]] = round(groups.get(r["group"], 0) + r["weight_pct"], 2)
        out = {"label": meta.get("label", s), "total_usd": round(total, 2), "total_sgd": round(total * fx, 2),
               "day_usd": round(day, 2), "day_pct": round(day / (total - day) * 100, 2) if total - day else 0,
               "pnl_usd": round(total - cost, 2), "pnl_pct": round((total / cost - 1) * 100, 2) if cost else 0,
               "group_weights": groups}
        if meta.get("invested_usd"):
            inv = meta["invested_usd"]
            out["invested_usd"] = inv
            out["pnl_vs_invested_usd"] = round(total - inv, 2)
            out["pnl_vs_invested_pct"] = round((total / inv - 1) * 100, 2)
        sleeves[s] = out
    return {"as_of": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "fx_usdsgd": fx, "positions": rows, "sleeves": sleeves}


def fmt_money(x):
    return "-" if x is None else "{:,.0f}".format(x)


def print_valuation(v):
    print("USD/SGD %.4f" % v["fx_usdsgd"])
    for s, sl in v["sleeves"].items():
        print("\n== %s ==" % sl["label"])
        print("%-8s %10s %9s %9s %7s %9s %7s %6s" % ("holding", "units", "avg", "price", "day%", "value$", "P&L%", "wt%"))
        for r in v["positions"]:
            if r["sleeve"] != s:
                continue
            print("%-8s %10.4f %9.2f %9.2f %7s %9s %7s %6.1f" % (
                r["name"], r["units"], r["avg_cost"], r["price"],
                "-" if r["day_pct"] is None else "%+.2f" % r["day_pct"], fmt_money(r["value_usd"]),
                "-" if r["pnl_pct"] is None else "%+.1f" % r["pnl_pct"], r["weight_pct"]))
        print("total $%s (S$%s)  day %+.0f (%+.2f%%)  P&L %+.0f (%+.1f%%)" % (
            fmt_money(sl["total_usd"]), fmt_money(sl["total_sgd"]), sl["day_usd"], sl["day_pct"],
            sl["pnl_usd"], sl["pnl_pct"]))
        print("by group: " + ", ".join("%s %.1f%%" % kv for kv in sorted(sl["group_weights"].items())))
        if "invested_usd" in sl:
            print("vs invested $%s: %+.0f (%+.1f%%)" % (fmt_money(sl["invested_usd"]),
                                                    sl["pnl_vs_invested_usd"], sl["pnl_vs_invested_pct"]))


# ---------------------------------------------------------------- commands

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=DEFAULT_DIR, help="data folder (default trader/)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("value", help="value the book")
    v.add_argument("--price", action="append", help="SYMBOL=PRICE (repeatable)")
    v.add_argument("--prev", action="append", help="SYMBOL=PREVIOUS_CLOSE (repeatable)")
    v.add_argument("--prices", help="JSON {SYMBOL: {price, prev_close}}")
    v.add_argument("--fx", type=float, help="SGD per USD")
    v.add_argument("--offline", help="folder of saved Yahoo JSON (tests)")
    v.add_argument("--json", action="store_true")
    v.add_argument("--write", action="store_true", help="write trader/valuation.json")

    t = sub.add_parser("trade", help="record a fill")
    t.add_argument("side", choices=["buy", "sell"])
    t.add_argument("ticker")
    t.add_argument("units", type=float)
    t.add_argument("price", type=float)
    t.add_argument("--sleeve", default="kc", help="kc (default) or another sleeve, only when KC says so")
    t.add_argument("--date")
    t.add_argument("--note")

    s = sub.add_parser("split", help="apply a share split")
    s.add_argument("ticker")
    s.add_argument("ratio", type=float, help="new shares per old share (2-for-1 = 2)")
    s.add_argument("--date")

    d = sub.add_parser("dividend", help="estimate (or apply) a reinvested dividend")
    d.add_argument("ticker")
    d.add_argument("per_share", type=float)
    d.add_argument("--reinvest-price", type=float, required=True)
    d.add_argument("--withholding", type=float, default=30.0)
    d.add_argument("--apply", action="store_true", help="only after KC confirms the units")
    d.add_argument("--date")

    a = ap.parse_args(argv)
    path = os.path.join(a.dir, "portfolio.json")
    try:
        book = read_json(path)
        if a.cmd == "value":
            quotes, fx, errors = gather_quotes(book, a)
            val = valuation(book, quotes, fx)
            val["errors"] = errors
            if a.write:
                write_json(os.path.join(a.dir, "valuation.json"), val)
            if a.json:
                print(json.dumps(val, indent=2))
            else:
                print_valuation(val)
                for e in errors:
                    print("warning: " + e, file=sys.stderr)
            missing = [p["ticker"] for p in book["positions"] if p["units"] > 0 and p["ticker"].upper() not in quotes]
            return 2 if missing else 0
        if a.cmd == "trade":
            meta = None
            if not find(book, a.ticker, a.sleeve):
                other = next((p for p in book["positions"] if p["ticker"].upper() == a.ticker.upper()), None)
                if other:
                    meta = {k: other[k] for k in ("name", "group", "currency") if k in other}
            pos = apply_trade(book, a.side, a.ticker, a.units, a.price, a.sleeve, a.date, a.note, meta)
            write_json(path, book)
            print("%s %s: now %.4f units @ %.4f avg (%s sleeve)" % (a.side, pos["ticker"], pos["units"],
                                                                  pos["avg_cost"], a.sleeve))
        elif a.cmd == "split":
            for p in apply_split(book, a.ticker, a.ratio, a.date):
                print("%s (%s): %.4f units @ %.4f avg" % (p["ticker"], p.get("sleeve", "kc"), p["units"], p["avg_cost"]))
            write_json(path, book)
        elif a.cmd == "dividend":
            est = dividend_estimate(book, a.ticker, a.per_share, a.reinvest_price, a.withholding)
            for e in est:
                print("%s sleeve: +%.4f units (US$%.2f after %.0f%% tax)" % (e["sleeve"], e["new_units"],
                                                                         e["cash_after_tax"], a.withholding))
            if a.apply:
                for e in est:
                    apply_trade(book, "buy", a.ticker, e["new_units"], a.reinvest_price, e["sleeve"], a.date,
                                "dividend reinvested")
                write_json(path, book)
                print("applied")
            else:
                print("preview only: ask KC for the broker's new unit count, then --apply")
    except BookError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
