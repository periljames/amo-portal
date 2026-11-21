from types import SimpleNamespace

from amodb.apps.quality.service import build_car_invite_link


def test_new_car_invitation_uses_fragment_bearer_and_canonical_public_route(monkeypatch):
    for name in (
        "CAR_INVITE_PUBLIC_BASE_URL",
        "PORTAL_FRONTEND_BASE_URL",
        "APP_PUBLIC_BASE_URL",
        "PUBLIC_BASE_URL",
        "FRONTEND_BASE_URL",
        "PORTAL_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    car = SimpleNamespace(invite_token="opaque_token-123")
    assert build_car_invite_link(car, request_origin="https://portal.example/") == (
        "https://portal.example/qms/car-access#token=opaque_token-123"
    )


def test_configured_public_base_precedes_request_origin(monkeypatch):
    monkeypatch.setenv("CAR_INVITE_PUBLIC_BASE_URL", "https://public.example/")
    monkeypatch.setenv("PORTAL_FRONTEND_BASE_URL", "https://fallback.example")

    car = SimpleNamespace(invite_token="opaque_token-123")
    assert build_car_invite_link(car, request_origin="https://request.example") == (
        "https://public.example/qms/car-access#token=opaque_token-123"
    )
