"""Submission adapter for governed Workforce personnel mutations."""
from __future__ import annotations

from sqlalchemy.orm import Session

from . import bulk_service


def submit_personnel_mutation(
    db: Session,
    *,
    amo_id: str,
    actor,
    idempotency_key: str,
    payload,
):
    user_ids, selection_token = bulk_service._resolve_checked_selection(
        db, amo_id=amo_id, payload=payload
    )
    mutation_payload = payload.model_dump(
        mode="json",
        exclude={"selection", "expected_match_count", "expected_selection_token", "mutation_type"},
    )
    item_inputs = {user_id: dict(mutation_payload) for user_id in user_ids}
    row, created = bulk_service._create_operation(
        db,
        amo_id=amo_id,
        actor_user_id=str(actor.id),
        operation_type=payload.mutation_type,
        idempotency_key=idempotency_key,
        selection_token=selection_token,
        user_ids=user_ids,
        selection_snapshot=payload.selection.model_dump(mode="json"),
        payload_json=mutation_payload,
        item_inputs=item_inputs,
    )
    return bulk_service._operation_read(row), created
