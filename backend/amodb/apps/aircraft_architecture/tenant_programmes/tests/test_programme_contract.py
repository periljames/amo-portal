import pytest

from amodb.apps.aircraft_architecture.tenant_programmes import services


def _task(code: str, interval: int):
    return {
        "task_code": code,
        "title": code,
        "ata_chapter": "05",
        "intervals_json": {"flight_hours": interval},
        "effectivity_expression_json": {},
        "source_reference": "MPD 76",
        "metadata_json": {},
    }


def test_revision_hash_is_task_order_independent():
    tasks = [_task("05-10-01", 500), _task("05-20-01", 1000)]
    left = services.programme_revision_hash("DHC8-AMP", "R1", "type-r1", "eff-r1", "AMP", "1", tasks)
    right = services.programme_revision_hash("DHC8-AMP", "R1", "type-r1", "eff-r1", "AMP", "1", list(reversed(tasks)))
    assert left == right


def test_upgrade_impact_never_silently_changes_tasks():
    impact = services.build_upgrade_impact(
        [_task("A", 500), _task("B", 1000)],
        [_task("A", 600), _task("C", 1000)],
    )
    assert impact == {
        "added_task_codes": ["C"],
        "removed_task_codes": ["B"],
        "changed_task_codes": ["A"],
        "requires_approval": True,
    }


def test_tenant_scope_is_enforced():
    services.require_same_tenant("amo-a", "amo-a")
    with pytest.raises(PermissionError):
        services.require_same_tenant("amo-a", "amo-b")
