---
name: kc-portfolio
description: >-
  Portfolio Book for KC's long-term ETF portfolio. Keeps the holdings in two
  sleeves (KC's own and a family member's, held in KC's account but tracked separately),
  records fills with the average-cost method KC's broker uses (a buy blends
  the average, a sell keeps it), applies share splits, estimates reinvested
  VOO dividends after 30% US withholding, and values everything in USD and
  SGD from Yahoo quotes, a prices file or prices typed in. Prints each
  holding's units, average cost, price, day %, value, P&L % and weight, the
  group weights (S&P 500 = VOO + SPYL), and the family sleeve's P&L
  against what was put in. Use when KC says "here's my trade", "I bought / sold", "for the family sleeve",
  "update my holdings", "what's my portfolio worth", "how much am I up",
  "SOXX split", "VOO dividend", or before /kc-tranches and the morning report.
argument-hint: "[value | trade buy|sell TICKER UNITS PRICE | split | dividend]"
---

# kc-portfolio

The book every other kc- skill reads. It is information and arithmetic, not
advice, and it never places an order.

`${CLAUDE_SKILL_DIR}` below is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/portfolio.py" value                                  # live Yahoo quotes
python3 "${CLAUDE_SKILL_DIR}/portfolio.py" value --prices trader/prices.json --write
python3 "${CLAUDE_SKILL_DIR}/portfolio.py" value --price GLDM=81.94 --prev GLDM=82.46 --fx 1.2801
python3 "${CLAUDE_SKILL_DIR}/portfolio.py" trade buy SPYL.L 41 19.10                # KC's own by default
python3 "${CLAUDE_SKILL_DIR}/portfolio.py" trade sell GLDM 6 80.00
python3 "${CLAUDE_SKILL_DIR}/portfolio.py" trade buy VOO 1 700 --sleeve family     # only when KC says it is for the family sleeve
python3 "${CLAUDE_SKILL_DIR}/portfolio.py" split SOXX 2 --date 2026-11-05
python3 "${CLAUDE_SKILL_DIR}/portfolio.py" dividend VOO 1.8226 --reinvest-price 700  # preview
```

## Files

| file | what |
| --- | --- |
| `trader/portfolio.json` | positions (ticker, name, currency, group, sleeve, units, avg_cost), sleeves, ledger |
| `trader/prices.json` | optional `{TICKER: {price, prev_close}}` plus `"SGD=X"` for USD/SGD |
| `trader/valuation.json` | written by `value --write`; read by kc-tranches and the morning report |

Start from `portfolio.example.json` (illustrative numbers). `trader/` is
git-ignored, so KC's real holdings never reach the public repo.

## Tickers

Yahoo symbols, exactly: `GLDM`, `QQQM`, `SOXX`, `VOO`, `SPYL.L` (London, USD
line), `D05.SI` (DBS, priced in SGD and converted at USD/SGD). Groups:
`sp500`, `nasdaq100`, `semis`, `gold`, `bonds`, `sg_bank`.

## Rules the book follows

1. **Trades are KC's own** unless KC says the trade is for the family
   sleeve. Then, and only then, `--sleeve family`.
2. **Average cost.** Buy: new avg = (old units x old avg + units x price) /
   new units. Sell: units go down, the average stays, unless KC says the
   sale came from specific units (record that in `--note`).
3. **Selling more than a sleeve holds is refused.**
4. **Splits** multiply units by the ratio and divide the average cost, in
   every sleeve. SOXX trades split-adjusted from 5 Nov 2026: look up the
   ratio, run `split`, and tell KC the first time it applies.
5. **Dividends.** VOO pays quarterly and both sleeves reinvest. `dividend`
   previews the estimate (per share x units x 0.70 / reinvest price). Ask KC
   for the broker's new unit count; record his number with `trade buy`, or
   `--apply` the estimate only if he confirms it. SPYL accumulates inside the
   fund, so its units never change from dividends.
6. **The family sleeve** is valued on its own and measured against
   `invested_usd`. It is never part of KC's totals, weights or tranche rules.

## How to use it in a conversation

- When KC reports fills, run `trade` for each one, then `value` and show
  him the new units and average cost so he can check them against the broker.
- When the network is blocked (a cloud session), find prices with web
  search, write them to `trader/prices.json` or pass `--price`, and say where
  each price came from. A London price may be an intraday quote: say so.
- Never guess units. If KC's numbers and the book disagree, ask him.

## Fine print

Not financial advice. Yahoo's chart endpoint is unofficial and can lag;
check anything that matters against the broker.
