"""Settings loaded from environment variables (or a local .env file)."""

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv is optional
    load_dotenv = None

# Live orders are only sent when LIVE_TRADING is set to exactly this phrase.
LIVE_TRADING_PHRASE = "I_UNDERSTAND_THE_RISK"


@dataclass(frozen=True)
class Settings:
    api_key: str | None
    api_secret: str | None
    live_trading: bool
    max_order_value: float
    max_daily_loss: float
    max_open_positions: int
    max_orders_per_day: int
    allowed_symbols: frozenset[str]
    paper_cash: float


def load_settings() -> Settings:
    if load_dotenv:
        load_dotenv()
    symbols = os.getenv("ALLOWED_SYMBOLS", "INFY,TCS,RELIANCE,HDFCBANK")
    return Settings(
        api_key=os.getenv("KITE_API_KEY") or None,
        api_secret=os.getenv("KITE_API_SECRET") or None,
        live_trading=os.getenv("LIVE_TRADING") == LIVE_TRADING_PHRASE,
        max_order_value=float(os.getenv("MAX_ORDER_VALUE", "5000")),
        max_daily_loss=float(os.getenv("MAX_DAILY_LOSS", "1000")),
        max_open_positions=int(os.getenv("MAX_OPEN_POSITIONS", "3")),
        max_orders_per_day=int(os.getenv("MAX_ORDERS_PER_DAY", "10")),
        allowed_symbols=frozenset(s.strip().upper() for s in symbols.split(",") if s.strip()),
        paper_cash=float(os.getenv("PAPER_CASH", "100000")),
    )
