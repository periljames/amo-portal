from __future__ import annotations

import pytest

from amodb import observability


def test_operation_span_does_not_mask_business_exception(monkeypatch):
    monkeypatch.setenv("OTEL_ENABLED", "true")

    with pytest.raises(ValueError, match="business failure"):
        with observability.operation_span("provider.test", provider="OTHER"):
            raise ValueError("business failure")


def test_operation_span_fails_open_when_tracer_setup_fails(monkeypatch):
    monkeypatch.setenv("OTEL_ENABLED", "true")

    from opentelemetry import trace

    def broken_get_tracer(*_args, **_kwargs):
        raise RuntimeError("tracer unavailable")

    monkeypatch.setattr(trace, "get_tracer", broken_get_tracer)

    executed = False
    with observability.operation_span("provider.test", provider="OTHER"):
        executed = True

    assert executed is True
