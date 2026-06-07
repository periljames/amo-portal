from datetime import timezone
from zoneinfo import ZoneInfoNotFoundError

from amodb.apps.qms import router


def test_valid_zoneinfo_falls_back_without_system_tzdata(monkeypatch):
    def missing_zoneinfo(_key: str):
        raise ZoneInfoNotFoundError(_key)

    monkeypatch.setattr(router, "ZoneInfo", missing_zoneinfo)

    zone = router._valid_zoneinfo("UTC")

    assert zone is timezone.utc
    assert getattr(zone, "key", "UTC") == "UTC"
