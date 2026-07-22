from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from amodb.apps.platform import saas_models, saas_queue


def _factory(file_backed: bool = False):
    if file_backed:
        path = Path(tempfile.mkdtemp()) / "queue.db"
        engine = create_engine(f"sqlite+pysqlite:///{path}", future=True)
    else:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    saas_models.SaaSJob.__table__.create(engine)
    saas_models.SaaSJobEvent.__table__.create(engine)
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)


def _session():
    return _factory()()


def test_claim_width_is_one_even_when_worker_requests_a_batch():
    db = _session()
    for index in range(4):
        saas_queue.enqueue_job(
            db,
            job_type="EXTERNAL_SIDE_EFFECT",
            payload={"index": index},
            idempotency_key=f"effect:{index}",
            queue_name="billing",
        )

    claimed = saas_queue.claim_jobs(
        db,
        worker_id="worker-one",
        queue_names=("billing",),
        batch_size=20,
        lease_seconds=90,
    )

    assert len(claimed) == 1
    assert claimed[0].status == "RUNNING"
    assert claimed[0].lease_token
    assert db.query(saas_models.SaaSJob).filter_by(status="PENDING").count() == 3


def test_complete_and_fail_require_an_active_lease():
    db = _session()
    job = saas_queue.enqueue_job(
        db,
        job_type="EXTERNAL_SIDE_EFFECT",
        payload={},
        idempotency_key="lease-required",
    )

    with pytest.raises(saas_queue.LeaseLostError):
        saas_queue.complete_job(db, job, {})

    claimed = saas_queue.claim_jobs(db, worker_id="worker-two", batch_size=10)[0]
    saas_queue.complete_job(db, claimed, {"ok": True}, worker_id="worker-two")
    assert claimed.status == "SUCCEEDED"


def test_stale_worker_cannot_complete_after_lease_token_changes():
    Session = _factory(file_backed=True)
    first = Session()
    second = Session()
    job = saas_queue.enqueue_job(
        first,
        job_type="ETIMS_FISCALIZE_INVOICE",
        payload={},
        idempotency_key="fiscalize:fenced",
    )
    claimed = saas_queue.claim_jobs(first, worker_id="worker-old", lease_seconds=60)[0]
    original_token = claimed.lease_token

    current = second.get(saas_models.SaaSJob, job.id)
    current.locked_by = "worker-new"
    current.lease_token = "replacement-fence-token"
    second.commit()

    assert claimed.lease_token == original_token
    with pytest.raises(saas_queue.LeaseLostError):
        saas_queue.complete_job(first, claimed, {"duplicate": True}, worker_id="worker-old")

    second.refresh(current)
    assert current.status == "RUNNING"
    assert current.locked_by == "worker-new"
    assert current.lease_token == "replacement-fence-token"


def test_heartbeat_requires_the_current_fence():
    Session = _factory(file_backed=True)
    first = Session()
    second = Session()
    job = saas_queue.enqueue_job(
        first,
        job_type="PROVIDER_HEALTH_CHECK",
        payload={},
        idempotency_key="heartbeat:fenced",
    )
    claimed = saas_queue.claim_jobs(first, worker_id="worker-heartbeat", lease_seconds=60)[0]

    current = second.get(saas_models.SaaSJob, job.id)
    current.lease_token = "new-heartbeat-fence"
    second.commit()

    with pytest.raises(saas_queue.LeaseLostError):
        saas_queue.heartbeat_job(
            first,
            claimed,
            worker_id="worker-heartbeat",
            lease_seconds=60,
        )
