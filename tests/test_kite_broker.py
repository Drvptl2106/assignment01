from autotrader.broker import KiteBroker, Order
from autotrader.engine import Trader
from autotrader.risk import RiskManager
from autotrader.strategy import SmaCrossover


class FakeKite:
    VARIETY_REGULAR = "regular"
    ORDER_TYPE_LIMIT = "LIMIT"
    VALIDITY_DAY = "DAY"

    def __init__(self):
        self.orders = []

    def holdings(self):
        return [
            {"tradingsymbol": "INFY", "quantity": 3, "t1_quantity": 1},
            {"tradingsymbol": "TCS", "quantity": 0, "t1_quantity": 0},
        ]

    def positions(self):
        return {
            "day": [
                {"tradingsymbol": "INFY", "product": "CNC", "quantity": 2, "pnl": -50.0},
                {"tradingsymbol": "SBIN", "product": "MIS", "quantity": 10, "pnl": 20.0},
            ]
        }

    def ltp(self, *instruments):
        return {i: {"last_price": 100.0} for i in instruments}

    def place_order(self, **params):
        self.orders.append(params)
        return f"order-{len(self.orders)}"


def test_open_quantities_counts_holdings_t1_and_cnc_day_trades():
    assert KiteBroker(FakeKite()).open_quantities() == {"INFY": 6}


def test_day_pnl_and_ltp():
    broker = KiteBroker(FakeKite())
    assert broker.day_pnl() == -30.0
    assert broker.ltp(["INFY", "TCS"]) == {"INFY": 100.0, "TCS": 100.0}


def test_place_order_sends_limit_order():
    kite = FakeKite()
    order_id = KiteBroker(kite).place_order(Order("INFY", "BUY", 2, 1500.05))
    assert order_id == "order-1"
    assert kite.orders[0] == {
        "variety": "regular",
        "exchange": "NSE",
        "tradingsymbol": "INFY",
        "transaction_type": "BUY",
        "quantity": 2,
        "product": "CNC",
        "order_type": "LIMIT",
        "price": 1500.05,
        "validity": "DAY",
        "tag": "autotrader",
    }


def test_live_trader_sells_live_holdings(tmp_path):
    kite = FakeKite()
    risk = RiskManager(
        max_order_value=5000,
        max_daily_loss=1000,
        max_open_positions=3,
        allowed_symbols=frozenset({"INFY"}),
        kill_switch_file=tmp_path / "KILL",
    )
    trader = Trader(SmaCrossover(fast=2, slow=4), risk, live=KiteBroker(kite))
    for p in [7, 8, 9, 10, 5]:
        trader.on_price("INFY", p)
    assert [(o["transaction_type"], o["quantity"]) for o in kite.orders] == [("SELL", 6)]
