"""PumpFun sniper strategy: entry filters, position tracking and exits.

The engine is pure Python with no network I/O. It consumes NoLimitNodes decoded
PumpFun events and returns ``Order`` objects; the runner executes them with a
trader from ``trader.py`` and reports fills back with ``on_fill``.

Entry modes:
    instant   buy on the ``create`` event (fastest, most rugs)
    momentum  buy once a launch reaches N unique buyers within T seconds

Exits: take profit, stop loss, trailing stop, max hold time and graduation.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from trader import LAMPORTS_PER_SOL, Fill

log = logging.getLogger("sniper")

TOPIC_CREATE = "prod.rpc.solana.pumpfun.create"
TOPIC_TRADE = "prod.rpc.solana.pumpfun.trade"
TOPIC_GRADUATE = "prod.rpc.solana.pumpfun.graduate"
TOPICS = (TOPIC_CREATE, TOPIC_TRADE, TOPIC_GRADUATE)

PUMPFUN_TOKEN_DECIMALS = 6


def _int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def curve_price(event: dict) -> Optional[float]:
    """Bonding-curve spot price in lamports per raw token unit (post-trade reserves)."""
    vsr, vtr = _int(event.get("virtual_sol_reserves")), _int(event.get("virtual_token_reserves"))
    if vsr <= 0 or vtr <= 0:
        return None
    return vsr / vtr


def mcap_sol(price: Optional[float], supply_raw: int = 10**15) -> Optional[float]:
    """Market cap in SOL from a lamports-per-raw-unit price and raw supply."""
    if price is None:
        return None
    return price * supply_raw / LAMPORTS_PER_SOL


def is_buy(trade: dict) -> bool:
    if "is_buy" in trade:
        return bool(trade["is_buy"])
    return str(trade.get("ix_name", "")).lower().startswith("buy")


@dataclass
class SniperConfig:
    mode: str = "momentum"  # instant | momentum
    buy_sol: float = 0.05
    max_positions: int = 3
    take_profit_pct: float = 100.0  # sell when up this much (0 = off)
    stop_loss_pct: float = 30.0  # sell when down this much (0 = off)
    trailing_stop_pct: float = 0.0  # sell when this far below the peak (0 = off)
    max_hold_s: int = 300  # sell after this many seconds (0 = off)
    sell_on_graduation: bool = True
    momentum_buyers: int = 10
    momentum_window_s: int = 30
    max_entry_mcap_sol: float = 60.0  # skip momentum entries above this market cap (0 = off)
    max_dev_buy_sol: float = 0.0  # skip if the creator's own buy exceeds this (0 = off)
    keywords: List[str] = field(default_factory=list)
    exclude_keywords: List[str] = field(default_factory=list)
    blocked_creators: Set[str] = field(default_factory=set)
    skip_mayhem: bool = True
    max_daily_loss_sol: float = 0.5  # stop opening positions after this realized loss (0 = off)


@dataclass
class Order:
    side: str  # buy | sell
    mint: str
    sol_lamports: int = 0
    fraction: float = 1.0
    reason: str = ""
    symbol: str = ""


@dataclass
class Launch:
    mint: str
    symbol: str
    name: str
    creator: str
    created_at: float
    supply_raw: int
    buyers: Set[str] = field(default_factory=set)
    dev_buy_lamports: int = 0
    triggered: bool = False
    rejected: str = ""


@dataclass
class Position:
    mint: str
    symbol: str
    sol_in: int
    tokens: int
    entry_price: float
    opened_at: float
    last_price: float
    peak_price: float
    supply_raw: int = 10**15
    closing: bool = False

    def pnl_pct(self) -> float:
        return (self.last_price / self.entry_price - 1) * 100 if self.entry_price else 0.0


class SniperEngine:
    def __init__(self, cfg: SniperConfig, clock=time.time, max_launches: int = 5000):
        self.cfg = cfg
        self.clock = clock
        self.launches: "OrderedDict[str, Launch]" = OrderedDict()
        self.max_launches = max_launches
        self.prices: Dict[str, float] = {}
        self.positions: Dict[str, Position] = {}
        self.pending: Set[str] = set()
        self.realized_lamports = 0
        self.day = time.strftime("%Y-%m-%d", time.gmtime(clock()))
        self.closed: List[dict] = []
        self.lock = threading.RLock()

    # -- helpers -----------------------------------------------------------------

    def price(self, mint: str) -> Optional[float]:
        return self.prices.get(mint)

    def _halted(self) -> bool:
        today = time.strftime("%Y-%m-%d", time.gmtime(self.clock()))
        if today != self.day:
            self.day, self.realized_lamports = today, 0
        cap = self.cfg.max_daily_loss_sol
        return cap > 0 and -self.realized_lamports >= cap * LAMPORTS_PER_SOL

    def _keyword_reject(self, launch: Launch) -> str:
        text = f"{launch.name} {launch.symbol}".lower()
        if self.cfg.keywords and not any(k.lower() in text for k in self.cfg.keywords):
            return "no keyword match"
        if any(k.lower() in text for k in self.cfg.exclude_keywords):
            return "excluded keyword"
        return ""

    def _buy(self, launch: Launch, reason: str) -> List[Order]:
        launch.triggered = True
        if self._halted():
            log.warning("daily loss cap reached; skipping %s", launch.symbol)
            return []
        if launch.mint in self.positions or launch.mint in self.pending:
            return []
        if len(self.positions) + len(self.pending) >= self.cfg.max_positions:
            log.info("max positions open; skipping %s", launch.symbol)
            return []
        self.pending.add(launch.mint)
        return [Order("buy", launch.mint, int(self.cfg.buy_sol * LAMPORTS_PER_SOL),
                      reason=reason, symbol=launch.symbol)]

    def _exit_reason(self, pos: Position, now: float) -> str:
        c = self.cfg
        pnl = pos.pnl_pct()
        if c.take_profit_pct and pnl >= c.take_profit_pct:
            return f"take profit {pnl:+.0f}%"
        if c.stop_loss_pct and pnl <= -c.stop_loss_pct:
            return f"stop loss {pnl:+.0f}%"
        if c.trailing_stop_pct and pos.peak_price > pos.entry_price:
            drop = (1 - pos.last_price / pos.peak_price) * 100
            if drop >= c.trailing_stop_pct:
                return f"trailing stop {drop:.0f}% off peak ({pnl:+.0f}%)"
        if c.max_hold_s and now - pos.opened_at >= c.max_hold_s:
            return f"max hold {c.max_hold_s}s ({pnl:+.0f}%)"
        return ""

    def _close(self, pos: Position, reason: str) -> List[Order]:
        pos.closing = True
        return [Order("sell", pos.mint, fraction=1.0, reason=reason, symbol=pos.symbol)]

    # -- event handlers ----------------------------------------------------------

    def handle(self, topic: str, event: dict) -> List[Order]:
        with self.lock:
            if topic == TOPIC_CREATE:
                return self.on_create(event)
            if topic == TOPIC_TRADE:
                return self.on_trade(event)
            if topic == TOPIC_GRADUATE:
                return self.on_graduate(event)
            return []

    def on_create(self, ev: dict) -> List[Order]:
        mint = ev.get("mint", "")
        if not mint:
            return []
        launch = Launch(
            mint=mint,
            symbol=str(ev.get("symbol", ""))[:16] or mint[:6],
            name=str(ev.get("name", ""))[:64],
            creator=ev.get("creator") or ev.get("user", ""),
            created_at=float(_int(ev.get("timestamp"), int(self.clock()))),
            supply_raw=_int(ev.get("token_total_supply"), 10**15) or 10**15,
        )
        self.launches[mint] = launch
        while len(self.launches) > self.max_launches:
            self.launches.popitem(last=False)
        price = curve_price(ev)
        if price:
            self.prices[mint] = price

        if launch.creator in self.cfg.blocked_creators:
            launch.rejected = "blocked creator"
        elif self.cfg.skip_mayhem and ev.get("is_mayhem_mode"):
            launch.rejected = "mayhem mode"
        else:
            launch.rejected = self._keyword_reject(launch)
        if launch.rejected:
            log.debug("skip %s: %s", launch.symbol, launch.rejected)
            return []
        if self.cfg.mode == "instant":
            return self._buy(launch, "new launch")
        return []

    def on_trade(self, ev: dict) -> List[Order]:
        mint = ev.get("mint", "")
        price = curve_price(ev)
        if not mint or price is None:
            return []
        self.prices[mint] = price
        orders: List[Order] = []

        launch = self.launches.get(mint)
        if launch and not launch.triggered and not launch.rejected and self.cfg.mode == "momentum" and is_buy(ev):
            user = ev.get("user", "")
            ts = float(_int(ev.get("timestamp"), int(self.clock())))
            if user == launch.creator:
                launch.dev_buy_lamports += _int(ev.get("sol_amount"))
                cap = self.cfg.max_dev_buy_sol
                if cap and launch.dev_buy_lamports > cap * LAMPORTS_PER_SOL:
                    launch.rejected = f"dev bought {launch.dev_buy_lamports / LAMPORTS_PER_SOL:.2f} SOL"
            elif user and ts - launch.created_at <= self.cfg.momentum_window_s:
                launch.buyers.add(user)
                if len(launch.buyers) >= self.cfg.momentum_buyers:
                    mcap = mcap_sol(price, launch.supply_raw) or 0
                    if self.cfg.max_entry_mcap_sol and mcap > self.cfg.max_entry_mcap_sol:
                        launch.rejected = f"mcap {mcap:.0f} SOL above entry cap"
                    else:
                        secs = ts - launch.created_at
                        orders += self._buy(launch, f"{len(launch.buyers)} buyers in {secs:.0f}s, mcap {mcap:.0f} SOL")

        pos = self.positions.get(mint)
        if pos and not pos.closing:
            pos.last_price = price
            pos.peak_price = max(pos.peak_price, price)
            reason = self._exit_reason(pos, self.clock())
            if reason:
                orders += self._close(pos, reason)
        return orders

    def on_graduate(self, ev: dict) -> List[Order]:
        pos = self.positions.get(ev.get("mint", ""))
        if pos and not pos.closing and self.cfg.sell_on_graduation:
            return self._close(pos, "graduated to AMM")
        return []

    def tick(self) -> List[Order]:
        """Time-based exits for positions that have stopped trading."""
        with self.lock:
            now = self.clock()
            out: List[Order] = []
            for pos in list(self.positions.values()):
                if not pos.closing:
                    reason = self._exit_reason(pos, now)
                    if reason:
                        out += self._close(pos, reason)
            return out

    # -- fills -------------------------------------------------------------------

    def on_fill(self, order: Order, fill: Optional[Fill], error: str = "") -> Optional[dict]:
        """Update state after the runner executes an order. Returns a closed-trade record."""
        with self.lock:
            if order.side == "buy":
                self.pending.discard(order.mint)
                if fill is None or fill.token_raw <= 0:
                    return None
                entry = fill.sol_lamports / fill.token_raw
                launch = self.launches.get(order.mint)
                self.positions[order.mint] = Position(
                    mint=order.mint, symbol=order.symbol, sol_in=fill.sol_lamports, tokens=fill.token_raw,
                    entry_price=entry, opened_at=self.clock(), last_price=self.prices.get(order.mint, entry),
                    peak_price=entry, supply_raw=launch.supply_raw if launch else 10**15)
                return None
            pos = self.positions.get(order.mint)
            if pos is None:
                return None
            if fill is None:
                if "balance to sell" in error or "holds no" in error:
                    self.positions.pop(order.mint, None)  # nothing left to sell
                else:
                    pos.closing = False  # retry on the next price update or tick
                return None
            self.positions.pop(order.mint, None)
            pnl = fill.sol_lamports - pos.sol_in
            self.realized_lamports += pnl
            record = {
                "mint": pos.mint, "symbol": pos.symbol, "reason": order.reason,
                "sol_in": pos.sol_in / LAMPORTS_PER_SOL, "sol_out": fill.sol_lamports / LAMPORTS_PER_SOL,
                "pnl_sol": pnl / LAMPORTS_PER_SOL, "pnl_pct": pnl / pos.sol_in * 100 if pos.sol_in else 0.0,
                "held_s": round(self.clock() - pos.opened_at, 1), "signature": fill.signature,
            }
            self.closed.append(record)
            return record

    def summary(self) -> dict:
        with self.lock:
            wins = sum(1 for r in self.closed if r["pnl_sol"] > 0)
            return {
                "closed_trades": len(self.closed),
                "wins": wins,
                "realized_pnl_sol": round(sum(r["pnl_sol"] for r in self.closed), 6),
                "open_positions": len(self.positions),
                "launches_seen": len(self.launches),
            }
