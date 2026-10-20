---
name: kc-compliance
description: >-
  Compliance Gate for KC's personal-trading rules. Checks every suggested
  order before KC sees it: funds and indexes need at least 30 constituents
  and no constituent above 20% at the point of trade (SOXX's index has only
  ~30 names, so its data must be fresh); commodities and commodity trackers
  are allowed; any Singapore security needs pre-clearance; individual
  non-Singapore stocks are never allowed. Also enforces KC's house rules:
  DBS cannot be traded at all, SLV is exited and not bought back, London
  lines like SPYL trade in whole units, no selling more than a sleeve holds,
  and any ticker not in the registry is blocked until it is verified. Prints
  PASS, PRECLEAR or BLOCK with the reason. Use when KC asks "can I buy X",
  "is this allowed", "does this break my rules", "check this fund", or
  before showing any trade suggestion, always.
argument-hint: "[check TICKER buy|sell] [--units N | --usd N]"
---

# kc-compliance

The gate between a suggestion and KC. It never places an order. A BLOCK is final: the order is not
shown as something to do. PRECLEAR means "allowed only after KC gets
pre-clearance", and must be shown with that warning.

`${CLAUDE_SKILL_DIR}` below is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/compliance.py"                        # trader/orders.json
python3 "${CLAUDE_SKILL_DIR}/compliance.py" check SOXX buy --usd 300
python3 "${CLAUDE_SKILL_DIR}/compliance.py" check SPYL.L buy --units 41
python3 "${CLAUDE_SKILL_DIR}/compliance.py" --json --today 2026-10-20
```

Exit code: 0 all PASS, 3 something needs pre-clearance, 4 something BLOCKed.

## Files

| file | what |
| --- | --- |
| `trader/orders.json` | `{"orders": [{ticker, side, units or usd, sleeve}]}` (kc-tranches writes it) |
| `trader/funds.json` | the instrument registry; falls back to `funds.example.json` here |
| `trader/portfolio.json` | to refuse a sell larger than the sleeve holds |

## The rules

| rule | verdict |
| --- | --- |
| 1. Fund or index with < 30 constituents, or a constituent > 20% | BLOCK |
| 1. Fund data older than `max_age_days` | warning; BLOCK when `strict` (SOXX: 7 days) |
| 2. Commodity or commodity tracker (GLDM) | PASS |
| 3. Singapore security (`sg_security`) | PRECLEAR |
| 4. Individual non-Singapore stock | BLOCK |
| DBS (`tradable: false`) | BLOCK, buy or sell |
| SLV buy (`no_rebuy`) | BLOCK |
| Fractional units on a `whole_units` line (SPYL.L) | BLOCK |
| Sell more than the sleeve holds | BLOCK |
| Ticker not in the registry | BLOCK until added with verified data |

Warnings (not blocks) flag a top weight within 3 points of 20%, or fewer
than 35 constituents.

## Keeping the registry honest

Before trading SOXX, or any fund whose data has gone stale, look up the
current holdings count and the top weight (iShares, stockanalysis.com
holdings page, justETF), update `constituents`, `top_weight_pct`,
`top_name`, `verified_on` and `source`, and re-run. When suggesting a new
fund (for example the ~10% bond sleeve, or CNDX instead of QQQM), add it
with verified numbers first. Never fill in numbers you have not checked.

## Fine print

These rules are KC's summary of his employer's policy as he gave it. The
gate checks them mechanically. It is not legal or compliance advice, and
KC's compliance team has the final word. Not financial advice.
