from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable


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
) -> str:
    normalized_tasks = sorted(
        (
            {
                "task_code": task["task_code"],
                "title": task["title"],
                "ata_chapter": task.get("ata_chapter"),
                "intervals": task.get("intervals_json") or {},
                "effectivity": task.get("effectivity_expression_json") or {},
                "source_reference": task["source_reference"],
                "metadata": task.get("metadata_json") or {},
            }
            for task in tasks
        ),
        key=lambda task: task["task_code"],
    )
    payload = {
        "programme_code": programme_code,
        "revision_code": revision_code,
        "aircraft_type_revision_id": aircraft_type_revision_id,
        "effectivity_rule_version_id": effectivity_rule_version_id,
        "source_reference": source_reference,
        "source_revision": source_revision,
        "tasks": normalized_tasks,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


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
