from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from amodb.apps.platform import saas_models, saas_providers, saas_queue, saas_secrets, saas_services


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    saas_models.SaaSJob.__table__.create(engine)
    saas_models.SaaSJobEvent.__table__.create(engine)
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)()


def test_provider_secret_encrypts_and_redacts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("PLATFORM_SECRETS_KEY", raising=False)
    encrypted, fingerprint = saas_secrets.encrypt_secret({"api_key": "secret-value", "region": "ke"})

    assert encrypted
    assert "secret-value" not in encrypted
    assert fingerprint == hashlib.sha256(b'{"api_key":"secret-value","region":"ke"}').hexdigest()[:16]
    assert saas_secrets.decrypt_secret(encrypted) == {"api_key": "secret-value", "region": "ke"}
    assert saas_secrets.redact_mapping({"api_key": "secret-value", "nested": {"password": "pass"}}) == {
        "api_key": "[REDACTED]",
        "nested": {"password": "[REDACTED]"},
    }


def test_production_requires_dedicated_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("PLATFORM_SECRETS_KEY", raising=False)
    with pytest.raises(saas_secrets.SecretConfigurationError):
        saas_secrets.encrypt_secret({"api_key": "secret-value"})


def test_stripe_signature_verification() -> None:
    payload = json.dumps({"id": "evt_123", "type": "checkout.session.completed"}).encode()
    timestamp = 1_700_000_000
    secret = "whsec_test"
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256).hexdigest()
    header = f"t={timestamp},v1={expected}"

    assert saas_providers.verify_stripe_signature(
        payload,
        header,
        secret,
        now_epoch=timestamp,
    )
    assert not saas_providers.verify_stripe_signature(
        payload + b"x",
        header,
        secret,
        now_epoch=timestamp,
    )
    assert not saas_providers.verify_stripe_signature(
        payload,
        header,
        secret,
        now_epoch=timestamp + 1000,
    )


def test_queue_is_idempotent_and_claimable() -> None:
    db = _session()
    first = saas_queue.enqueue_job(
        db,
        job_type="PROVIDER_HEALTH_CHECK",
        queue_name="integrations",
        payload={"provider": "stripe"},
        idempotency_key="health:stripe:1",
        commit=True,
    )
    second = saas_queue.enqueue_job(
        db,
        job_type="PROVIDER_HEALTH_CHECK",
        queue_name="integrations",
        payload={"provider": "stripe", "duplicate": True},
        idempotency_key="health:stripe:1",
        commit=True,
    )

    assert first.id == second.id
    claimed = saas_queue.claim_jobs(
        db,
        worker_id="test-worker",
        queue_names=("integrations",),
        batch_size=5,
        lease_seconds=30,
        now=datetime.now(timezone.utc),
    )
    assert [job.id for job in claimed] == [first.id]
    assert claimed[0].status == "RUNNING"
    assert claimed[0].locked_by == "test-worker"

    saas_queue.complete_job(db, claimed[0], {"ok": True})
    assert claimed[0].status == "SUCCEEDED"
    assert claimed[0].result_json == {"ok": True}


def test_failed_job_moves_to_retry_then_dead() -> None:
    db = _session()
    job = saas_queue.enqueue_job(
        db,
        job_type="TEST_FAILURE",
        payload={},
        idempotency_key="failure:1",
        max_attempts=2,
    )
    claimed = saas_queue.claim_jobs(db, worker_id="worker", batch_size=1)[0]
    saas_queue.fail_job(db, claimed, RuntimeError("temporary"), retryable=True)
    assert job.status == "RETRY"

    job.available_at = datetime.now(timezone.utc)
    db.commit()
    claimed = saas_queue.claim_jobs(db, worker_id="worker", batch_size=1)[0]
    saas_queue.fail_job(db, claimed, RuntimeError("final"), retryable=True)
    assert job.status == "DEAD"
    assert job.finished_at is not None


def test_provider_catalog_covers_required_saas_services() -> None:
    catalog = {item["provider"] for item in saas_providers.provider_catalog()}
    assert {"stripe", "mpesa_daraja", "etims_oscu", "etims_vscu", "smtp", "openai", "zendesk"}.issubset(catalog)


def test_module_code_normalization_rejects_unsafe_values() -> None:
    assert saas_services.normalize_module_code("Quality-Module") == "quality_module"
    with pytest.raises(ValueError):
        saas_services.normalize_module_code("../quality")
