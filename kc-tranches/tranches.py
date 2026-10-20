#!/usr/bin/env python3
"""KC's weekly tranche planner. Rebuilds the Monday-to-Friday plan from the
tranche rules every time it runs, so the Monday outlook and every daily
update land on the same plan, and says what to do TODAY (go / adjust / pause)
with the time window in Singapore time.

  python3 tranches.py                          # today (Singapore date)
  python3 tranches.py --date 2026-10-20 --json
  python3 tranches.py --write                  # trader/tranche-plan.json + today's trader/orders.json

Reads (all in trader/):
  valuation.json        from kc-portfolio `value --write` (weights, prices, overnight moves)
  portfolio.json        the ledger: trades already done this week
  tranche-config.json   targets and rules (tranche-config.example.json if missing)
  events.json           scheduled events with Singapore times (optional)

It never places an order. It writes suggestions that kc-compliance checks
and KC executes himself.
"""

import argparse
import datetime
import json
import math
import os
import sys

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
SGT = datetime.timezone(datetime.timedelta(hours=8))


def read_json(path, default=None):
    if not os.path.exists(path):
        if default is not None:
            return default
        raise SystemExit("error: %s not found" % path)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, doc):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")


# ---------------------------------------------------------------- clocks

def nth_sunday(year, month, n):
    d = datetime.date(year, month, 1)
    d += datetime.timedelta(days=(6 - d.weekday()) % 7)
    return d + datetime.timedelta(weeks=n - 1)


def last_sunday(year, month):
    d = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1) if month < 12 else datetime.date(year, 12, 31)
    return d - datetime.timedelta(days=(d.weekday() + 1) % 7)


def us_dst(d):
    return nth_sunday(d.year, 3, 2) <= d < nth_sunday(d.year, 11, 1)


def uk_bst(d):
    return last_sunday(d.year, 3) <= d < last_sunday(d.year, 10)


def windows(d):
    """Session times in Singapore time for the trading night that starts on date d."""
    us = ("21:30", "04:00") if us_dst(d) else ("22:30", "05:00")
    ldn = ("15:00", "23:30") if uk_bst(d) else ("16:00", "00:30")
    return {"us_open": us[0], "us_close": us[1], "london_open": ldn[0], "london_close": ldn[1]}


# ---------------------------------------------------------------- events

def events_for_night(events, d):
    """Events from 15:00 SGT on d to 05:00 SGT on d+1 (that day's London + US sessions)."""
    start = datetime.datetime(d.year, d.month, d.day, 15, 0, tzinfo=SGT)
    end = start + datetime.timedelta(hours=14)
    out = []
    for e in events:
        t = datetime.datetime.fromisoformat("%sT%s" % (e["date_sgt"], e.get("time_sgt", "00:00"))).replace(tzinfo=SGT)
        if start <= t < end:
            out.append(dict(e, when=t))
    return out


# ---------------------------------------------------------------- plan

def position(val, ticker, sleeve="kc"):
    for r in val["positions"]:
        if r["ticker"].upper() == ticker.upper() and r["sleeve"] == sleeve:
            return r
    return None


def price_of(val, cfg, ticker):
    r = position(val, ticker) or next((p for p in val["positions"] if p["ticker"].upper() == ticker.upper()), None)
    if r:
        return r["price"]
    return cfg.get("fallback_prices", {}).get(ticker)


def buy_target(val, cfg):
    """Most underweight group in priority order, measured against the low end of its target."""
    weights = val["sleeves"]["kc"]["group_weights"]
    for g in cfg["buy_priority"]:
        lo = cfg["targets_pct"][g][0]
        if weights.get(g, 0) < lo:
            return g, cfg["buy_with"].get(g)
    g = cfg["buy_priority"][0]
    return g, cfg["buy_with"].get(g)


def done_this_week(book, monday, ticker, side):
    total = 0.0
    for t in (book or {}).get("ledger", []):
        try:
            d = datetime.date.fromisoformat(t["date"])
        except (KeyError, ValueError):
            continue
        if (monday <= d <= monday + datetime.timedelta(days=4) and t.get("ticker", "").upper() == ticker.upper()
                and t.get("side") == side and t.get("sleeve", "kc") == "kc"):
            total += t["units"] * t["price"]
    return total


def build(val, cfg, events, book, today):
    monday = today - datetime.timedelta(days=today.weekday())
    fx = val["fx_usdsgd"]
    kc = val["sleeves"]["kc"]
    g = cfg["gold"]
    gold_w = kc["group_weights"].get("gold", 0)
    gold_max = cfg["targets_pct"]["gold"][1]
    total = kc["total_usd"]
    gold_price = price_of(val, cfg, g["ticker"])
    move_cap = cfg.get("pause_move_pct", 3)

    # weekly gold sale, less what was already sold this week
    sell_needed = gold_w > gold_max + g["trigger_pp_above_max"]
    weekly = min(g["weekly_sell_usd"], max(0.0, (gold_w - gold_max) / 100 * total)) if sell_needed else 0.0
    sold = done_this_week(book, monday, g["ticker"], "sell")
    remaining = max(0.0, weekly - sold)
    slice_usd = g["slice_usd"]
    n_slices = int(math.ceil(remaining / slice_usd - 1e-9)) if remaining > 0 else 0
    new_money_usd = cfg["new_money_sgd_per_week"] / fx
    group, buy_ticker = buy_target(val, cfg)
    buy_price = price_of(val, cfg, buy_ticker) if buy_ticker else None
    whole = buy_ticker in cfg.get("whole_units", [])
    bought = done_this_week(book, monday, buy_ticker, "buy") if buy_ticker else 0.0

    rows = []
    for i, name in enumerate(DAYS):
        d = monday + datetime.timedelta(days=i)
        ev = events_for_night(events, d)
        rows.append({"day": name, "date": d.isoformat(), "windows": windows(d),
                     "status": "past" if d < today else "today" if d == today else "planned",
                     "events": [{"time_sgt": e["when"].strftime("%a %H:%M"), "label": e["label"],
                                 "impact": e.get("impact", "info")} for e in ev],
                     "paused": any(e.get("impact") == "pause" for e in ev),
                     "actions": [], "notes": []})

    # place the remaining gold slices: preferred sell days first, then any open day; today or later only
    open_rows = [r for r in rows if r["status"] != "past" and not r["paused"]]
    preferred = [r for r in open_rows if r["day"] in g["sell_days"]]
    others = [r for r in open_rows if r["day"] not in g["sell_days"] and r["day"] != cfg.get("spare_day")]
    spare = [r for r in open_rows if r["day"] == cfg.get("spare_day")]
    slots = (preferred + others + spare)[:n_slices]
    slots.sort(key=lambda r: r["date"])
    left = remaining
    money_left = max(0.0, new_money_usd - bought) if bought < new_money_usd else 0.0
    for r in slots:
        amt = min(slice_usd, left)
        left -= amt
        units = round(amt / gold_price, 2) if gold_price else None
        r["actions"].append({"side": "sell", "ticker": g["ticker"], "usd": round(amt, 2), "units": units,
                             "window": "after the %s SGT US open (give it ~15 min)" % r["windows"]["us_open"]})
        cash = amt + money_left
        money_left = 0.0
        r["actions"].append(buy_action(buy_ticker, group, cash, buy_price, whole, r["windows"], same_night=True))

    # new money with no gold sale to ride on: first open day from today
    if money_left > 1 and open_rows:
        r = next((x for x in open_rows if not x["actions"]), open_rows[0])
        r["actions"].append(buy_action(buy_ticker, group, money_left, buy_price, whole, r["windows"], same_night=False))
        r["notes"].append("weekly new money SGD %.0f ~ USD %.0f" % (cfg["new_money_sgd_per_week"], new_money_usd))

    for r in rows:
        for e in r["events"]:
            if e["impact"] == "pause":
                r["notes"].append("pause: %s (%s SGT)" % (e["label"], e["time_sgt"]))
            elif e["impact"] == "wait":
                r["notes"].append("trade after %s (%s SGT)" % (e["label"], e["time_sgt"]))
        if r["status"] == "past" and not r["actions"]:
            r["notes"].append("past: anything planned here and not reported is rolled forward")

    # today's verdict
    t = next((r for r in rows if r["status"] == "today"), None)
    verdict = {"call": "NONE", "why": "weekend: no trading today" if today.weekday() > 4 else "nothing planned today"}
    if t:
        moves = {}
        for a in t["actions"]:
            p = position(val, a["ticker"]) or {}
            if p.get("day_pct") is not None:
                moves[a["ticker"]] = p["day_pct"]
        big = {k: v for k, v in moves.items() if abs(v) > move_cap}
        if t["paused"]:
            verdict = {"call": "PAUSE", "why": "; ".join(n for n in t["notes"] if n.startswith("pause"))}
            t["actions"] = []
        elif big:
            for a in t["actions"]:
                if a.get("usd"):
                    a["usd"] = round(a["usd"] / 2, 2)
                    if a.get("units") is not None:
                        a["units"] = math.floor(a["units"] / 2) if a["ticker"] in cfg.get("whole_units", []) \
                            else round(a["units"] / 2, 2)
            verdict = {"call": "ADJUST", "why": "halved: overnight move above %s%% (%s)" % (
                move_cap, ", ".join("%s %+.1f%%" % kv for kv in big.items()))}
        elif t["actions"]:
            waits = [n for n in t["notes"] if n.startswith("trade after")]
            verdict = {"call": "GO", "why": "no major event and no move above %s%%" % move_cap
                       + ("; " + "; ".join(waits) if waits else "")}
    return {"today": today.isoformat(), "week_of": monday.isoformat(),
            "gold": {"weight_pct": gold_w, "target_max_pct": gold_max, "sell_needed": sell_needed,
                     "weekly_sell_usd": round(weekly, 2), "sold_this_week_usd": round(sold, 2)},
            "buy_group": group, "buy_ticker": buy_ticker, "new_money_usd": round(new_money_usd, 2),
            "rows": rows, "verdict": verdict,
            "pause_rules": "pause on a 'pause' event night (e.g. a Fed decision); halve a slice if the asset "
                           "moved more than %s%% overnight; never trade %s" % (move_cap, ", ".join(cfg.get("never_trade", [])))}


def buy_action(ticker, group, usd, price, whole, w, same_night):
    if ticker is None:
        return {"side": "buy", "ticker": None, "usd": round(usd, 2), "units": None,
                "window": "pick a broad bond ETF first and run it through kc-compliance", "group": group}
    units = (math.floor(usd / price) if whole else round(usd / price, 4)) if price else None
    if ticker.endswith(".L"):
        win = "before London closes at %s SGT, or the next day from %s SGT" % (w["london_close"], w["london_open"])
        if not same_night:
            win = "%s-%s SGT (London)" % (w["london_open"], w["london_close"])
    else:
        win = "after the %s SGT US open" % w["us_open"]
    return {"side": "buy", "ticker": ticker, "usd": round(usd, 2), "units": units, "window": win, "group": group}


def print_plan(p):
    v = p["verdict"]
    print("Week of %s   today %s" % (p["week_of"], p["today"]))
    g = p["gold"]
    print("Gold %.1f%% (max %.0f%%): %s" % (g["weight_pct"], g["target_max_pct"],
          "sell ~$%.0f this week (sold so far $%.0f)" % (g["weekly_sell_usd"], g["sold_this_week_usd"])
          if g["sell_needed"] else "no rebalancing sale needed"))
    print("New money ~$%.0f -> %s (%s)\n" % (p["new_money_usd"], p["buy_ticker"], p["buy_group"]))
    for r in p["rows"]:
        acts = "; ".join("%s %s %s (~$%.0f) %s" % (a["side"], "" if a["units"] is None else a["units"],
                                                  a["ticker"], a["usd"], a["window"]) for a in r["actions"]) or "-"
        mark = ">" if r["status"] == "today" else " "
        print("%s%s %s  %s" % (mark, r["day"], r["date"][5:], acts))
        for n in r["notes"]:
            print("            " + n)
    print("\nTODAY: %s - %s" % (v["call"], v["why"]))
    print(p["pause_rules"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default="trader")
    ap.add_argument("--date", help="Singapore date YYYY-MM-DD (default: today in Singapore)")
    ap.add_argument("--config")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    here = os.path.dirname(os.path.abspath(__file__))
    today = datetime.date.fromisoformat(a.date) if a.date else datetime.datetime.now(SGT).date()
    cfg_path = a.config or os.path.join(a.dir, "tranche-config.json")
    if not os.path.exists(cfg_path):
        cfg_path = os.path.join(here, "tranche-config.example.json")
    cfg = read_json(cfg_path)
    val = read_json(os.path.join(a.dir, "valuation.json"))
    events = read_json(os.path.join(a.dir, "events.json"), {"events": []}).get("events", [])
    book = read_json(os.path.join(a.dir, "portfolio.json"), {})
    plan = build(val, cfg, events, book, today)
    if a.write:
        write_json(os.path.join(a.dir, "tranche-plan.json"), plan)
        todays = next((r for r in plan["rows"] if r["status"] == "today"), {"actions": []})
        write_json(os.path.join(a.dir, "orders.json"),
                   {"date": plan["today"], "orders": [dict(x, sleeve="kc") for x in todays["actions"] if x["ticker"]]})
    if a.json:
        print(json.dumps(plan, indent=2))
    else:
        print_plan(plan)
    return 0


if __name__ == "__main__":
    sys.exit(main())
