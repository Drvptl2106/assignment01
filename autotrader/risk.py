"""Pre-trade risk checks. Every order must pass through RiskManager.check()."""

from dataclasses import dataclass, field
from pathlib import Path

from autotrader.broker import Order

# Create this file (e.g. `touch KILL`) to stop all new orders immediately.
KILL_SWITCH_FILE = Path("KILL")


class RiskError(Exception):
    """Raised when an order is rejected by a risk rule."""


@dataclass
class RiskManager:
    max_order_value: float
    max_daily_loss: float
    max_open_positions: int
    allowed_symbols: frozenset[str]
    max_orders_per_day: int = 10
    kill_switch_file: Path = KILL_SWITCH_FILE
    realized_pnl_today: float = 0.0
    orders_today: int = 0
    halted_reason: str | None = field(default=None)

    def check(self, order: Order, open_positions: dict[str, int]) -> None:
        if self.kill_switch_file.exists():
            self.halt(f"kill switch file '{self.kill_switch_file}' present")
        if self.halted_reason:
            raise RiskError(f"trading halted: {self.halted_reason}")
        if order.symbol not in self.allowed_symbols:
            raise RiskError(f"{order.symbol} is not in the allowed symbol list")
        if order.quantity <= 0:
            raise RiskError("quantity must be positive")
        if order.limit_price <= 0:
            raise RiskError("limit price must be positive")
        if self.orders_today >= self.max_orders_per_day:
            raise RiskError(f"already sent {self.orders_today} orders today (max {self.max_orders_per_day})")
        value = order.quantity * order.limit_price
        # The size cap limits new exposure only; exits are never blocked by it.
        if order.side == "BUY" and value > self.max_order_value:
            raise RiskError(f"order value {value:.2f} exceeds max {self.max_order_value:.2f}")
        held = open_positions.get(order.symbol, 0)
        if order.side == "SELL" and order.quantity > held:
            raise RiskError(f"cannot sell {order.quantity} {order.symbol}, only {held} held (no shorting)")
        if order.side == "BUY" and held == 0:
            open_count = sum(1 for qty in open_positions.values() if qty > 0)
            if open_count >= self.max_open_positions:
                raise RiskError(f"already at max open positions ({self.max_open_positions})")

    def record_order(self) -> None:
        self.orders_today += 1

    def record_pnl(self, pnl: float) -> None:
        self.set_pnl(self.realized_pnl_today + pnl)

    def set_pnl(self, pnl_today: float) -> None:
        self.realized_pnl_today = pnl_today
        if self.realized_pnl_today <= -self.max_daily_loss:
            self.halt(f"daily loss limit hit ({self.realized_pnl_today:.2f})")

    def new_day(self) -> None:
        """Reset daily counters. A halt is not cleared; restart the process deliberately."""
        self.realized_pnl_today = 0.0
        self.orders_today = 0

    def halt(self, reason: str) -> None:
        if not self.halted_reason:
            self.halted_reason = reason
