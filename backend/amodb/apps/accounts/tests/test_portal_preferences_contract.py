from __future__ import annotations

import pytest

from amodb.apps.accounts.portal_preferences_router import (
    PortalPreferencesPatch,
    PortalPreferencesRead,
    router,
)


def test_portal_preference_routes_are_mounted_on_router() -> None:
    route_methods = {
        (route.path, method)
        for route in router.routes
        for method in (getattr(route, "methods", None) or set())
    }
    assert ("/portal-preferences", "GET") in route_methods
    assert ("/portal-preferences", "PATCH") in route_methods


def test_portal_preference_defaults_are_accessible() -> None:
    preferences = PortalPreferencesRead(user_id="user-1", amo_id="amo-1")
    assert preferences.text_scale == "standard"
    assert preferences.density == "comfortable"
    assert preferences.motion == "system"
    assert preferences.color_scheme == "system"
    assert preferences.accent == "tenant"


def test_portal_preference_patch_rejects_unknown_scale() -> None:
    with pytest.raises(Exception):
        PortalPreferencesPatch(text_scale="tiny")


def test_portal_preference_patch_accepts_accessible_scales() -> None:
    assert PortalPreferencesPatch(text_scale="large").text_scale == "large"
    assert PortalPreferencesPatch(text_scale="extra-large").text_scale == "extra-large"
