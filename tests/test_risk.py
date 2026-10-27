import pytest

from autotrader.broker import Order
from autotrader.risk import RiskError, RiskManager


@pytest.fixture
def risk(tmp_path):
    return RiskManager(
        max_order_value=5000,
        max_daily_loss=1000,
        max_open_positions=2,
        max_orders_per_day=3,
        allowed_symbols=frozenset({"INFY", "TCS", "SBIN"}),
        kill_switch_file=tmp_path / "KILL",
    )


def test_allows_small_buy(risk):
    risk.check(Order("INFY", "BUY", 2, 1500), {})


def test_rejects_unknown_symbol(risk):
    with pytest.raises(RiskError, match="allowed symbol"):
        risk.check(Order("ADANIENT", "BUY", 1, 100), {})


def test_rejects_oversized_buy_but_allows_large_exit(risk):
    with pytest.raises(RiskError, match="exceeds max"):
        risk.check(Order("INFY", "BUY", 4, 1500), {})
    risk.check(Order("INFY", "SELL", 4, 1500), {"INFY": 4})


def test_rejects_short_selling(risk):
    with pytest.raises(RiskError, match="no shorting"):
        risk.check(Order("INFY", "SELL", 1, 1500), {})


def test_max_open_positions(risk):
    held = {"INFY": 1, "TCS": 1}
    with pytest.raises(RiskError, match="max open positions"):
        risk.check(Order("SBIN", "BUY", 1, 800), held)
    risk.check(Order("INFY", "BUY", 1, 1500), held)  # adding to an existing position is fine


def test_max_orders_per_day(risk):
    for _ in range(3):
        risk.record_order()
    with pytest.raises(RiskError, match="orders today"):
        risk.check(Order("INFY", "BUY", 1, 1500), {})
    risk.new_day()
    risk.check(Order("INFY", "BUY", 1, 1500), {})


def test_daily_loss_halts_and_stays_halted(risk):
    risk.record_pnl(-600)
    risk.check(Order("INFY", "BUY", 1, 1500), {})
    risk.record_pnl(-400)
    with pytest.raises(RiskError, match="daily loss"):
        risk.check(Order("INFY", "BUY", 1, 1500), {})
    risk.new_day()
    with pytest.raises(RiskError, match="halted"):
        risk.check(Order("INFY", "BUY", 1, 1500), {})


def test_kill_switch_file(risk):
    risk.kill_switch_file.touch()
    with pytest.raises(RiskError, match="kill switch"):
        risk.check(Order("INFY", "BUY", 1, 1500), {})
