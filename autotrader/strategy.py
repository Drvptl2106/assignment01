"""A deliberately simple example strategy. It is a learning tool, not an edge."""

from dataclasses import dataclass

from autotrader.broker import Side


def sma(values: list[float], window: int) -> float:
    return sum(values[-window:]) / window


@dataclass(frozen=True)
class SmaCrossover:
    """Go long when the fast average crosses above the slow one; exit on the reverse cross."""

    fast: int = 10
    slow: int = 30

    def __post_init__(self):
        if not 0 < self.fast < self.slow:
            raise ValueError("need 0 < fast < slow")

    def signal(self, closes: list[float], holding: bool) -> Side | None:
        if len(closes) < self.slow + 1:
            return None
        prev_fast, prev_slow = sma(closes[:-1], self.fast), sma(closes[:-1], self.slow)
        fast, slow = sma(closes, self.fast), sma(closes, self.slow)
        if not holding and prev_fast <= prev_slow and fast > slow:
            return "BUY"
        if holding and prev_fast >= prev_slow and fast < slow:
            return "SELL"
        return None
