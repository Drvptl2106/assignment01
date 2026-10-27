"""A simulated PaperBroker for practice and a read-only gateway to Kite Connect."""

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
    product: str = "CNC"


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


class ReadOnlyKite:
    """Exposes only the read methods of a kiteconnect.KiteConnect client.

    Order, GTT, mutual fund and SIP methods are deliberately unreachable, so a bug
    (or a future change) in this project cannot place, modify or cancel anything.
    """

    ALLOWED = frozenset({
        "profile", "margins", "holdings", "positions", "orders", "trades",
        "mf_holdings", "ltp", "ohlc", "quote", "instruments", "historical_data",
    })

    def __init__(self, kite):
        self._kite = kite

    def __getattr__(self, name):
        if name not in self.ALLOWED:
            raise PermissionError(f"'{name}' is blocked: this project is read-only")
        return getattr(self._kite, name)

    def ltp_map(self, symbols: list[str], exchange: str = "NSE") -> dict[str, float]:
        data = self._kite.ltp(*[f"{exchange}:{s}" for s in symbols])
        return {key.split(":", 1)[1]: v["last_price"] for key, v in data.items()}
