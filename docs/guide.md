# PumpFun Sniper Bot Guide: Strategy, Latency and Deployment

This guide explains how the sniper turns NoLimitNodes (NLN) decoded PumpFun events into buys and sells, how to tune it, and how to run it 24/7.

## Which NLN topics does the sniper use?

| Topic | Event | Used for |
|---|---|---|
| `prod.rpc.solana.pumpfun.create` | `CreateEntry` | Instant entries, launch filters, creator and supply |
| `prod.rpc.solana.pumpfun.trade` | `TradeEntry` | Momentum buyer counts, dev-buy size, live price for exits |
| `prod.rpc.solana.pumpfun.graduate` | `GraduateEvent` | Graduation exits |

Field references are in the [NLN schema docs](https://github.com/no-limit-nodes/solana-programs-data-streaming-reference/blob/main/docs/schemas.md). Numeric fields arrive as strings and are parsed defensively.

## How does momentum mode decide to buy?

For each launch the engine keeps a set of buyer wallets:

1. A `trade` with `ix_name = buy` from the creator adds to `dev_buy`. If `dev_buy` exceeds `--max-dev-buy`, the launch is rejected.
2. A buy from any other wallet within `--momentum-window` seconds of the `create` timestamp adds that wallet to the set. Repeat buyers count once.
3. When the set reaches `--momentum-buyers`, the engine checks the current market cap against `--max-entry-mcap` and sends one buy order.

Each launch can trigger at most one entry. The engine remembers the last 5,000 launches.

## How are price, market cap and PnL calculated?

```text
price      = virtual_sol_reserves / virtual_token_reserves      (lamports per raw token unit)
market_cap = price × token_total_supply / 1e9                    (SOL)
pnl_pct    = (last_price / entry_price − 1) × 100
```

A fresh launch (30 SOL and 1.073 billion virtual tokens, 1 billion supply) starts at about 28 SOL market cap. `entry_price` is SOL spent divided by tokens received, so fees and slippage are already included in your break-even.

## How do exits work?

On every trade for a token you hold, and once a second for all positions, the engine checks in this order:

1. **Take profit:** `pnl_pct ≥ --take-profit`
2. **Stop loss:** `pnl_pct ≤ −--stop-loss`
3. **Trailing stop:** price is `--trailing-stop` percent below the highest price since entry
4. **Max hold:** position age `≥ --max-hold` seconds
5. **Graduation:** a `graduate` event arrives for the mint (unless `--hold-through-graduation`)

A sell that fails, for example from an RPC timeout or no route, clears the closing flag so the next price update or tick retries it. If the wallet holds none of the token, the position is dropped.

## What risk limits are there?

- `--max-positions` counts open positions **and** buys still in flight, so a burst of launches cannot overspend.
- `--max-daily-loss` sums realized PnL for the current UTC day. When the loss reaches the cap, no new positions open, and exits keep running.
- `--buy-sol` is fixed per entry. In live mode the bot refuses to start if the wallet holds less than `--buy-sol` plus 0.01 SOL.

## How are live trades executed?

```text
GET https://api.jup.ag/swap/v2/build?inputMint=So111…112&outputMint=<mint>&amount=<lamports>&taker=<wallet>
    &slippageBps=1500&computeUnitPricePercentile=high
→ compute budget + setup + swap + cleanup instructions, address lookup tables
→ MessageV0.try_compile(...) with a blockhash from NLN RPC, signed locally with solders
→ sendTransaction on NLN RPC (skipPreflight) → getSignatureStatuses until confirmed
→ getTokenAccountsByOwner (tokens received) and getTransaction (actual SOL spent)
```

Jupiter `/build` returns instructions instead of a signed transaction, so you choose the RPC that sends it and Jupiter takes no swap fee. Sells use the wallet's real token balance, across both SPL Token and Token-2022 accounts.

## How can I reduce latency?

- **Host location:** run the bot in the same region as your NLN endpoint. NLN plans include VPS credit.
- **Priority fees:** raise `--priority` to `veryHigh` or an explicit percentile during busy launches. The [Solana priority fee API](https://github.com/no-limit-nodes/solana-priority-fee-api) shows what landed PumpFun transactions actually paid.
- **Earlier detection:** NoLimitNodes [Shredstream](https://nolimitnodes.com/products/shredstream) delivers raw shreds before the block is confirmed. Decoding PumpFun creates from shreds and feeding them to `SniperEngine.on_create` is the next step past the decoded stream.
- **Direct instructions:** a custom PumpFun buy builder avoids the Jupiter request round trip. Implement `buy(mint, lamports)` and `sell(mint, fraction)` returning a `Fill`, and pass it to `Executor`.

## How do I run the sniper 24/7?

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

The stream client reconnects with exponential backoff. The process exits with code 2 when NLN rejects the API key, so systemd does not restart it in a loop. Positions live in memory: if the process restarts, open positions are not tracked, so check your wallet and sell manually if needed.

## How do I test a strategy change?

```bash
python run_sniper.py --replay examples/sample-events.jsonl --momentum-buyers 3 --stop-loss 20
python -m unittest discover -s tests
```

Record your own replay files as JSON lines shaped like `{"topic": "...", "event": {...}}`. Running the bot with `--json` in paper mode for a day is a cheap way to see how a configuration behaves on live launches.
