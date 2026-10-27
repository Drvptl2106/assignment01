from pathlib import Path

import pytest

from autotrader.backtest import load_prices, run_backtest
from autotrader.broker import Order, PaperBroker
from autotrader.engine import Trader, round_to_tick
from autotrader.risk import RiskManager
from autotrader.strategy import SmaCrossover

SAMPLE = Path(__file__).parent.parent / "data" / "sample_synthetic_prices.csv"


def make_risk(tmp_path, **overrides):
    params = dict(
        max_order_value=5000,
        max_daily_loss=1000,
        max_open_positions=3,
        allowed_symbols=frozenset({"INFY"}),
        kill_switch_file=tmp_path / "KILL",
    )
    return RiskManager(**{**params, **overrides})


def test_paper_broker_buy_sell_pnl():
    broker = PaperBroker(cash=10_000)
    assert broker.place_order(Order("INFY", "BUY", 2, 1510), market_price=1500).price == 1500
    assert broker.cash == 7000
    fill = broker.place_order(Order("INFY", "SELL", 2, 1590), market_price=1600)
    assert fill.realized_pnl == 200
    assert broker.cash == 10_200
    assert broker.positions == {}


def test_paper_broker_respects_limit_and_cash():
    broker = PaperBroker(cash=1000)
    assert broker.place_order(Order("INFY", "BUY", 1, 900), market_price=950) is None
    assert broker.place_order(Order("INFY", "BUY", 1, 1500), market_price=1500) is None
    assert broker.fills == []


def test_strategy_signals_on_cross():
    strat = SmaCrossover(fast=2, slow=4)
    falling_then_up = [10, 9, 8, 7, 12]
    assert strat.signal(falling_then_up, holding=False) == "BUY"
    assert strat.signal(falling_then_up, holding=True) is None
    rising_then_down = [7, 8, 9, 10, 5]
    assert strat.signal(rising_then_down, holding=True) == "SELL"


def test_strategy_rejects_bad_windows():
    with pytest.raises(ValueError):
        SmaCrossover(fast=30, slow=10)


def test_round_to_tick():
    assert round_to_tick(1503.03) == 1503.05
    assert round_to_tick(1503.01) == 1503.0


def test_trader_round_trip(tmp_path):
    trader = Trader(SmaCrossover(fast=2, slow=4), make_risk(tmp_path), paper=PaperBroker(cash=10_000))
    for p in [1000, 990, 980, 970, 1100]:
        trader.on_price("INFY", p)
    assert trader.paper.positions == {"INFY": 4}  # floor(5000 / 1102.2)
    for p in [1150, 1200, 900]:
        trader.on_price("INFY", p)
    assert trader.paper.positions == {}
    assert len(trader.paper.fills) == 2


def test_backtest_runs_on_sample_data(tmp_path):
    prices = load_prices(SAMPLE)
    risk = make_risk(tmp_path, allowed_symbols=frozenset(prices), max_orders_per_day=100)
    result = run_backtest(prices, SmaCrossover(), risk, cash=100_000)
    assert result.trades > 0
    assert 0 <= result.max_drawdown_pct < 100
