"""Brokers: an in-memory PaperBroker for practice and a thin KiteBroker wrapper."""

from dataclasses import dataclass, field
from typing import Literal

Side = Literal["BUY", "SELL"]


@dataclass(frozen=True)
class Order:
    symbol: str
    side: Side
    quantity: int
    limit_price: float
    exchange: str = "NSE"
    product: str = "CNC"  # delivery; avoids intraday auto square-off surprises


@dataclass(frozen=True)
class Fill:
    order: Order
    price: float
    order_id: str
    realized_pnl: float = 0.0


@dataclass
class PaperBroker:
    """Simulates fills against the price you pass in. No money moves."""

    cash: float
    positions: dict[str, int] = field(default_factory=dict)
    avg_price: dict[str, float] = field(default_factory=dict)
    fills: list[Fill] = field(default_factory=list)

    def place_order(self, order: Order, market_price: float) -> Fill | None:
        # A limit order only fills if the market is at or better than the limit.
        if order.side == "BUY" and market_price > order.limit_price:
            return None
        if order.side == "SELL" and market_price < order.limit_price:
            return None

        held = self.positions.get(order.symbol, 0)
        pnl = 0.0
        if order.side == "BUY":
            cost = order.quantity * market_price
            if cost > self.cash:
                return None
            self.cash -= cost
            new_qty = held + order.quantity
            prev_cost = held * self.avg_price.get(order.symbol, 0.0)
            self.avg_price[order.symbol] = (prev_cost + cost) / new_qty
            self.positions[order.symbol] = new_qty
        else:
            if order.quantity > held:
                return None
            self.cash += order.quantity * market_price
            pnl = (market_price - self.avg_price[order.symbol]) * order.quantity
            self.positions[order.symbol] = held - order.quantity
            if self.positions[order.symbol] == 0:
                del self.positions[order.symbol]
                del self.avg_price[order.symbol]

        fill = Fill(order, market_price, f"paper-{len(self.fills) + 1}", pnl)
        self.fills.append(fill)
        return fill

    def equity(self, prices: dict[str, float]) -> float:
        return self.cash + sum(qty * prices[sym] for sym, qty in self.positions.items())


class KiteBroker:
    """Wraps a logged-in kiteconnect.KiteConnect client."""

    def __init__(self, kite):
        self.kite = kite

    def profile(self) -> dict:
        return self.kite.profile()

    def holdings(self) -> list[dict]:
        return self.kite.holdings()

    def positions(self) -> dict:
        return self.kite.positions()

    def margins(self) -> dict:
        return self.kite.margins()

    def open_quantities(self) -> dict[str, int]:
        """Delivery shares held: settled + T1 holdings plus today's CNC trades."""
        qty: dict[str, int] = {}
        for h in self.kite.holdings():
            qty[h["tradingsymbol"]] = qty.get(h["tradingsymbol"], 0) + h["quantity"] + h.get("t1_quantity", 0)
        for p in self.kite.positions()["day"]:
            if p["product"] == "CNC":
                qty[p["tradingsymbol"]] = qty.get(p["tradingsymbol"], 0) + p["quantity"]
        return {sym: q for sym, q in qty.items() if q > 0}

    def day_pnl(self) -> float:
        return sum(p["pnl"] for p in self.kite.positions()["day"])

    def ltp(self, symbols: list[str], exchange: str = "NSE") -> dict[str, float]:
        data = self.kite.ltp(*[f"{exchange}:{s}" for s in symbols])
        return {key.split(":", 1)[1]: v["last_price"] for key, v in data.items()}

    def place_order(self, order: Order) -> str:
        # LIMIT orders only: SEBI rules restrict plain market orders via API, and
        # a limit caps how much slippage a bug can cost you.
        return self.kite.place_order(
            variety=self.kite.VARIETY_REGULAR,
            exchange=order.exchange,
            tradingsymbol=order.symbol,
            transaction_type=order.side,
            quantity=order.quantity,
            product=order.product,
            order_type=self.kite.ORDER_TYPE_LIMIT,
            price=order.limit_price,
            validity=self.kite.VALIDITY_DAY,
            tag="autotrader",
        )
