<h1 align="center">PumpFun Sniper Bot: Open-Source Solana Sniper for New pump.fun Tokens</h1>

<p align="center">
  <b>Watch every new pump.fun launch over gRPC, buy instantly or on real buyer momentum, and exit with take-profit, stop-loss, trailing-stop, max-hold and graduation rules.</b><br>
  <sub>A Python sniper bot with a pure strategy engine, a paper trader, a Jupiter-routed live trader and offline replay, running on the <a href="https://nolimitnodes.com">NoLimitNodes</a> decoded PumpFun event stream. Paper trading by default.</sub>
</p>

<p align="center">
  <a href="./LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square"></a>
  <a href="#repo-layout"><img alt="Python" src="https://img.shields.io/badge/language-Python-3776AB?style=flat-square"></a>
  <a href="#how-it-works"><img alt="3 PumpFun topics" src="https://img.shields.io/badge/PumpFun%20topics-3-green?style=flat-square"></a>
  <a href="#quickstart-run-the-sniper-in-paper-mode"><img alt="Paper trading by default" src="https://img.shields.io/badge/default-paper%20trading-orange?style=flat-square"></a>
  <a href="https://nolimitnodes.com"><img alt="Powered by NoLimitNodes" src="https://img.shields.io/badge/powered%20by-NoLimitNodes-FBDE00?style=flat-square&labelColor=000000"></a>
  <a href="#how-it-works"><img alt="gRPC TLS" src="https://img.shields.io/badge/transport-gRPC%2FTLS-brightgreen?style=flat-square"></a>
  <a href="https://solana.com"><img alt="Solana Mainnet" src="https://img.shields.io/badge/solana-mainnet-9945FF?style=flat-square"></a>
</p>

<p align="center">
  <a href="#quickstart-run-the-sniper-in-paper-mode">Quickstart</a> ·
  <a href="#features">Features</a> ·
  <a href="#configuration">Configuration</a> ·
  <a href="#strategy-entries-exits-and-risk-limits">Strategy</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#faq">FAQ</a> ·
  <a href="#disclaimer">Disclaimer</a>
</p>

---

> [!WARNING]
> **Paper trading is the default. Nothing is signed or sent until you pass `--live`.**
> This software is for education and research. It is not financial advice. Trading memecoins can lose all of your funds, and many PumpFun tokens are scams. If you trade live, use a **dedicated hot wallet** that holds only what you are willing to lose, and keep `--max-positions` and `--max-daily-loss` low.

## What this is

An open-source **PumpFun sniper bot** for Solana, written in Python. It watches every new pump.fun token launch in real time over gRPC and buys either right away (instant mode) or once a launch shows real buyer momentum (momentum mode, the default). It exits with take-profit, stop-loss, trailing-stop, max-hold and graduation rules, and enforces a position cap and a daily loss cap.

The bot runs on the [NoLimitNodes](https://nolimitnodes.com) decoded Solana event stream, so there is no log parsing, IDL maintenance or RPC polling. In live mode, swaps are routed with the Jupiter Swap API, then signed locally and sent through your own [NoLimitNodes Solana RPC](https://nolimitnodes.com/products/rpc-nodes). Your private key never leaves the process.

**If you've been looking for any of these, you're in the right place:**

- An open-source **pump.fun sniper bot** in Python
- A **Solana memecoin sniper** that reacts to new token launches as they are created
- A **PumpFun bot with take profit and stop loss**, plus trailing stop and max hold
- A **pump.fun momentum bot** that waits for N unique buyers before entering
- A **PumpFun graduation exit** that sells when the bonding curve migrates to PumpSwap
- **PumpFun rug filters**: dev-buy size, blocked creators, mayhem mode, keywords, entry market cap
- A **paper trading bot for pump.fun** with offline replay of recorded events
- A **Jupiter swap bot** that signs v0 transactions locally and sends through your own RPC
- **Telegram trade alerts** for every buy, sell and PnL

## Who this is for

- **Solana trading bot developers** who want a working sniper to read, fork and extend instead of starting from raw transaction parsing
- **Memecoin traders** who want to test instant and momentum entries in paper mode before risking SOL
- **Strategy researchers** who want a network-free engine they can drive from recorded JSONL events
- **Developers learning NoLimitNodes gRPC streams** who want a real multi-topic client with reconnect and fan-in

## Quickstart: run the sniper in paper mode

### Step 1. Get an API key

Register at **[app.nolimitnodes.com/register](https://app.nolimitnodes.com/register)**. You get a 5-day free Pro trial, no credit card required. Copy your API key from the dashboard.

### Step 2. Clone, install and paper-trade

```bash
git clone https://github.com/no-limit-nodes/pumpfun-sniper-bot.git
cd pumpfun-sniper-bot
python -m pip install -r requirements.txt

export NLN_API_KEY=sk_live_...     # https://app.nolimitnodes.com/register
python run_sniper.py               # paper-trades launches with 10 buyers in 30s
```

Other paper-mode examples from `run_sniper.py`:

```bash
# paper-trade every new launch instantly, 0.02 SOL each
python run_sniper.py --mode instant --buy-sol 0.02
```

### Try it offline (no API key)

```bash
python run_sniper.py --replay examples/sample-events.jsonl \
  --momentum-buyers 3 --exclude-keywords rug --max-dev-buy 2 --stop-loss 20
```

Output (timestamps vary):

```text
[13:05:46] 🟢 PAPER BUY MOON 0.0500 SOL (3 buyers in 4s, mcap 34 SOL)
https://pump.fun/coin/MoonAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxpump
[13:05:46] 💰 PAPER SELL MOON +0.0552 SOL (+110.4%) after 21s: take profit +115%
[13:05:46] 🟢 PAPER BUY DUMP 0.0500 SOL (3 buyers in 4s, mcap 34 SOL)
https://pump.fun/coin/DumpByyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyypump
[13:05:46] 🔴 PAPER SELL DUMP -0.0110 SOL (-22.1%) after 11s: stop loss -20%
[13:05:46] 🟢 PAPER BUY GRAD 0.0500 SOL (3 buyers in 3s, mcap 31 SOL)
https://pump.fun/coin/GradEvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvpump
[13:05:46] 💰 PAPER SELL GRAD +0.0011 SOL (+2.2%) after 27s: graduated to AMM
{
  "closed_trades": 3,
  "wins": 2,
  "realized_pnl_sol": 0.045279,
  "open_positions": 0,
  "launches_seen": 5
}
```

### Trade for real

Use a **dedicated hot wallet** that holds only what you are willing to lose.

```bash
export NLN_RPC_URL=https://...                    # your NoLimitNodes RPC URL
export SOLANA_KEYPAIR_PATH=~/.config/solana/sniper.json
# optional: export JUPITER_API_KEY=...            # https://developers.jup.ag/portal

python run_sniper.py --live --buy-sol 0.02 --max-positions 2 --stop-loss 25 --max-daily-loss 0.2
```

In live mode the bot checks your wallet balance at startup and refuses to start if it holds less than `--buy-sol` plus 0.01 SOL. For each order it gets a route from Jupiter `/build`, compiles and signs a v0 transaction on your machine, sends it through your NLN RPC and waits for confirmation.

## Features

| Feature | What it does | Flag |
|---|---|---|
| Instant mode | Buy on the PumpFun `create` event | `--mode instant` |
| Momentum mode (default) | Buy once a launch has N unique buyers within T seconds | `--momentum-buyers 10 --momentum-window 30` |
| Take profit / stop loss | Sell at +X% or −Y% | `--take-profit 100 --stop-loss 30` |
| Trailing stop | Sell when price falls X% from its peak | `--trailing-stop 25` |
| Max hold | Sell after N seconds, even if the token stops trading | `--max-hold 300` |
| Graduation exit | Sell when the bonding curve completes and migrates to PumpSwap | on by default |
| Rug filters | Skip large dev buys, blocked creators, mayhem mode, keywords, high entry market cap | `--max-dev-buy 2 --block-creators ... --exclude-keywords rug` |
| Risk caps | Max open positions and a daily realized-loss cap | `--max-positions 3 --max-daily-loss 0.5` |
| Paper trading and replay | Simulated fills at the live curve price, or offline replay of recorded events | default, `--replay` |
| Telegram alerts | Posts every buy, sell and PnL to a chat | `--telegram` |

## Configuration

Every flag with an env name below falls back to that environment variable (see [`.env.example`](.env.example)). The bot reads the process environment and does not load `.env` by itself, so `export` the values or use an `EnvironmentFile` (see [Running 24/7](#running-247)).

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
| `--max-entry-mcap` | `MAX_ENTRY_MCAP_SOL` | `60` | Skip momentum entries above this market cap in SOL (0 = off) |
| `--max-dev-buy` | `MAX_DEV_BUY_SOL` | `0` | Skip if the creator buys more than this many SOL (0 = off) |
| `--keywords` / `--exclude-keywords` | `KEYWORDS` / `EXCLUDE_KEYWORDS` | none | Comma-separated name or symbol filters |
| `--block-creators` | `BLOCKED_CREATORS` | none | Comma-separated creator wallets to ignore |
| `--allow-mayhem` | | off | Do not skip mayhem-mode launches |
| `--max-daily-loss` | `MAX_DAILY_LOSS_SOL` | `0.5` | Stop opening positions after this realized loss (UTC day, 0 = off) |
| `--live` | | off | Sign and send real transactions |
| `--slippage-bps` | `SLIPPAGE_BPS` | `1500` | Max slippage for live swaps |
| `--priority` | `PRIORITY` | `high` | Jupiter `computeUnitPricePercentile`: `medium`, `high`, `veryHigh` or `0`–`10000` |
| `--paper-cost-bps` | `PAPER_COST_BPS` | `200` | Paper mode fees plus slippage charged per side |
| `--telegram` | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | off | Telegram trade alerts |
| `--json` | | off | Print events as JSON lines |
| `--quiet` | | off | Do not print events to the console |
| `--replay FILE` | | none | Replay a JSONL file of `{"topic": ..., "event": ...}` records offline |
| `-v`, `--verbose` | | off | Debug logging |

### Environment variables

| Variable | Needed for | Notes |
|---|---|---|
| `NLN_API_KEY` | Streaming (not replay) | From [app.nolimitnodes.com/register](https://app.nolimitnodes.com/register) |
| `NLN_STREAM_ENDPOINT` | Optional | Defaults to `stream-1.nln.clr3.org:443` |
| `NLN_STREAM_INSECURE` | Testing only | Set to `1` only for a local plaintext test server |
| `NLN_RPC_URL` | `--live` | Your NoLimitNodes Solana RPC URL |
| `SOLANA_KEYPAIR_PATH` or `SOLANA_PRIVATE_KEY` | `--live` | A solana-keygen JSON keypair file, or a base58 secret key |
| `JUPITER_API_KEY` | Optional | A free key from [developers.jup.ag/portal](https://developers.jup.ag/portal) raises rate limits |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | `--telegram` | Telegram sends at most one message per second and honors `retry_after` |

## Strategy: entries, exits and risk limits

The full math is in [`docs/guide.md`](docs/guide.md). The short version:

### Momentum entries

1. A `trade` with `ix_name = buy` from the creator adds to the launch's dev buy. If it exceeds `--max-dev-buy`, the launch is rejected.
2. A buy from any other wallet within `--momentum-window` seconds of the `create` timestamp adds that wallet to a set. Repeat buyers count once.
3. When the set reaches `--momentum-buyers`, the engine checks the current market cap against `--max-entry-mcap` and sends one buy order.

Each launch triggers at most one entry. The engine remembers the last 5,000 launches. Instant mode skips the buyer count and buys on the `create` event.

### Price, market cap and PnL

```text
price      = virtual_sol_reserves / virtual_token_reserves      (lamports per raw token unit)
market_cap = price × token_total_supply / 1e9                    (SOL)
pnl_pct    = (last_price / entry_price − 1) × 100
```

A fresh launch (30 SOL and 1.073 billion virtual tokens, 1 billion supply) starts at about 28 SOL market cap. `entry_price` is SOL spent divided by tokens received, so fees and slippage are already in your break-even. Live fills use the wallet's actual balance change. Paper fills charge `--paper-cost-bps` on both sides.

### Exits, checked in this order

On every trade for a token you hold, and once a second for all positions:

1. **Take profit:** `pnl_pct ≥ --take-profit`
2. **Stop loss:** `pnl_pct ≤ −--stop-loss`
3. **Trailing stop:** price is `--trailing-stop` percent below the highest price since entry
4. **Max hold:** position age `≥ --max-hold` seconds
5. **Graduation:** a `graduate` event arrives for the mint (unless `--hold-through-graduation`)

A sell that fails, for example from an RPC timeout or no route, is retried on the next price update or tick. If the wallet holds none of the token, the position is dropped.

### Risk limits

- `--max-positions` counts open positions **and** buys still in flight, so a burst of launches cannot overspend.
- `--max-daily-loss` sums realized PnL for the current UTC day. Once the loss reaches the cap, no new positions open. Exits keep running.
- `--buy-sol` is fixed per entry. In live mode the bot refuses to start if the wallet holds less than `--buy-sol` plus 0.01 SOL.

## Live trade execution

```text
GET https://api.jup.ag/swap/v2/build?inputMint=So111…112&outputMint=<mint>&amount=<lamports>&taker=<wallet>
    &slippageBps=1500&computeUnitPricePercentile=high
→ compute budget + setup + swap + cleanup instructions, address lookup tables
→ MessageV0.try_compile(...) with a blockhash from NLN RPC, signed locally with solders
→ sendTransaction on NLN RPC (skipPreflight) → getSignatureStatuses until confirmed
→ getTokenAccountsByOwner (tokens received) and getTransaction (actual SOL spent)
```

Jupiter `/build` returns instructions instead of a signed transaction, so you choose the RPC that sends it and Jupiter takes no swap fee. Sells use the wallet's real token balance across both SPL Token and Token-2022 accounts.

### Reducing latency

- **Host location:** run the bot in the same region as your NLN endpoint. NLN plans include VPS credit.
- **Priority fees:** raise `--priority` to `veryHigh` or an explicit percentile during busy launches. The [Solana priority fee API](https://github.com/no-limit-nodes/solana-priority-fee-api) shows what landed PumpFun transactions actually paid.
- **Earlier detection:** NoLimitNodes [Shredstream](https://nolimitnodes.com/products/shredstream) delivers raw shreds before the block is confirmed. Decoding PumpFun creates from shreds and feeding them to `SniperEngine.on_create` is the next step past the decoded stream.
- **Direct instructions:** a custom PumpFun buy builder avoids the Jupiter round trip. Implement `buy(mint, lamports)` and `sell(mint, fraction)` returning a `Fill`, and pass it to `Executor`.

## Running 24/7

```ini
[Unit]
Description=PumpFun sniper bot
After=network-online.target

[Service]
WorkingDirectory=/opt/pumpfun-sniper-bot
EnvironmentFile=/opt/pumpfun-sniper-bot/.env
ExecStart=/opt/pumpfun-sniper-bot/.venv/bin/python run_sniper.py --telegram
Restart=always
RestartSec=5
RestartPreventExitStatus=2

[Install]
WantedBy=multi-user.target
```

The stream client reconnects with exponential backoff. The process exits with code 2 when NLN rejects the API key, so systemd does not restart it in a loop. **Positions live in memory.** If the process restarts, open positions are not tracked, so check your wallet and sell manually if needed. On shutdown the bot prints a JSON summary and logs any positions still open.

## Use cases

### Trading

- **Paper-test a sniping idea** on live launches with `--json` for a day before funding a wallet.
- **Run a small live sniper** with tight caps (`--buy-sol 0.02 --max-positions 2 --max-daily-loss 0.2`).
- **Get trade alerts on your phone** with `--telegram`.

### Research and development

- **Compare instant and momentum entries** on the same recorded events with `--replay`.
- **Tune filters offline** (`--max-dev-buy`, `--exclude-keywords`, `--max-entry-mcap`) without an API key.
- **Swap in your own executor** by replacing `LiveTrader.buy` with a direct PumpFun instruction builder. The engine and executor do not change.
- **Reuse `nln_stream.py`** as a gRPC client with reconnect and multi-topic fan-in in other projects.

## How it works

```text
NoLimitNodes gRPC (stream-1.nln.clr3.org:443)
  ├─ prod.rpc.solana.pumpfun.create   ─┐                       ┌─ PaperTrader (default)
  ├─ prod.rpc.solana.pumpfun.trade    ─┼─► SniperEngine ─► Executor ─┤
  └─ prod.rpc.solana.pumpfun.graduate ─┘   filters, positions,  └─ LiveTrader: Jupiter /build → sign → NLN RPC
                                           exits, risk caps
```

| Topic | Event | Used for |
|---|---|---|
| `prod.rpc.solana.pumpfun.create` | `CreateEntry` | Instant entries, launch filters, creator and supply |
| `prod.rpc.solana.pumpfun.trade` | `TradeEntry` | Momentum buyer counts, dev-buy size, live price for exits |
| `prod.rpc.solana.pumpfun.graduate` | `GraduateEvent` | Graduation exits |

- **Entries** come from `create` (instant mode) or from counting unique buyers on `trade` (momentum mode).
- **Prices** come from the post-trade virtual reserves on every `trade` event, so take profit and stop loss react to each trade on the curve.
- **Exits** are checked on every trade for a held token and once a second for time-based rules.
- **Orders** run on a background thread with sells ahead of buys, so the stream is never blocked.

Field references are in the [NLN schema docs](https://github.com/no-limit-nodes/solana-programs-data-streaming-reference/blob/main/docs/schemas.md). Numeric fields arrive as strings and are parsed defensively.

## Instant vs momentum mode: when to pick which

**Instant mode** is first in line, but it buys every launch that passes your filters, and most PumpFun tokens go to zero quickly. Pick it if you have strong creator or keyword filters and care most about entry price.

**Momentum mode** waits until a launch has real, distinct buyers (10 within 30 seconds by default), skips launches with a large creator buy, and caps the entry market cap. It enters later and at a higher price, but filters out most dead launches. Pick it if you would rather pay more for a launch that already has buyers.

Use `--replay` and paper mode to compare both on your own data.

## Repo layout

```
.
├── run_sniper.py              # command-line entry point, executor and replay
├── sniper.py                  # strategy engine: filters, positions, exits, risk caps (no network I/O)
├── trader.py                  # PaperTrader and LiveTrader (Jupiter Swap API V2 + NoLimitNodes RPC)
├── nln_stream.py              # NoLimitNodes gRPC client with reconnect and multi-topic fan-in
├── notify.py                  # console, JSON and Telegram output
├── docs/
│   └── guide.md               # strategy math, latency notes and deployment
├── examples/
│   └── sample-events.jsonl    # five recorded-shape launches for offline replay
├── tests/
│   ├── test_sniper.py         # engine and replay tests
│   └── test_trader.py         # paper and live-transaction assembly tests
├── requirements.txt           # grpcio, grpcio-tools, solders
├── .env.example
├── LICENSE                    # MIT
└── README.md
```

Run the tests with `python -m unittest discover -s tests`.

## FAQ

<details>
<summary><b>What is the fastest way to snipe pump.fun tokens?</b></summary>

Get launches from a push stream instead of polling RPC. This bot subscribes to the NoLimitNodes `prod.rpc.solana.pumpfun.create` gRPC topic and acts on each launch as it arrives. For earlier detection, NoLimitNodes Shredstream delivers raw shreds before blocks are confirmed. Pair it with `--priority veryHigh` and a host close to the leader validators.
</details>

<details>
<summary><b>Is it better to buy instantly or wait for momentum?</b></summary>

It depends on your filters. Instant mode is first in line but buys every launch that passes, and most PumpFun tokens go to zero quickly. Momentum mode waits for distinct buyers (10 within 30 seconds by default), skips big creator buys and caps entry market cap. It enters later and higher but skips most dead launches.
</details>

<details>
<summary><b>How does the bot calculate price and PnL?</b></summary>

Price is `virtual_sol_reserves / virtual_token_reserves` in lamports per raw token unit, read from each trade event's post-trade reserves. Market cap in SOL is price times total supply divided by 1e9. PnL is SOL received minus SOL spent. Live fills use the wallet's actual balance change, and paper fills charge `--paper-cost-bps` on both sides.
</details>

<details>
<summary><b>Can the bot buy tokens the second they launch?</b></summary>

Not always. In live mode, buys go through the Jupiter Swap API, which supports PumpFun bonding curves, but a token only a few hundred milliseconds old may not be routable yet. The buy then fails cleanly, is logged, and the bot keeps running. To send instructions straight to the PumpFun program, replace `LiveTrader.buy` with your own builder.
</details>

<details>
<summary><b>Does it support Bonk.fun, Raydium LaunchLab or PumpSwap?</b></summary>

The sniper targets PumpFun launches only. Sells after graduation go through Jupiter, which routes PumpSwap. NoLimitNodes also streams PumpSwap, Raydium, Orca and Meteora swaps (see the streaming reference repo), so you can add other venues by feeding their events into the engine. Bonk.fun and LaunchLab are not wired in today.
</details>

<details>
<summary><b>Is it safe to run the sniper with my main wallet?</b></summary>

No. Use a separate wallet funded with a small amount, keep `--max-daily-loss` and `--max-positions` low, and start in paper mode, which is the default. Positions live in memory, so a restart forgets them. Memecoin trading is extremely risky, and many PumpFun tokens are scams. Nothing here is financial advice.
</details>

<details>
<summary><b>Do I need an API key to try the sniper?</b></summary>

Not for replay. `python run_sniper.py --replay examples/sample-events.jsonl` runs the full engine and paper trader offline with no key. For live launches you need a NoLimitNodes API key in `NLN_API_KEY`. Registering at app.nolimitnodes.com gives a 5-day free Pro trial with no credit card required.
</details>

## Learn more on NoLimitNodes Academy

- [PumpFun WebSocket vs gRPC vs decoded stream](https://nolimitnodes.com/academy/pumpfun-websocket-vs-grpc-vs-decoded-stream): why this bot reads decoded `create`/`trade`/`graduate` events instead of raw logs.
- [Send Solana transactions that land](https://nolimitnodes.com/academy/send-solana-transactions-that-land): priority fees, confirmation and retries, the parts that decide whether a live snipe fills.
- [PumpFun graduations SQL workbook](https://nolimitnodes.com/academy/pumpfun-graduations-sql-workbook): study how launches graduate before tuning the graduation exit.
- [NoLimitNodes Academy](https://nolimitnodes.com/academy): all walkthroughs, comparisons and workbooks.

## Contributing

Issues and pull requests are welcome on [GitHub](https://github.com/no-limit-nodes/pumpfun-sniper-bot). Run `python -m unittest discover -s tests` and a `--replay` pass before opening a PR.

## License

Released under the [MIT License](LICENSE).

## Related resources

- [Solana copy trading bot](https://github.com/no-limit-nodes/solana-copy-trading-bot): mirror any wallet's trades across PumpFun, PumpSwap, Raydium, Orca and Meteora
- [PumpFun Telegram alert bot](https://github.com/no-limit-nodes/pumpfun-telegram-alert-bot): launch, graduation and whale alerts
- [Solana priority fee API](https://github.com/no-limit-nodes/solana-priority-fee-api): compute-unit price from landed PumpFun transactions
- [Solana streaming reference](https://github.com/no-limit-nodes/solana-programs-data-streaming-reference): every NLN topic with clients in 7 languages
- [Every Solana program decoded](https://github.com/no-limit-nodes/every-solana-program-decoded): 1,074 streams across 37 programs
- [NoLimitNodes PumpFun data](https://nolimitnodes.com/products/pumpfun-data)
- [NoLimitNodes Solana RPC nodes](https://nolimitnodes.com/products/rpc-nodes)
- [NoLimitNodes Shredstream](https://nolimitnodes.com/products/shredstream)
- [PumpFun token creations topic docs](https://nolimitnodes.com/docs/api-reference/enhanced-streams/topics/pumpfun-token-creations)
- [Custom Solana sniper bot development](https://nolimitnodes.com/custom-development/solana-sniper-bot-development)
- [Blog: trailing stop-loss strategies on pump.fun](https://nolimitnodes.com/blog/mastering-pump-fun-with-websocket-a-tutorial-on-trailing-stop-loss-strategies)
- [pump.fun](https://pump.fun)
- [Jupiter developer docs](https://dev.jup.ag)
- [Solana transaction fees](https://solana.com/docs/core/fees)

## Disclaimer

This software is provided for education and research. It is not financial advice. Trading memecoins can lose all of your funds, and many PumpFun tokens are scams. Paper trading is the default, and nothing is signed or sent until you pass `--live`. You are responsible for your keys, your trades and complying with the laws where you live.

---

<p align="center">
  <b>Ready to snipe pump.fun launches on a decoded gRPC stream?</b><br>
  <a href="https://app.nolimitnodes.com/register">Register, get a 5-day free Pro trial, grab your API key →</a>
</p>
