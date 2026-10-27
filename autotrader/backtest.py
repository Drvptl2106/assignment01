"""Replay daily closes from a CSV through the same Trader used for paper/live trading."""

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from autotrader.broker import PaperBroker
from autotrader.engine import Trader
from autotrader.risk import RiskManager
from autotrader.strategy import SmaCrossover


@dataclass(frozen=True)
class BacktestResult:
    start_equity: float
    end_equity: float
    max_drawdown_pct: float
    trades: int
    buy_and_hold_pct: float
    log: list[str]

    @property
    def return_pct(self) -> float:
        return (self.end_equity / self.start_equity - 1) * 100


def load_prices(path: Path) -> dict[str, list[tuple[str, float]]]:
    """CSV columns: date,symbol,close (sorted by date)."""
    series: dict[str, list[tuple[str, float]]] = defaultdict(list)
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            series[row["symbol"].upper()].append((row["date"], float(row["close"])))
    return dict(series)


def run_backtest(
    prices: dict[str, list[tuple[str, float]]],
    strategy: SmaCrossover,
    risk: RiskManager,
    cash: float,
) -> BacktestResult:
    broker = PaperBroker(cash=cash)
    trader = Trader(strategy, risk, paper=broker)

    by_date: dict[str, dict[str, float]] = defaultdict(dict)
    for symbol, rows in prices.items():
        for date, close in rows:
            by_date[date][symbol] = close

    last: dict[str, float] = {}
    peak, max_dd = cash, 0.0
    for date in sorted(by_date):
        risk.new_day()
        for symbol, close in sorted(by_date[date].items()):
            last[symbol] = close
            trader.on_price(symbol, close, label=date)
        equity = broker.equity(last)
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100)

    # Equal-weight buy-and-hold of every symbol, for comparison.
    bh = [rows[-1][1] / rows[0][1] - 1 for rows in prices.values() if rows]
    return BacktestResult(
        start_equity=cash,
        end_equity=broker.equity(last),
        max_drawdown_pct=max_dd,
        trades=len(broker.fills),
        buy_and_hold_pct=sum(bh) / len(bh) * 100 if bh else 0.0,
        log=trader.log,
    )
