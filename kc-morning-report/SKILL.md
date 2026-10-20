---
name: kc-morning-report
description: >-
  KC's 7:00 AM Singapore-time portfolio report. Monday is the Weekly Outlook
  (Friday's closes, weekend news, the week's events in Singapore time, the
  week's tranche table); Tuesday to Friday is the Daily Update (overnight US
  close, latest London and SGX closes, the past 24 hours of news, today's
  tranche: go, adjust or pause). Runs /kc-portfolio, /kc-tranches and
  /kc-compliance, reads the news that matters for gold, US rates, the S&P
  500, the Nasdaq-100, semiconductors and DBS, and writes a phone-sized
  report with an opinion per holding and plain-English explanations for a
  reader who is not very financially literate. Use when KC says "morning
  report", "weekly outlook", "daily update", "how's my portfolio today",
  "what do I do today", or on the 7 AM schedule.
argument-hint: "[weekly | daily]"
---

# kc-morning-report

KC reviews every opinion personally before placing any trade. This skill
never places trades: "execution" means telling KC clearly what to do today.

## Steps

1. **Date.** Check today's date and weekday in Asia/Singapore time. Monday
   gives the Weekly Outlook; Tuesday to Friday gives the Daily Update.
2. **Holdings.** Read `trader/portfolio.json`. If KC has reported trades in
   chat or memory since it was updated, record them with /kc-portfolio
   `trade` first (his own sleeve unless he said the trade was for the family sleeve).
3. **Prices.** Run `/kc-portfolio value --write`. If live quotes fail, find
   each close with web search (one ticker per search; SPYL from the London
   USD line), write `trader/prices.json` and re-run with `--prices`. Note
   market holidays and quotes that may be intraday. On Monday also give each
   holding's change over the past week.
4. **News.** US rates, the Fed and Treasury yields, inflation data, oil and
   geopolitics, gold drivers, AI and semiconductor news and big SOXX
   constituent earnings, S&P and Nasdaq moves, DBS and Singapore banks,
   USD/SGD. Paraphrase; do not quote at length.
5. **Events.** Refresh `trader/events.json` with this week's scheduled
   events in Singapore time (`pause` for a Fed decision night; `wait` for a
   release just before the US open).
6. **Plan.** Run `/kc-tranches --write`, then `/kc-compliance`. Only show
   orders that PASS; show PRECLEAR with its warning; never show a BLOCK as
   something to do.
7. **Splits and dividends.** From 5 Nov 2026 SOXX trades split-adjusted:
   look up the ratio, run `split`, and mention it once. When VOO has paid a
   dividend since the last report, preview it with `dividend` and ask KC for
   the new unit count.

## Format

- Title: "Weekly outlook" or "Daily update", with the date.
- Headline: KC's total in USD and SGD, the day change (Monday: the week
  change too), and total unrealised P&L.
- Table: holding | units | avg cost | price | day % | value | P&L % | weight.
  Then one line with the combined S&P 500 weight (VOO + SPYL).
- **Family sleeve** (money KC manages for a family member, kept separate):
  units, average cost, value, its mix vs the `target` in portfolio.json,
  and P&L vs `invested_usd`. Suggest a rebalance only if the mix is more
  than ~5 points off target and KC has not chosen otherwise.
- **News that matters:** 3-5 bullets.
- **Opinions:** one line per holding: Add / Hold / Trim, with a reason tied
  to the news and the target mix. DBS is always Hold (cannot trade). VOO is
  Hold, because new S&P 500 money goes to SPYL. Don't chase momentum.
- **Today's tranche** (go / adjust / pause, the reason and the window), and
  Monday's table of the week's tranches with what would pause one; on other
  days, progress on the week.
- **Coming up:** key dates with Singapore times; the UK clock change (25 Oct
  2026) and the next VOO ex-dividend date when it is within two weeks.
- **What this means:** 2-4 short plain-English explanations with everyday
  analogies and no jargon, varied with the news (why rising yields hurt
  gold, what averaging in is, why trimming at a loss can still make sense,
  what a split does).
- One line asking KC to reply with any trades done (units and prices; say if a
  trade was for the family sleeve).
- A short Sources list, then: "Information to weigh, not personal financial
  advice."

Length: Monday up to about three phone screens; daily about two.

## When nobody is watching

On a schedule, deliver the report with the message tool and send a short
notification that leads with today's call. Don't ask questions: state the
assumption in the report and carry on.

## Fine print

Not financial advice. The numbers are arithmetic on public prices that can
lag; KC checks his broker before acting.
