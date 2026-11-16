# PumpFun Sniper Bot: Open-Source Solana Sniper for New pump.fun Tokens

An open-source **Solana sniper bot for pump.fun** written in Python. It watches every new PumpFun token launch in real time over gRPC and buys either right away or once a launch shows real buyer momentum. It exits with take-profit, stop-loss, trailing-stop, max-hold and graduation rules.

The bot runs on the [NoLimitNodes](https://nolimitnodes.com) decoded Solana event stream, so there is no log parsing, IDL maintenance or RPC polling. Swaps are routed with the Jupiter Swap API, then signed locally and sent through your own [NoLimitNodes Solana RPC](https://nolimitnodes.com/products/rpc-nodes).

**Paper trading is the default.** Nothing is signed or sent until you pass `--live`.

```text
[14:02:11] 🟢 PAPER BUY MOON 0.0500 SOL (10 buyers in 6s, mcap 34 SOL)
https://pump.fun/coin/MoonA...pump
[14:02:32] 💰 PAPER SELL MOON +0.0552 SOL (+110.4%) after 21s: take profit +115%
[14:03:20] 🔴 PAPER SELL DUMP -0.0110 SOL (-22.1%) after 11s: stop loss -20%
```

## What is a pump.fun sniper bot?

A pump.fun sniper bot detects new tokens the moment they are created on the PumpFun bonding curve and buys early, before most traders see them. Speed comes from the data feed, not from the bot's code. This bot gets `create`, `trade` and `graduate` events already decoded from NoLimitNodes gRPC streams, applies your filters and risk limits, and sends a swap.

## Features

| Feature | What it does | Flag |
|---|---|---|
| ⚡ Instant mode | Buy on the PumpFun `create` event | `--mode instant` |
| 🔥 Momentum mode (default) | Buy once a launch has N unique buyers within T seconds | `--momentum-buyers 10 --momentum-window 30` |
| 🎯 Take profit / stop loss | Sell at +X% or −Y% | `--take-profit 100 --stop-loss 30` |
| 📉 Trailing stop | Sell when price falls X% from its peak | `--trailing-stop 25` |
| ⏱ Max hold | Sell after N seconds, even if the token stops trading | `--max-hold 300` |
| 🎓 Graduation exit | Sell when the bonding curve completes and migrates to PumpSwap | on by default |
| 🛡 Rug filters | Skip large dev buys, blocked creators, mayhem mode, keywords, high entry market cap | `--max-dev-buy 2 --block-creators ... --exclude-keywords rug` |
| 💸 Risk caps | Max open positions and a daily realized-loss cap | `--max-positions 3 --max-daily-loss 0.5` |
| 🧪 Paper trading and replay | Simulated fills at the live curve price, or offline replay of recorded events | default, `--replay` |
| 📣 Telegram alerts | Posts every buy, sell and PnL to a chat | `--telegram` |

## Quick start

```bash
git clone https://github.com/no-limit-nodes/pumpfun-sniper-bot.git
cd pumpfun-sniper-bot
python -m pip install -r requirements.txt

export NLN_API_KEY=sk_live_...     # https://app.nolimitnodes.com/register
python run_sniper.py               # paper-trades launches with 10 buyers in 30s
```

### Try it offline (no API key)

```bash
python run_sniper.py --replay examples/sample-events.jsonl \
  --momentum-buyers 3 --exclude-keywords rug --max-dev-buy 2 --stop-loss 20
```

### Trade for real

Use a **dedicated hot wallet** that holds only what you are willing to lose.

```bash
export NLN_RPC_URL=https://...                    # your NoLimitNodes RPC URL
export SOLANA_KEYPAIR_PATH=~/.config/solana/sniper.json
# optional: export JUPITER_API_KEY=...            # https://developers.jup.ag/portal

python run_sniper.py --live --buy-sol 0.02 --max-positions 2 --stop-loss 25 --max-daily-loss 0.2
```

In live mode, the bot checks your wallet balance at startup. For each order it gets a route from Jupiter `/build`, compiles and signs a v0 transaction on your machine, sends it through your NLN RPC and waits for confirmation. Your private key never leaves the process.

## Configuration

Every flag can also be set as an environment variable (see [`.env.example`](.env.example)).

| Flag | Env | Default | Meaning |
|---|---|---|---|
| `--mode` | `MODE` | `momentum` | `momentum` or `instant` |
| `--buy-sol` | `BUY_SOL` | `0.05` | SOL spent per entry |
| `--max-positions` | `MAX_POSITIONS` | `3` | Open plus pending positions |
| `--take-profit` | `TAKE_PROFIT_PCT` | `100` | Percent gain that triggers a sell (0 = off) |
| `--stop-loss` | `STOP_LOSS_PCT` | `30` | Percent loss that triggers a sell (0 = off) |
| `--trailing-stop` | `TRAILING_STOP_PCT` | `0` | Percent drop from peak that triggers a sell (0 = off) |
| `--max-hold` | `MAX_HOLD_S` | `300` | Seconds before a forced exit (0 = off) |
| `--hold-through-graduation` | | off | Keep positions after the curve completes |
| `--momentum-buyers` | `MOMENTUM_BUYERS` | `10` | Unique buyers, not counting the creator, needed to enter |
| `--momentum-window` | `MOMENTUM_WINDOW_S` | `30` | Seconds after launch in which buyers count |
| `--max-entry-mcap` | `MAX_ENTRY_MCAP_SOL` | `60` | Skip momentum entries above this market cap (0 = off) |
| `--max-dev-buy` | `MAX_DEV_BUY_SOL` | `0` | Skip if the creator buys more than this many SOL (0 = off) |
| `--keywords` / `--exclude-keywords` | `KEYWORDS` / `EXCLUDE_KEYWORDS` | none | Name or symbol filters |
| `--block-creators` | `BLOCKED_CREATORS` | none | Creator wallets to ignore |
| `--allow-mayhem` | | off | Do not skip mayhem-mode launches |
| `--max-daily-loss` | `MAX_DAILY_LOSS_SOL` | `0.5` | Stop opening positions after this realized loss (UTC day) |
| `--live` | | off | Sign and send real transactions |
| `--slippage-bps` | `SLIPPAGE_BPS` | `1500` | Max slippage for live swaps |
| `--priority` | `PRIORITY` | `high` | Priority fee level: `medium`, `high`, `veryHigh` or `0`–`10000` |
| `--paper-cost-bps` | `PAPER_COST_BPS` | `200` | Paper mode fees plus slippage per side |
| `--telegram` | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | off | Telegram trade alerts |
| `--json` | | off | Print events as JSON lines |

## How it works

```text
NoLimitNodes gRPC (stream-1.nln.clr3.org:443)
  ├─ prod.rpc.solana.pumpfun.create   ─┐                       ┌─ PaperTrader (default)
  ├─ prod.rpc.solana.pumpfun.trade    ─┼─► SniperEngine ─► Executor ─┤
  └─ prod.rpc.solana.pumpfun.graduate ─┘   filters, positions,  └─ LiveTrader: Jupiter /build → sign → NLN RPC
                                           exits, risk caps
```

- **Entries** come from `create` (instant mode) or from counting unique buyers on `trade` (momentum mode).
- **Prices** come from the post-trade virtual reserves on every `trade` event, so take profit and stop loss react to each trade on the curve.
- **Exits** are checked on every trade for a held token and once a second for time-based rules.
- **Orders** run on a background thread with sells ahead of buys, so the stream is never blocked.

See [`docs/guide.md`](docs/guide.md) for the strategy math, latency notes and deployment.

## Repository layout

- [`run_sniper.py`](run_sniper.py): command-line entry point, executor and replay.
- [`sniper.py`](sniper.py): strategy engine with filters, positions, exits and risk caps. No network I/O.
- [`trader.py`](trader.py): `PaperTrader` and `LiveTrader` (Jupiter Swap API V2 plus NoLimitNodes RPC). Reusable.
- [`nln_stream.py`](nln_stream.py): NoLimitNodes gRPC client with reconnect and multi-topic fan-in.
- [`notify.py`](notify.py): console, JSON and Telegram output.
- [`examples/sample-events.jsonl`](examples/sample-events.jsonl): five recorded-shape launches for offline replay.
- [`tests/`](tests): engine, paper, live-transaction assembly and replay tests (`python -m unittest discover -s tests`).

## FAQ

### What is the fastest way to snipe pump.fun tokens?

Get launches from a push stream instead of polling RPC. This bot subscribes to the NoLimitNodes `prod.rpc.solana.pumpfun.create` gRPC topic and acts on each launch as it arrives. For the lowest possible latency, NoLimitNodes [Shredstream](https://nolimitnodes.com/products/shredstream) delivers raw shreds before blocks are confirmed. Pair it with a priority fee (`--priority veryHigh`) and a host close to the leader validators.

### Is it better to buy instantly or wait for momentum?

Instant mode is first in line but buys every launch, and most PumpFun tokens go to zero quickly. Momentum mode waits until a launch has real, distinct buyers (10 within 30 seconds by default), skips launches with a large creator buy, and caps the entry market cap. It enters later and at a higher price, but filters out most dead launches. Use `--replay` and paper mode to compare both on your own data.

### How does the bot calculate price and PnL?

The PumpFun bonding-curve price is `virtual_sol_reserves / virtual_token_reserves` (lamports per raw token unit). It is read from each trade event's post-trade reserves. Market cap in SOL is that price times total supply divided by 1e9. PnL is SOL received minus SOL spent. Live fills use the wallet's actual balance change, and paper fills charge `--paper-cost-bps` on both sides.

### Can it buy tokens the second they launch?

In live mode, buys are routed through the Jupiter Swap API, which supports PumpFun bonding curves. A token that is only a few hundred milliseconds old may not be routable yet. In that case the buy fails cleanly and is logged, and the bot keeps running. To send instructions straight to the PumpFun program, replace `LiveTrader.buy` with your own builder. The engine and executor do not change.

### Does it support Bonk.fun, Raydium LaunchLab or PumpSwap?

The sniper targets PumpFun launches. Sells after graduation go through Jupiter, which routes PumpSwap. NoLimitNodes also streams PumpSwap, Raydium, Orca and Meteora swaps (see the [streaming reference](https://github.com/no-limit-nodes/solana-programs-data-streaming-reference)), so you can add other venues by feeding their events into the engine.

### Is this safe to run with my main wallet?

No. Use a separate wallet funded with a small amount, keep `--max-daily-loss` and `--max-positions` low, and start in paper mode. Memecoin trading is extremely risky.

## Related NoLimitNodes resources

- [Solana copy trading bot](https://github.com/no-limit-nodes/solana-copy-trading-bot): mirror any wallet's trades across PumpFun, PumpSwap, Raydium, Orca and Meteora
- [PumpFun Telegram alert bot](https://github.com/no-limit-nodes/pumpfun-telegram-alert-bot): launch, graduation and whale alerts
- [Solana priority fee API](https://github.com/no-limit-nodes/solana-priority-fee-api): compute-unit price from landed PumpFun transactions
- [Solana streaming reference](https://github.com/no-limit-nodes/solana-programs-data-streaming-reference): every NLN topic with clients in 7 languages
- [Every Solana program decoded](https://github.com/no-limit-nodes/every-solana-program-decoded): 1,074 events across 37 programs

## Disclaimer

This software is provided for education and research. It is not financial advice. Trading memecoins can lose all of your funds, and many PumpFun tokens are scams. You are responsible for your keys, your trades and complying with the laws where you live.

## License

Released under the [MIT License](LICENSE).
