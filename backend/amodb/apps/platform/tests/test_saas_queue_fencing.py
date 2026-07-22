from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from amodb.apps.platform import saas_models, saas_queue


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    saas_models.SaaSJob.__table__.create(engine)
    saas_models.SaaSJobEvent.__table__.create(engine)
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)()


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
    assert db.query(saas_models.SaaSJob).filter_by(status="PENDING").count() == 3


def test_complete_and_fail_require_an_active_lease():
    db = _session()
    job = saas_queue.enqueue_job(
        db,
        job_type="EXTERNAL_SIDE_EFFECT",
        payload={},
        idempotency_key="lease-required",
    )

    try:
        saas_queue.complete_job(db, job, {})
        raise AssertionError("completion without a lease should fail")
    except ValueError:
        pass

    claimed = saas_queue.claim_jobs(db, worker_id="worker-two", batch_size=10)[0]
    saas_queue.complete_job(db, claimed, {"ok": True})
    assert claimed.status == "SUCCEEDED"
