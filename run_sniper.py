#!/usr/bin/env python3
"""Run the PumpFun sniper bot on the NoLimitNodes decoded event stream.

Paper trading is the default. Nothing is signed or sent unless you pass --live.

Examples:
    # paper-trade launches that reach 10 buyers in 30s
    python run_sniper.py

    # paper-trade every new launch instantly, 0.02 SOL each
    python run_sniper.py --mode instant --buy-sol 0.02

    # offline replay (no API key needed)
    python run_sniper.py --replay examples/sample-events.jsonl --momentum-buyers 3

    # real trades with a dedicated hot wallet
    python run_sniper.py --live --buy-sol 0.02 --max-positions 2
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import os
import queue
import signal
import sys
import threading

from notify import Notifier
from sniper import TOPICS, Order, SniperConfig, SniperEngine
from trader import LAMPORTS_PER_SOL, LiveTrader, NlnRpc, PaperTrader, TradeError, load_keypair

log = logging.getLogger("run_sniper")


def csv(value: str):
    return [v.strip() for v in value.split(",") if v.strip()]


def parse_args(argv=None):
    env = os.environ.get
    p = argparse.ArgumentParser(description="PumpFun sniper bot on NoLimitNodes gRPC streams.")
    p.add_argument("--mode", choices=("momentum", "instant"), default=env("MODE", "momentum"),
                   help="momentum: buy after N unique buyers; instant: buy on the create event")
    p.add_argument("--buy-sol", type=float, default=float(env("BUY_SOL", 0.05)), help="SOL per entry")
    p.add_argument("--max-positions", type=int, default=int(env("MAX_POSITIONS", 3)))
    p.add_argument("--take-profit", type=float, default=float(env("TAKE_PROFIT_PCT", 100)),
                   help="take profit in percent (0 = off)")
    p.add_argument("--stop-loss", type=float, default=float(env("STOP_LOSS_PCT", 30)),
                   help="stop loss in percent (0 = off)")
    p.add_argument("--trailing-stop", type=float, default=float(env("TRAILING_STOP_PCT", 0)),
                   help="sell when this many percent below the peak (0 = off)")
    p.add_argument("--max-hold", type=int, default=int(env("MAX_HOLD_S", 300)),
                   help="sell after this many seconds (0 = off)")
    p.add_argument("--hold-through-graduation", action="store_true",
                   help="keep positions when the bonding curve completes")
    p.add_argument("--momentum-buyers", type=int, default=int(env("MOMENTUM_BUYERS", 10)))
    p.add_argument("--momentum-window", type=int, default=int(env("MOMENTUM_WINDOW_S", 30)))
    p.add_argument("--max-entry-mcap", type=float, default=float(env("MAX_ENTRY_MCAP_SOL", 60)),
                   help="skip momentum entries above this market cap in SOL (0 = off)")
    p.add_argument("--max-dev-buy", type=float, default=float(env("MAX_DEV_BUY_SOL", 0)),
                   help="skip launches whose creator buys more than this many SOL (0 = off)")
    p.add_argument("--keywords", type=csv, default=csv(env("KEYWORDS", "")))
    p.add_argument("--exclude-keywords", type=csv, default=csv(env("EXCLUDE_KEYWORDS", "")))
    p.add_argument("--block-creators", type=csv, default=csv(env("BLOCKED_CREATORS", "")))
    p.add_argument("--allow-mayhem", action="store_true", help="do not skip mayhem-mode launches")
    p.add_argument("--max-daily-loss", type=float, default=float(env("MAX_DAILY_LOSS_SOL", 0.5)),
                   help="stop opening positions after this realized loss in SOL (0 = off)")
    p.add_argument("--live", action="store_true", help="sign and send real transactions")
    p.add_argument("--slippage-bps", type=int, default=int(env("SLIPPAGE_BPS", 1500)))
    p.add_argument("--priority", default=env("PRIORITY", "high"),
                   help="Jupiter computeUnitPricePercentile: medium, high, veryHigh or 0-10000")
    p.add_argument("--paper-cost-bps", type=int, default=int(env("PAPER_COST_BPS", 200)),
                   help="paper mode: fees + slippage charged per side")
    p.add_argument("--telegram", action="store_true", help="send trade alerts to Telegram")
    p.add_argument("--json", action="store_true", help="print events as JSON lines")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--replay", metavar="FILE", help="JSONL of {\"topic\":..., \"event\":...} to replay offline")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def build_config(a) -> SniperConfig:
    return SniperConfig(
        mode=a.mode, buy_sol=a.buy_sol, max_positions=a.max_positions,
        take_profit_pct=a.take_profit, stop_loss_pct=a.stop_loss, trailing_stop_pct=a.trailing_stop,
        max_hold_s=a.max_hold, sell_on_graduation=not a.hold_through_graduation,
        momentum_buyers=a.momentum_buyers, momentum_window_s=a.momentum_window,
        max_entry_mcap_sol=a.max_entry_mcap, max_dev_buy_sol=a.max_dev_buy,
        keywords=a.keywords, exclude_keywords=a.exclude_keywords,
        blocked_creators=set(a.block_creators), skip_mayhem=not a.allow_mayhem,
        max_daily_loss_sol=a.max_daily_loss)


class Executor:
    """Runs orders off the stream thread. Sells are executed before buys."""

    def __init__(self, engine: SniperEngine, trader, notifier: Notifier, inline: bool = False):
        self.engine, self.trader, self.notifier = engine, trader, notifier
        self.inline = inline
        self.q: "queue.PriorityQueue" = queue.PriorityQueue()
        self._seq = itertools.count()
        if not inline:
            threading.Thread(target=self._run, daemon=True, name="executor").start()

    def submit(self, orders) -> None:
        for order in orders:
            if self.inline:
                self.execute(order)
            else:
                self.q.put((0 if order.side == "sell" else 1, next(self._seq), order))

    def _run(self) -> None:
        while True:
            _, _, order = self.q.get()
            self.execute(order)

    def execute(self, order: Order) -> None:
        tag = "PAPER" if self.trader.paper else "LIVE"
        try:
            if order.side == "buy":
                fill = self.trader.buy(order.mint, order.sol_lamports)
            else:
                fill = self.trader.sell(order.mint, order.fraction)
        except TradeError as exc:
            self.engine.on_fill(order, None, str(exc))
            self.notifier.send("error", f"⚠️ {tag} {order.side} {order.symbol} failed: {exc}",
                               {"mint": order.mint})
            return
        record = self.engine.on_fill(order, fill)
        if order.side == "buy":
            self.notifier.send("buy", f"🟢 {tag} BUY {order.symbol} {fill.sol:.4f} SOL ({order.reason})\n"
                               f"https://pump.fun/coin/{order.mint}",
                               {"mint": order.mint, "sol": fill.sol, "signature": fill.signature})
        elif record:
            icon = "💰" if record["pnl_sol"] > 0 else "🔴"
            self.notifier.send("sell", f"{icon} {tag} SELL {order.symbol} {record['pnl_sol']:+.4f} SOL "
                               f"({record['pnl_pct']:+.1f}%) after {record['held_s']:.0f}s: {order.reason}",
                               record)


def replay(path: str, engine: SniperEngine, executor: Executor, clock_box: list) -> None:
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            rec = json.loads(line)
            ts = rec["event"].get("timestamp") or rec["event"].get("block_time")
            if ts:
                clock_box[0] = float(ts)
            executor.submit(engine.handle(rec["topic"], rec["event"]))
            executor.submit(engine.tick())


def main(argv=None) -> int:
    a = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = build_config(a)
    notifier = Notifier(json_lines=a.json, quiet=a.quiet,
                        telegram_token=os.environ.get("TELEGRAM_BOT_TOKEN", "") if a.telegram else "",
                        telegram_chat=os.environ.get("TELEGRAM_CHAT_ID", "") if a.telegram else "")

    if a.replay:
        clock_box = [0.0]
        engine = SniperEngine(cfg, clock=lambda: clock_box[0])
        trader = PaperTrader(engine.price, a.paper_cost_bps)
        replay(a.replay, engine, Executor(engine, trader, notifier, inline=True), clock_box)
        print(json.dumps(engine.summary(), indent=2))
        return 0

    import nln_stream

    api_key = nln_stream.require_api_key()
    engine = SniperEngine(cfg)
    if a.live:
        keypair = load_keypair()
        rpc = NlnRpc()
        bal = rpc.balance(str(keypair.pubkey())) / LAMPORTS_PER_SOL
        log.warning("LIVE mode: wallet %s holds %.4f SOL", keypair.pubkey(), bal)
        if bal < cfg.buy_sol + 0.01:
            raise SystemExit(f"wallet balance {bal:.4f} SOL is below --buy-sol plus fees")
        trader = LiveTrader(keypair, rpc, slippage_bps=a.slippage_bps, priority=a.priority)
    else:
        log.info("PAPER mode: no transactions will be sent (use --live for real trades)")
        trader = PaperTrader(engine.price, a.paper_cost_bps)
    executor = Executor(engine, trader, notifier)

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    def ticker():
        while not stop.wait(1.0):
            executor.submit(engine.tick())

    threading.Thread(target=ticker, daemon=True, name="ticker").start()
    log.info("mode=%s buy=%.3f SOL tp=%s%% sl=%s%% max_hold=%ss", cfg.mode, cfg.buy_sol,
             cfg.take_profit_pct, cfg.stop_loss_pct, cfg.max_hold_s)
    try:
        for topic, event in nln_stream.merge(list(TOPICS), api_key, stop=stop):
            executor.submit(engine.handle(topic, event))
    except nln_stream.StreamAuthError as exc:
        log.error("NoLimitNodes rejected the API key: %s", exc)
        return 2
    finally:
        print(json.dumps(engine.summary(), indent=2), file=sys.stderr)
        if engine.positions:
            log.warning("%d position(s) still open: %s", len(engine.positions),
                        ", ".join(p.symbol for p in engine.positions.values()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
