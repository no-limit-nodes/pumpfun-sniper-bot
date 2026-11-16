import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sniper import (TOPIC_CREATE, TOPIC_GRADUATE, TOPIC_TRADE, SniperConfig,  # noqa: E402
                    SniperEngine, curve_price, mcap_sol)
from trader import Fill  # noqa: E402

MINT = "9FYVRJAFa1DwtjZao34Cyfd9GYHwgDzRiQTC864ppump"
CREATOR = "Ggv9eQTn2v41TLUdW2wYsqYJuEgf5HEjxnMsqktJALLY"
T0 = 1_776_154_516


def create(**kw):
    ev = {"mint": MINT, "symbol": "CAT", "name": "the nick Pirate", "creator": CREATOR, "user": CREATOR,
          "timestamp": str(T0), "token_total_supply": "1000000000000000",
          "virtual_sol_reserves": "30000000000", "virtual_token_reserves": "1073000000000000"}
    ev.update(kw)
    return ev


def trade(user, vsr, ts=T0 + 1, buy=True, sol="500000000"):
    k = 30_000_000_000 * 1_073_000_000_000_000
    return {"mint": MINT, "user": user, "sol_amount": sol, "ix_name": "buy" if buy else "sell",
            "timestamp": str(ts), "virtual_sol_reserves": str(vsr), "virtual_token_reserves": str(k // vsr)}


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


def open_position(engine, order, price):
    sol = order.sol_lamports
    return engine.on_fill(order, Fill("buy", order.mint, sol, int(sol / price), "sig"))


class MathTest(unittest.TestCase):
    def test_launch_mcap_is_about_28_sol(self):
        self.assertAlmostEqual(mcap_sol(curve_price(create())), 27.96, places=2)


class EntryTest(unittest.TestCase):
    def test_instant_buys_on_create(self):
        e = SniperEngine(SniperConfig(mode="instant", buy_sol=0.1))
        orders = e.handle(TOPIC_CREATE, create())
        self.assertEqual([(o.side, o.sol_lamports) for o in orders], [("buy", 100_000_000)])
        self.assertEqual(e.handle(TOPIC_CREATE, create()), [])  # no double entry while pending

    def test_momentum_counts_unique_non_creator_buyers_in_window(self):
        e = SniperEngine(SniperConfig(mode="momentum", momentum_buyers=3, momentum_window_s=30))
        e.handle(TOPIC_CREATE, create())
        self.assertEqual(e.handle(TOPIC_TRADE, trade(CREATOR, 31_000_000_000)), [])
        self.assertEqual(e.handle(TOPIC_TRADE, trade("A", 31_500_000_000)), [])
        self.assertEqual(e.handle(TOPIC_TRADE, trade("A", 32_000_000_000)), [])  # repeat buyer
        self.assertEqual(e.handle(TOPIC_TRADE, trade("B", 32_500_000_000)), [])
        self.assertEqual(e.handle(TOPIC_TRADE, trade("C", 33_000_000_000, ts=T0 + 31)), [])  # too late
        orders = e.handle(TOPIC_TRADE, trade("D", 33_500_000_000, ts=T0 + 20))
        self.assertEqual(len(orders), 1)
        self.assertIn("3 buyers", orders[0].reason)

    def test_filters(self):
        cases = [
            (SniperConfig(mode="instant", keywords=["dog"]), create()),
            (SniperConfig(mode="instant", exclude_keywords=["pirate"]), create()),
            (SniperConfig(mode="instant", blocked_creators={CREATOR}), create()),
            (SniperConfig(mode="instant"), create(is_mayhem_mode=True)),
        ]
        for cfg, ev in cases:
            self.assertEqual(SniperEngine(cfg).handle(TOPIC_CREATE, ev), [], cfg)

    def test_dev_buy_cap(self):
        e = SniperEngine(SniperConfig(momentum_buyers=1, max_dev_buy_sol=1.0))
        e.handle(TOPIC_CREATE, create())
        e.handle(TOPIC_TRADE, trade(CREATOR, 33_000_000_000, sol="3000000000"))
        self.assertEqual(e.handle(TOPIC_TRADE, trade("A", 33_500_000_000)), [])

    def test_entry_mcap_cap(self):
        e = SniperEngine(SniperConfig(momentum_buyers=1, max_entry_mcap_sol=30))
        e.handle(TOPIC_CREATE, create())
        self.assertEqual(e.handle(TOPIC_TRADE, trade("A", 40_000_000_000)), [])

    def test_max_positions_counts_pending(self):
        e = SniperEngine(SniperConfig(mode="instant", max_positions=1))
        self.assertEqual(len(e.handle(TOPIC_CREATE, create())), 1)
        self.assertEqual(e.handle(TOPIC_CREATE, create(mint="Other111pump")), [])


class ExitTest(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.e = SniperEngine(SniperConfig(mode="instant", take_profit_pct=50, stop_loss_pct=20,
                                           max_hold_s=60, max_daily_loss_sol=0.05), clock=self.clock)
        order = self.e.handle(TOPIC_CREATE, create())[0]
        open_position(self.e, order, curve_price(create()))

    def _sell_reason(self, orders):
        self.assertEqual([o.side for o in orders], ["sell"])
        return orders[0].reason

    def test_take_profit(self):
        self.assertIn("take profit", self._sell_reason(self.e.handle(TOPIC_TRADE, trade("A", 37_000_000_000))))

    def test_stop_loss_then_daily_cap_halts_entries(self):
        orders = self.e.handle(TOPIC_TRADE, trade("A", 26_000_000_000, buy=False))
        self.assertIn("stop loss", self._sell_reason(orders))
        rec = self.e.on_fill(orders[0], Fill("sell", MINT, 40_000_000, 1, "sig2"))
        self.assertAlmostEqual(rec["pnl_sol"], -0.01)
        self.assertEqual(len(self.e.handle(TOPIC_CREATE, create(mint="Next111pump"))), 1)
        self.e.realized_lamports = -60_000_000  # beyond the 0.05 SOL daily cap
        self.assertEqual(self.e.handle(TOPIC_CREATE, create(mint="Last111pump")), [])

    def test_max_hold_via_tick(self):
        self.assertEqual(self.e.tick(), [])
        self.clock.t += 61
        self.assertIn("max hold", self._sell_reason(self.e.tick()))
        self.assertEqual(self.e.tick(), [])  # already closing

    def test_graduation_exit(self):
        self.assertIn("graduated", self._sell_reason(self.e.handle(TOPIC_GRADUATE, {"mint": MINT})))

    def test_failed_sell_is_retried(self):
        orders = self.e.handle(TOPIC_GRADUATE, {"mint": MINT})
        self.e.on_fill(orders[0], None, "HTTP 500")
        self.assertFalse(self.e.positions[MINT].closing)
        self.clock.t += 61
        self.assertEqual(len(self.e.tick()), 1)


class ReplayTest(unittest.TestCase):
    def test_sample_file_replays(self):
        import io
        from contextlib import redirect_stdout

        import run_sniper

        path = os.path.join(os.path.dirname(__file__), "..", "examples", "sample-events.jsonl")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = run_sniper.main(["--replay", path, "--momentum-buyers", "3", "--exclude-keywords", "rug",
                                  "--max-dev-buy", "2", "--stop-loss", "20", "--quiet"])
        self.assertEqual(rc, 0)
        self.assertIn('"closed_trades": 3', buf.getvalue())


if __name__ == "__main__":
    unittest.main()
