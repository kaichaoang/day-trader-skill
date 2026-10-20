# KC's ETF Rebalancer (branch `kc-etf-rebalancer`)

A fork of [Jake Schincariol's Day Trader skill](https://github.com/Jakeschincariol/day-trader-skill),
retuned for a different job: a **long-term ETF portfolio**, rebalanced slowly
in weekly tranches, for an investor in **Singapore** who must follow an
employer's personal-trading rules.

The `main` branch is the upstream day-trading pack, untouched. This branch
keeps the pack's style (plain stdlib Python, a `trader/` data folder, a
SKILL.md per job, offline tests) and swaps the day-trading flow for this one:

```
kc-portfolio value  ->  kc-tranches  ->  kc-compliance  ->  KC places the trade himself
                         (Mon-Fri plan,    (PASS / PRECLEAR /
                          Singapore time)   BLOCK)
kc-morning-report: runs the chain at 7:00 AM SGT and writes the report
trader-news, trader-alerts: kept from upstream for headlines and price alerts
```

**Nothing on this branch places an order.** There is no broker connector.
Every suggestion is checked against KC's rules, and KC reviews it and
trades at his own broker.

## The skills

| command | job | what it does |
| --- | --- | --- |
| `/kc-portfolio` | Portfolio Book | Holdings in two sleeves (KC's own and a family sleeve), average-cost fills, splits, reinvested dividends, valuation in USD and SGD with weights and P&L. |
| `/kc-compliance` | Compliance Gate | KC's four trading rules plus house rules (no DBS, no SLV rebuy, whole SPYL units). PASS, PRECLEAR or BLOCK. |
| `/kc-tranches` | Tranche Planner | Rebuilds the week's plan from the rules: gold trimmed in small slices, proceeds and weekly new money to the most underweight target, Singapore-time windows, today's GO / ADJUST / PAUSE. |
| `/kc-morning-report` | Morning Report | The 7 AM report: Monday weekly outlook, Tuesday-Friday daily update, in plain English. |
| `/trader-news` | News Monitor | Upstream. Headlines for the ETFs and big SOXX constituents (`--no-sec`). |
| `/trader-alerts` | Price Alerts | Upstream. Price levels on the ETFs; now keeps `SPYL.L` and `D05.SI` suffixes intact. |

Removed from upstream (they serve day trading, or trade single stocks,
which KC's rules forbid): scanner, entry, exit, time machine, risk, budget,
broker, analyst, Pelosi tracker.

## KC's rules, as encoded

Compliance (from KC's employer's policy, as he stated it):

1. Funds and indexes need **at least 30 constituents** and **no constituent
   above 20%** at the point of trade.
2. Individual commodities and commodity trackers (GLDM) are allowed.
3. Any **Singapore security needs pre-clearance**.
4. **Individual non-Singapore stocks are not allowed.**

House rules: DBS is hold-only; SLV was exited and is not bought back; SPYL
(London, USD line) trades in whole units.

Tranche rules (`kc-tranches/tranche-config.example.json`, illustrative
numbers): a target range per group for KC's own sleeve (S&P 500 via VOO +
SPYL with new money to SPYL, Nasdaq-100 via QQQM, semis via SOXX, gold via
GLDM, bonds). While gold is well above its cap, sell a set amount a week in
small slices. A fixed amount of new money each week. Pause on a
Fed-decision night; halve a slice after a move above 3%.

A second sleeve (money KC manages for a family member) is held in the same
account but tracked separately. It is never mixed into KC's totals,
weights or tranches.

**Real holdings, amounts and targets are not in this repo.** They live in
`trader/`, which git ignores. Every number in the examples and tests is
made up.

## Install

In Claude Code, from this branch:

```bash
git clone -b kc-etf-rebalancer https://github.com/kaichaoang/day-trader-skill.git
cp -r day-trader-skill/kc-* day-trader-skill/trader-* ~/.claude/skills/
```

Or upload a single `SKILL.md` folder as a skill in the Claude app (for
example `kc-morning-report`) if your organization allows it.

Then set up your data (this folder is git-ignored, so real holdings never
reach this public repo):

```bash
mkdir -p trader
cp kc-portfolio/portfolio.example.json  trader/portfolio.json     # then put in your real units and costs
cp kc-tranches/tranche-config.example.json trader/tranche-config.json
cp kc-tranches/events.example.json      trader/events.json        # refresh weekly
cp kc-compliance/funds.example.json     trader/funds.json         # re-verify holdings data
```

## Daily use

```bash
python3 kc-portfolio/portfolio.py trade sell GLDM 6 80.00              # record last night's fills
python3 kc-portfolio/portfolio.py trade buy SPYL.L 34 19.00
python3 kc-portfolio/portfolio.py value --write                       # or --prices trader/prices.json
python3 kc-tranches/tranches.py --write                               # today's call + the week
python3 kc-compliance/compliance.py                                   # check today's orders
```

Example output (made-up holdings, the example config):

```
Week of 2026-10-19   today 2026-10-20
Gold 56.1% (max 10%): sell ~$1000 this week (sold so far $0)
New money ~$156 -> SPYL.L (sp500)

 Mon 10-19  -
            past: anything planned here and not reported is rolled forward
>Tue 10-20  sell 6.25 GLDM (~$500) after the 21:30 SGT US open (give it ~15 min); buy 34 SPYL.L (~$656) before London closes at 23:30 SGT, or the next day from 15:00 SGT
 Wed 10-21  -
 Thu 10-22  sell 6.25 GLDM (~$500) after the 21:30 SGT US open (give it ~15 min); buy 26 SPYL.L (~$500) before London closes at 23:30 SGT, or the next day from 15:00 SGT
            trade after US jobless claims (Thu 20:30 SGT)
 Fri 10-23  -

TODAY: GO - no major event and no move above 3%
pause on a 'pause' event night (e.g. a Fed decision); halve a slice if the asset moved more than 3% overnight; never trade D05.SI, SLV
```

Tests (offline):

```bash
cd tests && python3 -m unittest
```

## Fine print

**Not financial advice.** This is software that does arithmetic on public
prices and on rules KC chose. It cannot see the future. The compliance gate
checks KC's summary of his employer's policy mechanically; his compliance
team has the final word.

**The data is free and unofficial.** Yahoo's chart endpoint can lag, change
or rate-limit. Fund holdings data in `funds.json` goes stale: re-verify it
before trading, especially SOXX. Check prices against the broker before
acting.

MIT. Original pack by [Jake Schincariol](https://opusjake.ai); this branch by KC.
