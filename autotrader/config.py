"""Settings loaded from environment variables (or a local .env file)."""

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv is optional
    load_dotenv = None


@dataclass(frozen=True)
class Settings:
    api_key: str | None
    api_secret: str | None
    max_order_value: float
    max_daily_loss: float
    max_open_positions: int
    max_orders_per_day: int
    allowed_symbols: frozenset[str]
    paper_cash: float
    max_holding_pct: float
    loss_alert_pct: float
    gain_alert_pct: float
    sector_file: str


def load_settings() -> Settings:
    if load_dotenv:
        load_dotenv()
    symbols = os.getenv("ALLOWED_SYMBOLS", "INFY,TCS,RELIANCE,HDFCBANK")
    return Settings(
        api_key=os.getenv("KITE_API_KEY") or None,
        api_secret=os.getenv("KITE_API_SECRET") or None,
        max_order_value=float(os.getenv("MAX_ORDER_VALUE", "5000")),
        max_daily_loss=float(os.getenv("MAX_DAILY_LOSS", "1000")),
        max_open_positions=int(os.getenv("MAX_OPEN_POSITIONS", "3")),
        max_orders_per_day=int(os.getenv("MAX_ORDERS_PER_DAY", "10")),
        allowed_symbols=frozenset(s.strip().upper() for s in symbols.split(",") if s.strip()),
        paper_cash=float(os.getenv("PAPER_CASH", "100000")),
        max_holding_pct=float(os.getenv("MAX_HOLDING_PCT", "20")),
        loss_alert_pct=float(os.getenv("LOSS_ALERT_PCT", "20")),
        gain_alert_pct=float(os.getenv("GAIN_ALERT_PCT", "50")),
        sector_file=os.getenv("SECTOR_FILE", "data/sectors.csv"),
    )
