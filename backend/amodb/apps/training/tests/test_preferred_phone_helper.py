from types import SimpleNamespace

from amodb.apps.training.router import _preferred_phone


def test_preferred_phone_uses_primary_phone_without_recursion():
    user = SimpleNamespace(phone="  +254700000000  ", secondary_phone="+254711111111")
    assert _preferred_phone(user) == "+254700000000"


def test_preferred_phone_falls_back_to_secondary_phone():
    user = SimpleNamespace(phone="", secondary_phone="+254711111111")
    assert _preferred_phone(user) == "+254711111111"


def test_preferred_phone_handles_missing_values():
    user = SimpleNamespace(email="person@example.com")
    assert _preferred_phone(user) is None
