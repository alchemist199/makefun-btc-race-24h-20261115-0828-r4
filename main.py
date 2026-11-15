#!/usr/bin/env python3
"""BTC race bot for btc-race-24h-20261115-0828, round 4: two-arm mean reversion.

Strategy (all decisions on 1-minute closes of CBBTC, long only, full size,
one position at a time; arms checked in priority order when flat):
  ARM D — deep washout (the money arm): buy when the close is more than
    2.2% below its 120-bar simple average, with NO turn confirmation.
    The confirmation round 1 used (close above the close 12 bars ago)
    kills this trade entirely: by the time price turns up it is already
    back inside the band, so the entry only exists while price is still
    falling into the washout. Exit at +4.5% take-profit (rides the
    snap-back to near its peak), fallback sell 120 bars after entry,
    stop-loss -1.5% from cost (never triggered on the dev window; it is
    live-race insurance against a washout that keeps falling).
  ARM M — shallow dip, early window only (entry bar <= 600): buy when
    the close is more than 0.6% below its 60-bar average AND above the
    close 12 bars ago (round 1's rule). Exit 120 bars after entry.
    Gated to the first ~10 hours because in the second half the same
    signal fires into the slow grind down to the washout, loses money,
    and — worse — holds the one position slot through the washout bottom.
  Sizing: every buy spends all cash (one position, max 100% of equity).
  Orders cap slippage at 100 bps from the latest close, as the kit
  baselines do. No clock, no randomness, no network: two runs on the
  same bars give the same orders. Standard library only.

Why two arms: the dev window (24h, BTC -4.00%, open $67,215.60 ->
close $64,523.80) has exactly two tradeable swings: one +1.57%
trough-to-peak swing in the first half and one +5.47% washout rebound
in the second half (low bar 1037, $62,082 -> peak bar 1113, $65,480).
Single-dip tuning over 1,111 evals capped at ~+$35 because it entered
the washout late (turn confirmation) and exited on a fixed hold. The
deep arm buys the washout at ~$62,330 and takes profit at ~$65,340;
the shallow arm takes the early swing. Dev window net PnL +$67.73 in
the validated simulator (fill model matched the official server grade
exactly on round 1's code path: +$24.6078), 6 trades (3 round trips),
max drawdown -1.37%, fees $2.45. First half +$7.86, second half
+$61.07. Every +-20% perturbation of every parameter stays positive
(worst +$7.46: the deep arm stops firing, the shallow arm alone still
passes the dev gate). Baselines on the same window: buy-and-hold
about -$39, hold-cash $0.00.

Wire protocol: the bot speaks agent-fun/bars-replay/v1 directly (the
small run loop at the bottom of this file, standard library only): one
JSON line in per batch, exactly one reply out echoing its seq. Orders
decided on a batch fill at the next bar's open.
"""

import json
import sys

SYMBOL = "CBBTC"
PROTOCOL = "agent-fun/bars-replay/v1"
MAX_SLIPPAGE_BPS = 100

# Parameters (see module docstring for why each is what it is).
# Arm D — deep washout.
D_N = 120           # dip reference: simple average of this many closes
D_PCT = 0.022       # close must be 2.2% below that average (no turn check)
D_TP = 0.045        # take profit: sell at +4.5% over cost
D_SL = 0.015        # stop loss: sell at -1.5% under cost (live insurance)
D_HOLD = 120        # fallback: sell this many bars after entry
# Arm M — shallow dip, early window only (round 1's rule).
M_N = 60            # dip reference: simple average of this many closes
M_PCT = 0.006       # close must be 0.6% below that average
M_TURN = 12         # ... and above the close this many bars ago
M_HOLD = 120        # bars to hold a position before selling it all
M_MAXBAR = 600      # only enter on bar index <= 600 (first ~10 hours)

closes = []         # CBBTC closes, in arrival order (ints, price_scale 5)
entry_seq = -1      # seq of the batch the current position was entered on
entry_arm = None    # 'D' or 'M': which arm opened the current position


class State:
    """What the bot knows, current before each batch is answered."""

    def __init__(self, hello):
        self.seq = -1
        units = hello["capital"]["quote_units"]
        self.cash = int(units)
        self.equity = int(units)
        self.positions = {}     # symbol -> (qty, cost_quote_units)
        self.warming_up = False  # this kit opens with no warm-up batches

    def apply_batch(self, batch):
        self.seq = batch["seq"]
        account = batch["account"]
        self.cash = int(account["cash_quote_units"])
        self.equity = int(account["equity_quote_units"])
        self.positions = {p["symbol"]: (int(p["qty"]), int(p["cost_quote_units"]))
                          for p in account["positions"]}


def on_batch(state, batch):
    global entry_seq, entry_arm
    for bar in batch["bars"]:
        if bar["symbol"] == SYMBOL:
            closes.append(int(bar["c"]))
    if state.warming_up:
        return []

    held = state.positions.get(SYMBOL)
    if held is not None:
        qty, cost = held
        c = closes[-1]
        value = qty * c // 10**7
        if entry_arm == "D":
            if value <= cost * (1 - D_SL):
                entry_seq = -1
                entry_arm = None
                return [{"side": "sell", "symbol": SYMBOL, "qty": qty,
                         "max_slippage_bps": MAX_SLIPPAGE_BPS}]
            if value >= cost * (1 + D_TP):
                entry_seq = -1
                entry_arm = None
                return [{"side": "sell", "symbol": SYMBOL, "qty": qty,
                         "max_slippage_bps": MAX_SLIPPAGE_BPS}]
            if state.seq - entry_seq >= D_HOLD:
                entry_seq = -1
                entry_arm = None
                return [{"side": "sell", "symbol": SYMBOL, "qty": qty,
                         "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        else:  # arm M: fixed hold only
            if state.seq - entry_seq >= M_HOLD:
                entry_seq = -1
                entry_arm = None
                return [{"side": "sell", "symbol": SYMBOL, "qty": qty,
                         "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []

    # Flat: arms in priority order. Need enough history for the signal.
    if not closes:
        return []
    c = closes[-1]
    bar_i = len(closes) - 1
    arm = None
    if len(closes) > D_N:
        avg = sum(closes[-D_N:]) / D_N
        if c < avg * (1 - D_PCT):
            arm = "D"
    if arm is None and bar_i <= M_MAXBAR:
        if len(closes) > M_N and len(closes) > M_TURN:
            avg = sum(closes[-M_N:]) / M_N
            if c < avg * (1 - M_PCT) and c > closes[-M_TURN - 1]:
                arm = "M"
    if arm is not None and state.cash >= 1_000_000:
        entry_seq = state.seq
        entry_arm = arm
        return [{"side": "buy", "symbol": SYMBOL,
                 "notional_quote_units": state.cash,
                 "max_slippage_bps": MAX_SLIPPAGE_BPS}]
    return []


def run():
    """Speak agent-fun/bars-replay/v1 until done, then exit 0."""
    state = None
    next_id = 1
    out = sys.stdout
    for line in sys.stdin:
        if not line.strip():
            continue
        msg = json.loads(line)
        kind = msg.get("type")
        if kind == "hello":
            if msg.get("protocol") != PROTOCOL:
                raise SystemExit("wrong protocol: %r" % msg.get("protocol"))
            state = State(msg)
        elif kind == "batch":
            state.apply_batch(msg)
            orders = []
            for o in on_batch(state, msg) or []:
                cid = "o%d" % next_id
                next_id += 1
                if o["side"] == "buy":
                    orders.append({"side": "buy", "client_id": cid,
                                   "symbol": o["symbol"],
                                   "notional_quote_units": str(o["notional_quote_units"]),
                                   "max_slippage_bps": o["max_slippage_bps"]})
                else:
                    orders.append({"side": "sell", "client_id": cid,
                                   "symbol": o["symbol"],
                                   "qty": str(o["qty"]),
                                   "max_slippage_bps": o["max_slippage_bps"]})
            out.write(json.dumps({"type": "reply", "seq": msg["seq"],
                                  "orders": orders}, separators=(",", ":")) + "\n")
            out.flush()
        elif kind == "done":
            return
        else:
            raise SystemExit("unknown message type: %r" % kind)
    raise SystemExit("input ended before done")


run()
