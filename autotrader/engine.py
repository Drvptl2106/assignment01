"""Turns strategy signals into risk-checked orders for the simulated PaperBroker."""

import math
from dataclasses import dataclass, field

from autotrader.broker import Order, PaperBroker
from autotrader.risk import RiskError, RiskManager
from autotrader.strategy import SmaCrossover

TICK_SIZE = 0.05  # NSE equity tick size
LIMIT_BUFFER = 0.002  # 0.2% through the last price so the limit order is marketable


def round_to_tick(price: float) -> float:
    return round(round(price / TICK_SIZE) * TICK_SIZE, 2)


@dataclass
class Trader:
    strategy: SmaCrossover
    risk: RiskManager
    paper: PaperBroker
    history: dict[str, list[float]] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)

    def on_price(self, symbol: str, price: float, label: str = "") -> None:
        closes = self.history.setdefault(symbol, [])
        closes.append(price)
        positions = dict(self.paper.positions)
        held = positions.get(symbol, 0)
        side = self.strategy.signal(closes, holding=held > 0)
        if side is None:
            return

        if side == "BUY":
            limit = round_to_tick(price * (1 + LIMIT_BUFFER))
            quantity = math.floor(self.risk.max_order_value / limit)
        else:
            limit = round_to_tick(price * (1 - LIMIT_BUFFER))
            quantity = held
        if quantity <= 0:
            self.log.append(f"{label} {symbol} {side} skipped: price {price} too high for max order value")
            return

        order = Order(symbol, side, quantity, limit)
        try:
            self.risk.check(order, positions)
        except RiskError as exc:
            self.log.append(f"{label} {symbol} {side} rejected: {exc}")
            return

        self.risk.record_order()
        fill = self.paper.place_order(order, price)
        if fill is None:
            self.log.append(f"{label} {symbol} {side} x{quantity} @ {limit} not filled")
            return
        self.risk.record_pnl(fill.realized_pnl)
        self.log.append(
            f"{label} PAPER {side} {symbol} x{quantity} @ {fill.price:.2f}"
            + (f" pnl {fill.realized_pnl:+.2f}" if side == "SELL" else "")
        )
