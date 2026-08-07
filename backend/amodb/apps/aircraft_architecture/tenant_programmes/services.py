from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from sqlalchemy.orm import Session

from . import models


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def programme_revision_hash(
    programme_code: str,
    revision_code: str,
    aircraft_type_revision_id: str,
    effectivity_rule_version_id: str | None,
    source_reference: str,
    source_revision: str,
    tasks: Iterable[dict[str, Any]],
    base_content_pack_revision_id: str | None = None,
) -> str:
    normalized_tasks = sorted(
        (
            {
                "source_content_task_id": task.get("source_content_task_id"),
                "decision": task.get("decision") or "LEGACY",
                "task_code": task["task_code"],
                "title": task["title"],
                "ata_chapter": task.get("ata_chapter"),
                "intervals": task.get("intervals_json") or {},
                "effectivity": task.get("effectivity_expression_json") or {},
                "source_reference": task["source_reference"],
                "justification": task.get("justification"),
                "approval_reference": task.get("approval_reference"),
                "source_task_hash": task.get("source_task_hash"),
                "metadata": task.get("metadata_json") or {},
            }
            for task in tasks
        ),
        key=lambda task: (task["task_code"], task.get("source_content_task_id") or ""),
    )
    payload = {
        "programme_code": programme_code,
        "revision_code": revision_code,
        "aircraft_type_revision_id": aircraft_type_revision_id,
        "effectivity_rule_version_id": effectivity_rule_version_id,
        "base_content_pack_revision_id": base_content_pack_revision_id,
        "source_reference": source_reference,
        "source_revision": source_revision,
        "tasks": normalized_tasks,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def revision_task_dicts(revision: models.TenantProgrammeRevision) -> list[dict[str, Any]]:
    return [
        {
            "source_content_task_id": task.source_content_task_id,
            "decision": task.decision,
            "task_code": task.task_code,
            "title": task.title,
            "ata_chapter": task.ata_chapter,
            "intervals_json": task.intervals_json or {},
            "effectivity_expression_json": task.effectivity_expression_json or {},
            "source_reference": task.source_reference,
            "justification": task.justification,
            "approval_reference": task.approval_reference,
            "source_task_hash": task.source_task_hash,
            "metadata_json": task.metadata_json or {},
        }
        for task in revision.tasks
    ]


def recompute_revision_hash(revision: models.TenantProgrammeRevision) -> str:
    return programme_revision_hash(
        revision.programme.code,
        revision.revision_code,
        revision.aircraft_type_revision_id,
        revision.effectivity_rule_version_id,
        revision.source_reference,
        revision.source_revision,
        revision_task_dicts(revision),
        revision.base_content_pack_revision_id,
    )


def persist_validation_run(
    db: Session,
    *,
    revision: models.TenantProgrammeRevision,
    baseline_content_hash: str,
    result: dict[str, Any],
    actor_id: str | None,
) -> models.TenantProgrammeValidationRun:
    row = models.TenantProgrammeValidationRun(
        amo_id=revision.programme.amo_id,
        revision_id=revision.id,
        baseline_revision_id=revision.base_content_pack_revision_id,
        programme_content_hash=revision.content_hash or recompute_revision_hash(revision),
        baseline_content_hash=baseline_content_hash,
        status=result["status"],
        blocking_count=result["blocking_count"],
        warning_count=result["warning_count"],
        issues_json=result["issues"],
        summary_json=result["summary"],
        created_by_user_id=actor_id,
    )
    db.add(row)
    db.flush()
    return row


def build_upgrade_impact(
    current_tasks: Iterable[dict[str, Any]],
    proposed_tasks: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    current = {task["task_code"]: task for task in current_tasks}
    proposed = {task["task_code"]: task for task in proposed_tasks}
    added = sorted(set(proposed) - set(current))
    removed = sorted(set(current) - set(proposed))
    changed = sorted(
        code
        for code in set(current) & set(proposed)
        if canonical_json(current[code]) != canonical_json(proposed[code])
    )
    return {
        "added_task_codes": added,
        "removed_task_codes": removed,
        "changed_task_codes": changed,
        "requires_approval": bool(added or removed or changed),
    }


def require_same_tenant(resource_amo_id: str, actor_amo_id: str) -> None:
    if str(resource_amo_id) != str(actor_amo_id):
        raise PermissionError("tenant-scoped maintenance programme is not accessible")
