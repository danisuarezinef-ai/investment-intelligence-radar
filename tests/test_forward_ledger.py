import json
from radar_forward_ledger import _canonical, _hash, REAL_TRADING


def test_canonical_hash_is_order_independent():
    a={"b":2,"a":1}
    b={"a":1,"b":2}
    assert _canonical(a)==_canonical(b)
    assert _hash(a)==_hash(b)


def test_hash_changes_when_prediction_changes():
    assert _hash({"score":1}) != _hash({"score":2})


def test_real_trading_off():
    assert REAL_TRADING is False
