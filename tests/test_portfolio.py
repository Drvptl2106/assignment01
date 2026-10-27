from pathlib import Path

from autotrader.portfolio import Holding, Rules, holdings_from_csv, holdings_from_kite, load_sectors, review, snapshot

DATA = Path(__file__).parent.parent / "data"


def messages(suggestions, symbol=None):
    return [s.message for s in suggestions if s.symbol == symbol]


def test_holding_math():
    h = Holding("INFY", 10, 100.0, 120.0)
    assert (h.invested, h.value, h.pnl, h.pnl_pct) == (1000, 1200, 200, 20)


def test_holdings_from_kite_adds_t1_and_skips_empty():
    rows = [
        {"tradingsymbol": "INFY", "quantity": 3, "t1_quantity": 2, "average_price": 10, "last_price": 11,
         "day_change_percentage": 1.5},
        {"tradingsymbol": "TCS", "quantity": 0, "t1_quantity": 0, "average_price": 10, "last_price": 11},
    ]
    [h] = holdings_from_kite(rows, {"INFY": "IT"})
    assert (h.symbol, h.quantity, h.sector, h.day_change_pct) == ("INFY", 5, "IT", 1.5)


def test_review_flags_concentration_losses_gains_and_moves():
    holdings = [
        Holding("BIG", 10, 100, 100),           # 1000 of 1900 -> 53%
        Holding("LOSER", 10, 50, 30),           # -40%
        Holding("WINNER", 10, 20, 40, day_change_pct=-6),  # +100%, big day move
        Holding("OK", 10, 20, 20),
        Holding("OK2", 10, 10, 10),
    ]
    out = review(holdings, rules=Rules(max_holding_pct=40))
    assert any("in one name" in m for m in messages(out, "BIG"))
    assert any(s.level == "ALERT" and "Down 40%" in s.message for s in out if s.symbol == "LOSER")
    assert any("Up 100%" in m for m in messages(out, "WINNER"))
    assert any("-6.0% today" in m for m in messages(out, "WINNER"))
    assert messages(out, "OK") == []


def test_review_portfolio_level_checks():
    holdings = [Holding("A", 1, 100, 100, sector="IT"), Holding("B", 1, 100, 100, sector="IT")]
    out = messages(review(holdings, cash=1000, rules=Rules(max_holding_pct=100)))
    assert any("in IT" in m for m in out)
    assert any("Only 2 stock" in m for m in out)
    assert any("idle cash" in m for m in out)


def test_review_empty_and_quiet():
    assert review([])[0].message == "No holdings found."
    calm = [Holding(s, 1, 100, 100, sector=sec) for s, sec in
            [("A", "IT"), ("B", "Banking"), ("C", "FMCG"), ("D", "Auto"), ("E", "Pharma")]]
    assert [s.message for s in review(calm)] == ["Nothing stands out under the current rules."]


def test_sample_csv_and_snapshot():
    holdings = holdings_from_csv(DATA / "sample_holdings.csv", load_sectors(DATA / "sectors.csv"))
    assert len(holdings) == 6 and all(h.sector != "Unknown" for h in holdings)
    snap = snapshot(holdings, 5000, review(holdings, 5000))
    assert snap["cash"] == 5000
    assert round(sum(h["weight_pct"] for h in snap["holdings"])) == 100
    assert snap["suggestions"]


def test_missing_sector_file(tmp_path):
    assert load_sectors(tmp_path / "nope.csv") == {}
