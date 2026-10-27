"""Command line entry point: python -m autotrader <command>"""

import argparse
import datetime as dt
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

from autotrader.backtest import load_prices, run_backtest
from autotrader.broker import KiteBroker, PaperBroker
from autotrader.config import LIVE_TRADING_PHRASE, Settings, load_settings
from autotrader.engine import Trader
from autotrader.risk import RiskManager
from autotrader.strategy import SmaCrossover

SESSION_FILE = Path(".kite_session.json")  # gitignored; holds today's access token


def make_risk(s: Settings) -> RiskManager:
    return RiskManager(
        max_order_value=s.max_order_value,
        max_daily_loss=s.max_daily_loss,
        max_open_positions=s.max_open_positions,
        max_orders_per_day=s.max_orders_per_day,
        allowed_symbols=s.allowed_symbols,
    )


def kite_client(s: Settings, need_token: bool = True):
    try:
        from kiteconnect import KiteConnect
    except ImportError:
        sys.exit("kiteconnect is not installed: pip install -r requirements.txt")
    if not s.api_key:
        sys.exit("KITE_API_KEY is not set (copy .env.example to .env)")
    kite = KiteConnect(api_key=s.api_key)
    if need_token:
        if not SESSION_FILE.exists():
            sys.exit("No session. Run: python -m autotrader login")
        session = json.loads(SESSION_FILE.read_text())
        if session.get("date") != dt.date.today().isoformat():
            sys.exit("Session is from a previous day (Kite tokens expire daily). Run login again.")
        kite.set_access_token(session["access_token"])
    return kite


def cmd_login(s: Settings, args) -> None:
    if not s.api_secret:
        sys.exit("KITE_API_SECRET is not set")
    kite = kite_client(s, need_token=False)
    print("1. Open this URL and log in with your Zerodha account:\n  ", kite.login_url())
    print("2. You'll be redirected to your redirect URL. Copy the request_token from it.")
    token = input("request_token (or the full redirect URL): ").strip()
    if "request_token=" in token:
        token = token.split("request_token=", 1)[1].split("&", 1)[0]
    data = kite.generate_session(token, api_secret=s.api_secret)
    SESSION_FILE.write_text(json.dumps({"date": dt.date.today().isoformat(), "access_token": data["access_token"]}))
    SESSION_FILE.chmod(0o600)
    print(f"Logged in as {data.get('user_name', data.get('user_id'))}. Token saved to {SESSION_FILE}.")


def cmd_portfolio(s: Settings, args) -> None:
    broker = KiteBroker(kite_client(s))
    holdings = broker.holdings()
    print(f"{'SYMBOL':<14}{'QTY':>6}{'AVG':>12}{'LTP':>12}{'P&L':>12}")
    total = 0.0
    for h in holdings:
        qty = h["quantity"] + h.get("t1_quantity", 0)
        total += h["pnl"]
        print(f"{h['tradingsymbol']:<14}{qty:>6}{h['average_price']:>12.2f}{h['last_price']:>12.2f}{h['pnl']:>12.2f}")
    print(f"{'Total P&L':<44}{total:>12.2f}")
    equity = broker.margins().get("equity", {})
    print(f"Available cash: {equity.get('available', {}).get('live_balance', 'n/a')}")


def cmd_backtest(s: Settings, args) -> None:
    prices = load_prices(Path(args.csv))
    risk = replace(make_risk(s), allowed_symbols=frozenset(prices))
    result = run_backtest(prices, SmaCrossover(args.fast, args.slow), risk, cash=s.paper_cash)
    if args.verbose:
        print("\n".join(result.log))
    print(f"Start equity:      {result.start_equity:,.2f}")
    print(f"End equity:        {result.end_equity:,.2f}")
    print(f"Strategy return:   {result.return_pct:+.2f}%")
    print(f"Buy & hold return: {result.buy_and_hold_pct:+.2f}% (equal weight)")
    print(f"Max drawdown:      {result.max_drawdown_pct:.2f}%")
    print(f"Fills:             {result.trades}")


def cmd_trade(s: Settings, args) -> None:
    broker = KiteBroker(kite_client(s))
    symbols = sorted(s.allowed_symbols)
    risk = make_risk(s)
    if args.live:
        if not s.live_trading:
            sys.exit(f"Refusing live trading: set LIVE_TRADING={LIVE_TRADING_PHRASE} in .env first.")
        print(f"LIVE MODE. Real orders, real money. Max order {s.max_order_value}, max daily loss {s.max_daily_loss}.")
        if input("Type LIVE to continue: ").strip() != "LIVE":
            sys.exit("Aborted.")
        trader = Trader(SmaCrossover(args.fast, args.slow), risk, live=broker)
    else:
        print("PAPER MODE: live prices from Kite, simulated fills. No orders are sent.")
        trader = Trader(SmaCrossover(args.fast, args.slow), risk, paper=PaperBroker(cash=s.paper_cash))

    print(f"Watching {', '.join(symbols)} every {args.interval}s. Ctrl+C or `touch KILL` to stop.")
    seen = 0
    try:
        while not risk.halted_reason:
            if args.live:
                risk.set_pnl(broker.day_pnl())
            stamp = dt.datetime.now().strftime("%H:%M:%S")
            for symbol, price in broker.ltp(symbols).items():
                trader.on_price(symbol, price, label=stamp)
            for line in trader.log[seen:]:
                print(line)
            seen = len(trader.log)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    print(f"Stopped. {risk.halted_reason or 'user interrupt'}")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="autotrader", description="Zerodha Kite trading sandbox")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("login", help="get today's Kite access token")
    sub.add_parser("portfolio", help="show holdings (read-only)")
    bt = sub.add_parser("backtest", help="replay a CSV of daily closes")
    bt.add_argument("csv", nargs="?", default="data/sample_synthetic_prices.csv")
    bt.add_argument("-v", "--verbose", action="store_true")
    tr = sub.add_parser("trade", help="poll live prices and trade (paper unless --live)")
    tr.add_argument("--live", action="store_true", help="send real orders (needs LIVE_TRADING in .env)")
    tr.add_argument("--interval", type=int, default=60, help="seconds between price polls")
    for p in (bt, tr):
        p.add_argument("--fast", type=int, default=10)
        p.add_argument("--slow", type=int, default=30)
    args = parser.parse_args(argv)

    settings = load_settings()
    {"login": cmd_login, "portfolio": cmd_portfolio, "backtest": cmd_backtest, "trade": cmd_trade}[args.command](
        settings, args
    )
