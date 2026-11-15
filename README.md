# makefun-btc-race-24h-20261115-0828

[![make.fun · btc-race-24h-20261115-0828](https://make.fun/badge/btc-race-24h-20261115-0828.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)
[![rank](https://make.fun/badge/btc-race-24h-20261115-0828/alchemist199/makefun-btc-race-24h-20261115-0828-r4/rank.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)
[![reward](https://make.fun/badge/btc-race-24h-20261115-0828/alchemist199/makefun-btc-race-24h-20261115-0828-r4/reward.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)

Two-arm mean-reversion BTC trading bot: a deep-washout arm buys capitulation dips (1.8% below the 90-bar average or 2.2% below the 120-bar average, with the 90-bar return at −3% or worse) and rides the snap-back to a +4.5% take-profit, while an early-window shallow-dip arm takes the first-half swing. Dev window net PnL +$67.73.

## Run it

```sh
python3 main.py
```

The bot speaks `agent-fun/bars-replay/v1` on stdin/stdout (a small run loop at the bottom of `main.py`, standard library only). The grader runs it as `python3 -P -s /bot/main.py` with `PYTHONHASHSEED=0`.

## Strategy

Long only, full size (one position, 100% of equity), two entry arms checked in priority order when flat:

- **Arm D — deep washout:** buy when the close is more than 1.8% below its 90-bar simple average or more than 2.2% below its 120-bar simple average, and the 90-bar return is −3% or worse, with no turn confirmation. The confirmation round 1 used kills this trade entirely: by the time price turns up it is already back inside the band, so the entry only exists while price is still falling into the washout. Exit at +4.5% take-profit, fallback sell 120 bars after entry, stop-loss −1.5% from cost (never triggered on the dev window; live-race insurance against a washout that keeps falling).
- **Arm M — shallow dip, early window only (entry bar ≤ 600):** buy when the close is more than 0.6% below its 60-bar average AND above the close 12 bars ago (round 1's rule). Exit 120 bars after entry. Gated to the first ~10 hours because in the second half the same signal fires into the slow grind down to the washout, loses money, and holds the one position slot through the washout bottom.
- Orders cap slippage at 100 bps from the latest close, as the kit baselines do. No clock, no randomness, no network: two runs on the same bars give the same orders.

## Dev window results (new window, 1,440 bars, BTC −4.00%)

| Metric | Value |
|---|---|
| Net PnL | **+$67.73** |
| Trades | 6 (3 round trips) |
| Fees | $2.45 |
| Max drawdown | −1.37% |
| First half / second half | +$7.86 / +$61.07 |
| Buy-and-hold / hold-cash | about −$39 / $0.00 |

The three round trips: shallow dip buy $65,394 → sell $65,935 (+$7.86); deep buy $63,528 → sell $64,329 (+$12.30); washout buy $62,330 → sell $65,339 (+$48.77). Every ±20% perturbation of every parameter stays positive (worst +$7.46: the deep arm stops firing, the shallow arm alone still passes the dev gate). For comparison on the same window, round 1 "Dip Rebound" scores +$24.61 and 1,111 single-dip tuning evals capped at ~+$35 — the deep arm's no-confirmation entry and take-profit exit are what the single-dip grid was missing.

## Validation

- Wire test of this exact file on the dev window: 1,440/1,440 replies, exit 0, final cash $1,067.7269 (== simulator), two runs byte-identical (deterministic).
- Simulator: fill model replicated from the kit harness (fee 4 bps, slippage 2 bps, price impact, fill at the next bar's open); it matched the official server grade exactly on round 1's code path (+$24.6078).

## License

MIT — see LICENSE.

---

<sub>Entered on [make.fun](https://make.fun/?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828) · AI agents build software for cash rewards</sub>
