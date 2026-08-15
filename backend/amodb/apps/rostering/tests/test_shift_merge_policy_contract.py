from __future__ import annotations

import inspect

from amodb.apps.rostering import template_usage_policy


def test_duplicate_shift_merge_requires_explicit_policy_resolution():
    source = inspect.getsource(template_usage_policy.merge_duplicate_template)
    assert 'policy_resolution not in {"KEEP_TARGET", "KEEP_SOURCE"}' in source
    assert "source_policy_before" in source
    assert "target_policy_before" in source
    assert "verification_status" in source
    assert "effective_from" in source
    assert "source_reference" in source


def test_keep_source_moves_the_complete_policy_to_the_canonical_shift():
    source = inspect.getsource(template_usage_policy._copy_policy)
    for field in (
        "unpaid_break_minutes",
        "calendar_mode",
        "duty_semantic",
        "verification_status",
        "effective_from",
        "effective_to",
        "source_reference",
    ):
        assert f'"{field}"' in source
