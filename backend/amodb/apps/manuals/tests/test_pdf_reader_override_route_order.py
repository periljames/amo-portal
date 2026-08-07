from __future__ import annotations

from amodb.main import app


def test_precomputed_capabilities_and_form_overrides_precede_legacy_engine_routes() -> None:
    expected = {
        "/manuals/t/{tenant_slug}/{manual_id}/rev/{revision_id}/pdf-capabilities": "precomputed_pdf_reader_capabilities",
        "/manuals/t/{tenant_slug}/{manual_id}/rev/{revision_id}/flatten.pdf": "flatten_completed_form_pages",
    }
    for path, endpoint_name in expected.items():
        matches = [route for route in app.routes if getattr(route, "path", "") == path]
        assert matches, path
        assert getattr(matches[0].endpoint, "__name__", "") == endpoint_name
