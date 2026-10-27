import pytest

from autotrader.broker import ReadOnlyKite


class FakeKite:
    def __init__(self):
        self.calls = []

    def holdings(self):
        return [{"tradingsymbol": "INFY", "quantity": 1}]

    def ltp(self, *instruments):
        return {i: {"last_price": 100.0} for i in instruments}

    def __getattr__(self, name):  # anything else "exists" on the fake, like on the real client
        return lambda *a, **k: self.calls.append(name)


def test_read_methods_pass_through():
    kite = ReadOnlyKite(FakeKite())
    assert kite.holdings() == [{"tradingsymbol": "INFY", "quantity": 1}]
    assert kite.ltp_map(["INFY", "TCS"]) == {"INFY": 100.0, "TCS": 100.0}


@pytest.mark.parametrize("method", [
    "place_order", "modify_order", "cancel_order", "exit_order", "place_autoslice_order",
    "place_gtt", "modify_gtt", "delete_gtt", "place_mf_order", "place_mf_sip", "convert_position",
])
def test_write_methods_are_blocked(method):
    fake = FakeKite()
    kite = ReadOnlyKite(fake)
    with pytest.raises(PermissionError, match="read-only"):
        getattr(kite, method)
    assert fake.calls == []
