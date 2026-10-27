# assignment01: Automated trading sandbox (Zerodha Kite Connect)

A small Python project for learning automated trading on Zerodha with safety built in.
It runs in **paper mode by default**. Real orders need several deliberate steps first.

> This is a learning project, not financial advice. Most retail algo strategies lose money
> once costs are included. Only trade money you can afford to lose.

## What's in here

| Command | What it does | Needs Kite login? | Risk |
|---|---|---|---|
| `python -m autotrader backtest` | Replays daily closes from a CSV through the strategy | No | None |
| `python -m autotrader login` | Gets today's Kite access token (tokens expire daily) | — | None |
| `python -m autotrader portfolio` | Shows your holdings and cash (read-only) | Yes | None |
| `python -m autotrader trade` | Polls live prices, **simulated** fills | Yes + market data plan | None |
| `python -m autotrader trade --live` | Same, but sends **real limit orders** | Yes + `LIVE_TRADING` phrase + typed confirmation | **Real money** |

Code layout:

```
autotrader/
  config.py    settings from .env (keys, risk limits)
  risk.py      pre-trade checks: symbol allowlist, order size cap, max positions,
               max orders/day, daily loss halt, kill switch file, no shorting
  broker.py    PaperBroker (simulated) and KiteBroker (thin kiteconnect wrapper)
  strategy.py  SMA crossover example (deliberately simple)
  engine.py    Trader: signal -> position sizing -> risk check -> broker
  backtest.py  runs the same Trader over historical data
  cli.py       the commands above
data/sample_synthetic_prices.csv   random-walk prices (NOT real market data)
tests/         unit tests, including a fake Kite client
```

## Quick start

```bash
pip install -r requirements.txt
python -m pytest            # all tests should pass
python -m autotrader backtest -v
```

On the synthetic sample data the SMA strategy returns about -0.4% while buy-and-hold returns about
+1.3%. That's typical: a simple strategy often does worse than just holding. That's why you
backtest before going live.

To connect your Zerodha account:

1. Create an app at <https://developers.kite.trade> and note the API key and secret.
   Set the redirect URL to something you control (even `http://127.0.0.1/` works; you just copy the token from the address bar).
2. `cp .env.example .env` and fill in `KITE_API_KEY` / `KITE_API_SECRET`.
3. `python -m autotrader login`, then `python -m autotrader portfolio`.

`.env`, `.kite_session.json` and `KILL` are gitignored. **Never commit your API secret or access token.**

### Emergency stop

`touch KILL` in the project folder: the next order attempt halts the trader. Hitting the daily loss
limit also halts it, and the halt holds until you restart the process yourself.

## Options for connecting Claude to your portfolio

1. **Zerodha's Kite MCP server (easiest way to "talk to your portfolio").** Zerodha publishes an
   official MCP server (<https://github.com/zerodha/kite-mcp-server>) that you can add to Claude as a
   connector. You can then ask Claude things like "what's my P&L by sector?" or "which holdings are
   down more than 10%?". Good for analysis. Check its docs for which tools (especially order placement)
   the hosted version currently exposes.
2. **Your own bot (this repo).** Rules-based code places the orders and Claude helps you write, test
   and review it. The code is deterministic and testable, and you can explain every trade.
3. **Hybrid (recommended long-term).** Claude does the research and analysis (portfolio reviews,
   summarising results, news), the bot executes fixed rules, and you approve anything unusual.
   Letting an LLM place trades directly on its own judgement is not recommended: its outputs aren't
   reproducible, you can't backtest them, and a mistake costs real money.
4. **No-code platforms** such as Zerodha's Streak, if you'd rather not maintain code.

## Pros and cons

**Pros**
- Discipline: rules run without fear or greed, and stop-losses actually get executed.
- Backtesting: you can see how an idea would have done historically before risking money.
- Speed and coverage: it can watch many symbols all day.
- Great learning project: APIs, data, testing, risk management, Python.
- Claude (via the Kite MCP) is genuinely useful for portfolio analysis even if you never automate orders.

**Cons and risks**
- **Most strategies don't beat buy-and-hold** after brokerage, STT, exchange charges and slippage.
  Backtests overfit easily.
- **Bugs cost real money.** A loop that sends the same order 50 times is the classic failure, which is why
  `risk.py` exists. Keep the limits small.
- **Operational hassle:** Kite access tokens expire every day and need a manual login (automating the
  login with stored passwords/TOTP is against Zerodha's terms and a security risk). The bot needs a
  machine that stays running during market hours.
- **Cost:** order placement and portfolio APIs are on Zerodha's free Personal plan. Live and historical
  market data needs the paid Connect plan (reported as ₹500/month since 2025). Check current pricing on
  developers.kite.trade.
- **Regulation (India):** SEBI's retail algo-trading framework (mandatory from April 2026) applies to API
  orders. Order placement only works from a **whitelisted static IP** (a home connection usually isn't
  one, so a small VPS is the usual answer). Strategies above roughly 10 orders/second, or ones you sell to
  others, must be registered with the exchange through the broker. Personal, low-frequency trading for
  yourself, like this project, sits below that. **Check the current Zerodha/SEBI rules before going live.**
- **Security:** an API key plus access token can trade your account. Keep them out of git, chats and screenshots.

## Roadmap (how to go from here)

1. **Now:** run the tests and the backtest, read `risk.py` and `engine.py`, and tweak `--fast/--slow`.
2. **Real data:** download real daily closes (e.g. NSE bhavcopy or Kite historical API) into the same
   CSV format and backtest on that. Add brokerage/STT costs to `PaperBroker` and fill at the *next*
   bar's price, not the signal bar's (the current backtest is optimistic on both counts).
3. **Connect read-only:** `login` + `portfolio`. Add the Kite MCP connector to Claude for analysis.
4. **Paper trade for weeks:** `trade` (paper) during market hours. Compare with the backtest.
5. **Tiny live test:** only after the above. Use 1 share, `MAX_ORDER_VALUE` of a few thousand rupees,
   and set up the static IP. Watch every order in the Kite app.
6. **Later:** order-status tracking (postbacks/websocket), logging to a file/DB, better strategies,
   a scheduler for market hours.
