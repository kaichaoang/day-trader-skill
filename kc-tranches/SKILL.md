---
name: kc-tranches
description: >-
  Tranche Planner for KC's slow rebalancing. Rebuilds the Monday-to-Friday
  plan from fixed rules every run, so Monday's outlook and each daily update
  agree: while gold is well above its target cap, sell a set amount of GLDM
  a week in small slices; put the proceeds plus the weekly new money into
  the most underweight target (S&P 500 via SPYL in whole units, then QQQM,
  then a bond ETF); roll missed slices forward; pause
  on nights with a major event like a Fed decision; halve a slice after a
  move above 3%. Gives every step a Singapore-time window (US open 21:30 or
  22:30, London 15:00-23:30 or 16:00-00:30 after the UK clock change) and
  today's call: GO, ADJUST, PAUSE or NONE. Use when KC asks "what should I do
  today", "this week's tranches", "should I sell gold", "when do I buy SPYL",
  or in the morning report.
argument-hint: "[--date YYYY-MM-DD]"
---

# kc-tranches

Turns the book and the rules into "what to do tonight". It writes
suggestions only. KC places every trade himself, after kc-compliance passes
it.

`${CLAUDE_SKILL_DIR}` below is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/tranches.py"                       # today, Singapore date
python3 "${CLAUDE_SKILL_DIR}/tranches.py" --date 2026-10-20
python3 "${CLAUDE_SKILL_DIR}/tranches.py" --write               # trader/tranche-plan.json + trader/orders.json
python3 "${CLAUDE_SKILL_DIR}/tranches.py" --json
```

## Files

| file | what |
| --- | --- |
| `trader/valuation.json` | from `/kc-portfolio value --write`: weights, prices, overnight moves |
| `trader/portfolio.json` | the ledger: what was already sold or bought this week |
| `trader/tranche-config.json` | targets and rules; falls back to `tranche-config.example.json` |
| `trader/events.json` | the week's events in Singapore time (`events.example.json` shows the shape) |
| `trader/tranche-plan.json`, `trader/orders.json` | written with `--write`; orders go to /kc-compliance |

## The rules (tranche-config.example.json)

- **Targets** (KC's own sleeve): a low-high % range per group in
  `targets_pct` (sp500 = VOO + SPYL with new money to SPYL, nasdaq100,
  semis, gold, bonds). DBS is hold-only and just shrinks as a share over time.
  The example file has illustrative numbers; the real ones live in
  `trader/tranche-config.json`, which git ignores.
- **New money:** `new_money_sgd_per_week`, riding on the
  first buy of the week.
- **Gold:** while gold is more than `trigger_pp_above_max` (5) points above
  the gold cap, sell `weekly_sell_usd` a week in `slice_usd`
  slices on `sell_days` (Tue, Thu), then any open day, then the spare day
  (Fri). What was already sold this week (from the ledger) is subtracted.
- **Buys** go to the first group in `buy_priority` that is below the low end
  of its target. SPYL is whole units, rounded down.
- **Pause** a night with a `pause` event between 15:00 SGT and 05:00 SGT the
  next morning (e.g. FOMC at 02:00). A `wait` event means trade after the
  release. **Halve** the day's slices if the asset moved more than 3%.
- Never DBS (cannot trade) or SLV (exited).

## Timing (Singapore time)

| | until 25 Oct 2026 | 26 Oct - 1 Nov 2026 | from 2 Nov 2026 |
| --- | --- | --- | --- |
| US session (GLDM, QQQM, SOXX, VOO) | 21:30-04:00 | 21:30-04:00 | 22:30-05:00 |
| London (SPYL) | 15:00-23:30 | 16:00-00:30 | 16:00-00:30 |

When a GLDM sale funds a SPYL buy: sell GLDM after the US open, buy SPYL
before London closes, or buy it the next afternoon. The planner works out
these clocks itself from the US and UK daylight-saving rules.

## How to use it in a conversation

1. Run /kc-portfolio `value --write` first, then refresh `trader/events.json`
   with this week's data releases, Fed events and big SOXX-constituent
   earnings in Singapore time.
2. Run `tranches.py --write`, then /kc-compliance on `trader/orders.json`.
3. Tell KC today's call in plain words: what to sell or buy, about how
   much, and the time window. Then show the rest of the week.
4. If a past day's slice was not reported as done, it is rolled forward.
   Ask KC to report fills so the plan stays right.

## Fine print

Not financial advice. The plan is arithmetic on KC's own rules. KC reviews
it and places every trade himself.
