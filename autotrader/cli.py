"""Command line entry point: python -m autotrader <command>

Read-only by design: no command can place, modify or cancel a real order.
"""

import argparse
import datetime as dt
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

from autotrader.backtest import load_prices, run_backtest
from autotrader.broker import PaperBroker, ReadOnlyKite
from autotrader.config import Settings, load_settings
from autotrader.engine import Trader
from autotrader.portfolio import Rules, holdings_from_csv, holdings_from_kite, load_sectors, review, snapshot
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


def kite_client(s: Settings):
    try:
        from kiteconnect import KiteConnect
    except ImportError:
        sys.exit("kiteconnect is not installed: pip install -r requirements.txt")
    if not s.api_key:
        sys.exit("KITE_API_KEY is not set (copy .env.example to .env)")
    return KiteConnect(api_key=s.api_key)


def read_only_kite(s: Settings) -> ReadOnlyKite:
    kite = kite_client(s)
    if not SESSION_FILE.exists():
        sys.exit("No session. Run: python -m autotrader login")
    session = json.loads(SESSION_FILE.read_text())
    if session.get("date") != dt.date.today().isoformat():
        sys.exit("Session is from a previous day (Kite tokens expire daily). Run login again.")
    kite.set_access_token(session["access_token"])
    return ReadOnlyKite(kite)


def cmd_login(s: Settings, args) -> None:
    if not s.api_secret:
        sys.exit("KITE_API_SECRET is not set")
    kite = kite_client(s)
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
    sectors = load_sectors(Path(s.sector_file))
    if args.csv:
        holdings = holdings_from_csv(Path(args.csv), sectors)
        cash = args.cash
    else:
        kite = read_only_kite(s)
        holdings = holdings_from_kite(kite.holdings(), sectors)
        cash = kite.margins().get("equity", {}).get("available", {}).get("live_balance", 0.0)

    rules = Rules(max_holding_pct=s.max_holding_pct, loss_alert_pct=s.loss_alert_pct, gain_alert_pct=s.gain_alert_pct)
    suggestions = review(holdings, cash, rules)

    total_value = sum(h.value for h in holdings)
    print(f"{'SYMBOL':<12}{'SECTOR':<14}{'QTY':>6}{'AVG':>10}{'LTP':>10}{'VALUE':>12}{'P&L':>11}{'P&L%':>8}{'WT%':>6}")
    for h in sorted(holdings, key=lambda h: h.value, reverse=True):
        weight = h.value / total_value * 100 if total_value else 0
        print(f"{h.symbol:<12}{h.sector[:13]:<14}{h.quantity:>6}{h.average_price:>10.2f}{h.last_price:>10.2f}"
              f"{h.value:>12,.0f}{h.pnl:>11,.0f}{h.pnl_pct:>7.1f}%{weight:>5.0f}%")
    invested = sum(h.invested for h in holdings)
    pnl_pct = (total_value / invested - 1) * 100 if invested else 0
    print(f"\nInvested {invested:,.0f} | Value {total_value:,.0f} | P&L {total_value - invested:+,.0f} "
          f"({pnl_pct:+.1f}%) | Cash {cash:,.0f}")

    print("\nSuggestions (rule-based prompts, not financial advice):")
    for sug in suggestions:
        who = f"{sug.symbol}: " if sug.symbol else ""
        print(f"  [{sug.level}] {who}{sug.message}")

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(snapshot(holdings, cash, suggestions), indent=2))
        print(f"\nSaved snapshot to {out}. It contains your holdings: keep it under exports/ (gitignored).")


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


def cmd_paper(s: Settings, args) -> None:
    kite = read_only_kite(s)
    symbols = sorted(s.allowed_symbols)
    risk = make_risk(s)
    trader = Trader(SmaCrossover(args.fast, args.slow), risk, paper=PaperBroker(cash=s.paper_cash))
    print("PAPER MODE: live prices from Kite, simulated fills. No orders are ever sent.")
    print(f"Watching {', '.join(symbols)} every {args.interval}s. Ctrl+C to stop.")
    seen = 0
    try:
        while not risk.halted_reason:
            stamp = dt.datetime.now().strftime("%H:%M:%S")
            for symbol, price in kite.ltp_map(symbols).items():
                trader.on_price(symbol, price, label=stamp)
            for line in trader.log[seen:]:
                print(line)
            seen = len(trader.log)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    print(f"Stopped. {risk.halted_reason or 'user interrupt'}")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="autotrader", description="Read-only Zerodha portfolio assistant")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("login", help="get today's Kite access token")
    pf = sub.add_parser("portfolio", help="show holdings with suggestions (read-only)")
    pf.add_argument("--csv", help="read holdings from a CSV instead of Kite (no login needed)")
    pf.add_argument("--cash", type=float, default=0.0, help="cash balance to assume with --csv")
    pf.add_argument("--json", help="also save a snapshot to this JSON file")
    bt = sub.add_parser("backtest", help="replay a CSV of daily closes")
    bt.add_argument("csv", nargs="?", default="data/sample_synthetic_prices.csv")
    bt.add_argument("-v", "--verbose", action="store_true")
    pp = sub.add_parser("paper", help="paper-trade on live Kite prices (simulated fills only)")
    pp.add_argument("--interval", type=int, default=60, help="seconds between price polls")
    for p in (bt, pp):
        p.add_argument("--fast", type=int, default=10)
        p.add_argument("--slow", type=int, default=30)
    args = parser.parse_args(argv)

    settings = load_settings()
    {"login": cmd_login, "portfolio": cmd_portfolio, "backtest": cmd_backtest, "paper": cmd_paper}[args.command](
        settings, args
    )
