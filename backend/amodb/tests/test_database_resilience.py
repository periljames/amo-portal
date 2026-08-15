from __future__ import annotations

from amodb.database_resilience import DatabaseCircuitBreaker, is_database_disconnect


def test_database_circuit_opens_fails_fast_and_recovers() -> None:
    circuit = DatabaseCircuitBreaker()

    assert circuit.allow_request() is True
    assert circuit.mark_failure("server closed the connection unexpectedly") is True
    assert circuit.allow_request() is False
    assert circuit.retry_after_seconds() >= 1
    assert circuit.snapshot()["state"] == "offline"

    assert circuit.begin_probe(force=True) is True
    circuit.mark_success()
    circuit.end_probe()

    snapshot = circuit.snapshot()
    assert snapshot["state"] == "online"
    assert snapshot["consecutive_failures"] == 0
    assert circuit.allow_request() is True


def test_database_probe_is_single_flight() -> None:
    circuit = DatabaseCircuitBreaker()
    circuit.mark_failure("connection timed out")

    assert circuit.begin_probe(force=True) is True
    assert circuit.begin_probe(force=True) is False
    circuit.end_probe()
    assert circuit.begin_probe(force=True) is True
    circuit.end_probe()


def test_disconnect_classifier_ignores_business_errors() -> None:
    assert is_database_disconnect(RuntimeError("SSL connection has been closed unexpectedly")) is True
    assert is_database_disconnect(RuntimeError("duplicate key violates unique constraint")) is False
