# assignment01: Read-only Zerodha portfolio assistant

A small Python project that **looks at** your Zerodha portfolio and suggests things to review.
It **cannot place, modify or cancel orders**. The Kite client is wrapped in `ReadOnlyKite`, which only lets
read methods through (holdings, positions, prices...). Order, GTT and mutual fund methods raise an error,
and there's a test that checks this.

> Suggestions are rule-based prompts to look closer, not financial advice.

## Commands

| Command | What it does | Needs Kite login? |
|---|---|---|
| `python -m autotrader portfolio --csv data/sample_holdings.csv --cash 60000` | Review a holdings CSV (try this first) | No |
| `python -m autotrader login` | Get today's Kite access token (tokens expire daily) | — |
| `python -m autotrader portfolio` | Review your real Zerodha holdings + cash | Yes |
| `python -m autotrader portfolio --json exports/today.json` | Also save a snapshot you can paste into Claude | — |
| `python -m autotrader backtest -v` | Test the example strategy on past prices | No |
| `python -m autotrader paper` | Practice trading on live prices with **pretend** money | Yes + paid market data plan |

Example output (sample data, made-up numbers):

```
SYMBOL      SECTOR           QTY       AVG       LTP       VALUE        P&L    P&L%   WT%
RELIANCE    Oil & Gas         30   2450.00   2905.10      87,153     13,653   18.6%   36%
ITC         FMCG             100    310.00    505.75      50,575     19,575   63.1%   21%
...
Suggestions (rule-based prompts, not financial advice):
  [REVIEW] RELIANCE: 36% of your stock portfolio is in one name (guide: <20%). ...
  [REVIEW] ITC: Up 63%. Consider booking partial profit or setting a trailing stop-loss ...
  [ALERT] SUNPHARMA: Down 28% from your average price. Re-check why you bought it ...
  [INFO] HDFCBANK: Moved +5.6% today. Check the news before reacting.
```

What it checks (thresholds are set in `.env`):
- one stock is too large a share of the portfolio (default >20%)
- one sector is too large (default >40%, uses `data/sectors.csv`; add your stocks there)
- big losers (default down 20%+) and big winners (default up 50%+)
- big moves today (±5%)
- too few stocks, or a lot of idle cash

## Setup

```bash
pip install -r requirements.txt
python -m pytest            # all tests should pass
python -m autotrader portfolio --csv data/sample_holdings.csv --cash 60000
```

To connect your real account:

1. Create an app at <https://developers.kite.trade> (the free Personal plan is enough for holdings).
   Set the redirect URL to `http://127.0.0.1/`; after login you'll copy the token from the browser's address bar.
2. `cp .env.example .env` and fill in `KITE_API_KEY` / `KITE_API_SECRET`.
3. `python -m autotrader login`, then `python -m autotrader portfolio`.

`.env`, `.kite_session.json` and `exports/` are gitignored. **Never commit or share your API secret or access token.**
Even though this code is read-only, the token itself could trade your account in someone else's hands.

## Getting recommendations from Claude

The rules above are mechanical. For a conversation ("why is my portfolio so IT-heavy, what are my options?"):

- **Option A:** run `portfolio --json exports/today.json` and paste the file's contents into Claude.
- **Option B:** add Zerodha's official Kite MCP server as a connector in Claude
  (<https://github.com/zerodha/kite-mcp-server>), so Claude can read your holdings directly.
  If you want to be sure nothing gets traded, check which tools it exposes and turn off any order tools.

## How money moves in Zerodha (and why this project can't touch your bank)

```
Your bank account ──(Add funds: UPI / net banking, done by you in Kite)──▶ Zerodha trading balance
Zerodha trading balance ──(buy)──▶ shares in your demat account (credited T+1)
shares ──(sell)──▶ money back in Zerodha balance (T+1) ──(Withdraw, done by you)──▶ your bank
```

- A bank account is linked when the Zerodha account is opened; you can't open the account without one.
  Money only enters or leaves Zerodha through that linked bank.
- **The Kite API has no way to add or withdraw funds.** An app or bot can only use money you have already
  moved into your Zerodha balance. Your bank account is never accessible to it.
- Selling shares from your demat also needs authorisation (a one-time DDPI, or a CDSL TPIN/OTP each time).
- So if buying/selling is ever added, the safe pattern is to add only a small amount to Zerodha as the bot's
  maximum budget.

## If you add trading later

The paper-trading pieces are here to learn on: `risk.py` (limits, kill switch), `engine.py`, `strategy.py`,
`backtest.py`. Real order placement was removed on purpose; the first commit in git history has a gated
version. Before going live, read up on SEBI's retail algo rules (from April 2026, API orders need a
whitelisted static IP) and paper-trade for weeks first.

## Code layout

```
autotrader/
  portfolio.py  holdings, review rules, JSON snapshot
  broker.py     ReadOnlyKite (read-only gateway) and PaperBroker (simulated)
  config.py     settings from .env
  risk.py       paper-trading limits
  strategy.py   SMA crossover example
  engine.py     paper trader: signal -> size -> risk check -> simulated fill
  backtest.py   replays a price CSV through the paper trader
  cli.py        the commands above
data/
  sample_holdings.csv          made-up portfolio for trying things out
  sectors.csv                  symbol -> sector map (extend it with your stocks)
  sample_synthetic_prices.csv  random-walk prices, NOT real market data
tests/
```
