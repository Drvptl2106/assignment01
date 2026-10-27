"""Portfolio snapshot and rule-based review. Read-only: nothing here can trade.

The suggestions are portfolio-hygiene checks (concentration, big losers/winners,
idle cash), not stock tips. They are prompts for you to look closer and decide.
"""

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

Level = Literal["ALERT", "REVIEW", "INFO"]


@dataclass(frozen=True)
class Holding:
    symbol: str
    quantity: int
    average_price: float
    last_price: float
    day_change_pct: float = 0.0
    sector: str = "Unknown"

    @property
    def invested(self) -> float:
        return self.quantity * self.average_price

    @property
    def value(self) -> float:
        return self.quantity * self.last_price

    @property
    def pnl(self) -> float:
        return self.value - self.invested

    @property
    def pnl_pct(self) -> float:
        return self.pnl / self.invested * 100 if self.invested else 0.0


@dataclass(frozen=True)
class Suggestion:
    level: Level
    symbol: str | None
    message: str


@dataclass(frozen=True)
class Rules:
    max_holding_pct: float = 20.0  # one stock above this share of the portfolio is concentrated
    max_sector_pct: float = 40.0
    loss_alert_pct: float = 20.0  # flag holdings down at least this much
    gain_alert_pct: float = 50.0  # flag holdings up at least this much
    day_move_pct: float = 5.0
    min_holdings: int = 5
    max_cash_pct: float = 30.0


def load_sectors(path: Path) -> dict[str, str]:
    """CSV columns: symbol,sector. Missing file -> empty map."""
    if not path.exists():
        return {}
    with open(path, newline="") as f:
        return {r["symbol"].strip().upper(): r["sector"].strip() for r in csv.DictReader(f)}


def holdings_from_kite(rows: list[dict], sectors: dict[str, str]) -> list[Holding]:
    out = []
    for h in rows:
        qty = h["quantity"] + h.get("t1_quantity", 0)
        if qty <= 0:
            continue
        sym = h["tradingsymbol"]
        out.append(Holding(
            symbol=sym,
            quantity=qty,
            average_price=h["average_price"],
            last_price=h["last_price"],
            day_change_pct=h.get("day_change_percentage", 0.0),
            sector=sectors.get(sym, "Unknown"),
        ))
    return out


def holdings_from_csv(path: Path, sectors: dict[str, str]) -> list[Holding]:
    """CSV columns: symbol,quantity,average_price,last_price[,day_change_pct][,sector]."""
    out = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            sym = r["symbol"].strip().upper()
            out.append(Holding(
                symbol=sym,
                quantity=int(r["quantity"]),
                average_price=float(r["average_price"]),
                last_price=float(r["last_price"]),
                day_change_pct=float(r.get("day_change_pct") or 0),
                sector=(r.get("sector") or "").strip() or sectors.get(sym, "Unknown"),
            ))
    return out


def review(holdings: list[Holding], cash: float = 0.0, rules: Rules = Rules()) -> list[Suggestion]:
    out: list[Suggestion] = []
    if not holdings:
        return [Suggestion("INFO", None, "No holdings found.")]

    invested_value = sum(h.value for h in holdings)
    total = invested_value + cash

    for h in sorted(holdings, key=lambda h: h.value, reverse=True):
        weight = h.value / invested_value * 100
        if weight > rules.max_holding_pct:
            out.append(Suggestion("REVIEW", h.symbol,
                f"{weight:.0f}% of your stock portfolio is in one name (guide: <{rules.max_holding_pct:.0f}%). "
                "Consider whether you'd be comfortable if it fell 30%; trimming or adding other names spreads risk."))
        if h.pnl_pct <= -rules.loss_alert_pct:
            out.append(Suggestion("ALERT", h.symbol,
                f"Down {abs(h.pnl_pct):.0f}% from your average price. Re-check why you bought it: "
                "if that reason no longer holds, decide on an exit level instead of waiting to break even."))
        elif h.pnl_pct >= rules.gain_alert_pct:
            out.append(Suggestion("REVIEW", h.symbol,
                f"Up {h.pnl_pct:.0f}%. Consider booking partial profit or setting a trailing stop-loss "
                "to protect the gain (mind capital gains tax: <1 year is short-term)."))
        if abs(h.day_change_pct) >= rules.day_move_pct:
            out.append(Suggestion("INFO", h.symbol,
                f"Moved {h.day_change_pct:+.1f}% today. Check the news before reacting."))

    by_sector: dict[str, float] = {}
    for h in holdings:
        by_sector[h.sector] = by_sector.get(h.sector, 0.0) + h.value
    for sector, value in sorted(by_sector.items(), key=lambda kv: kv[1], reverse=True):
        weight = value / invested_value * 100
        if sector != "Unknown" and weight > rules.max_sector_pct:
            out.append(Suggestion("REVIEW", None,
                f"{weight:.0f}% of your stocks are in {sector} (guide: <{rules.max_sector_pct:.0f}%). "
                "One bad sector event would hit most of your portfolio."))

    if len(holdings) < rules.min_holdings:
        out.append(Suggestion("INFO", None,
            f"Only {len(holdings)} stock(s). A few more across different sectors, or an index fund/ETF, "
            "reduces single-stock risk."))
    if total and cash / total * 100 > rules.max_cash_pct:
        out.append(Suggestion("INFO", None,
            f"{cash / total * 100:.0f}% of your account is idle cash. Fine if intentional (emergency fund, "
            "waiting to buy); otherwise consider a plan for it."))
    if not out:
        out.append(Suggestion("INFO", None, "Nothing stands out under the current rules."))
    return out


def snapshot(holdings: list[Holding], cash: float, suggestions: list[Suggestion]) -> dict:
    """Plain dict for JSON export, e.g. to paste into Claude for a deeper discussion."""
    invested = sum(h.invested for h in holdings)
    value = sum(h.value for h in holdings)
    return {
        "cash": cash,
        "invested": round(invested, 2),
        "current_value": round(value, 2),
        "pnl": round(value - invested, 2),
        "holdings": [
            {**asdict(h), "value": round(h.value, 2), "pnl": round(h.pnl, 2), "pnl_pct": round(h.pnl_pct, 2),
             "weight_pct": round(h.value / value * 100, 2) if value else 0.0}
            for h in holdings
        ],
        "suggestions": [asdict(s) for s in suggestions],
    }
