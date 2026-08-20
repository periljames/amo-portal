"""Policy-driven examination selection and item intelligence.

No pass marks, item-quality thresholds, cooldowns or exposure limits are embedded
here.  The calling tenant/course blueprint supplies those controlled values.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
from typing import Iterable, Mapping, Sequence

from .governance_rules import question_eligibility_reasons


def select_question_revisions(
    candidates: Iterable[Mapping[str, object]],
    *,
    on_date,
    selection_rules: Mapping[str, object],
) -> dict[str, object]:
    """Select only current approved revisions and explain every exclusion.

    Selection is deterministic by exposure count then question code/id.  Randomisation
    for presentation may happen after the controlled eligible population/form has been
    frozen, preserving repeatability and auditability of the generated form.
    """
    required_count = int(selection_rules.get("question_count") or 0)
    if required_count <= 0:
        raise ValueError("Exam blueprint must provide a positive controlled question_count.")
    max_exposure = selection_rules.get("max_exposure_count")
    allowed_modules = {str(value) for value in selection_rules.get("module_ids", []) or []}
    allowed_objectives = {str(value) for value in selection_rules.get("learning_objective_ids", []) or []}
    eligible: list[Mapping[str, object]] = []
    excluded: list[dict[str, object]] = []

    for candidate in candidates:
        question = candidate.get("question") if isinstance(candidate.get("question"), Mapping) else candidate
        revision = candidate.get("revision") if isinstance(candidate.get("revision"), Mapping) else candidate
        reasons = question_eligibility_reasons(question, revision, on_date=on_date)
        module_id = str(question.get("module_id") or "")
        objective_id = str(question.get("learning_objective_id") or "")
        if allowed_modules and module_id not in allowed_modules:
            reasons.append("Question is outside the blueprint module scope.")
        if allowed_objectives and objective_id not in allowed_objectives:
            reasons.append("Question is outside the blueprint learning-objective scope.")
        exposure = int(question.get("exposure_count") or 0)
        if max_exposure is not None and exposure >= int(max_exposure):
            reasons.append("Question has reached the blueprint exposure ceiling.")
        if reasons:
            excluded.append({"question_revision_id": str(revision.get("id") or ""), "reasons": reasons})
        else:
            eligible.append(candidate)

    eligible.sort(key=lambda row: (
        int((row.get("question") if isinstance(row.get("question"), Mapping) else row).get("exposure_count") or 0),
        str((row.get("question") if isinstance(row.get("question"), Mapping) else row).get("question_code") or ""),
        str((row.get("revision") if isinstance(row.get("revision"), Mapping) else row).get("id") or ""),
    ))
    if len(eligible) < required_count:
        return {
            "ready": False,
            "selected_revision_ids": [],
            "eligible_count": len(eligible),
            "required_count": required_count,
            "excluded": excluded,
            "blockers": [f"Blueprint requires {required_count} eligible questions but only {len(eligible)} are available."],
        }
    selected = eligible[:required_count]
    return {
        "ready": True,
        "selected_revision_ids": [str((row.get("revision") if isinstance(row.get("revision"), Mapping) else row).get("id")) for row in selected],
        "eligible_count": len(eligible),
        "required_count": required_count,
        "excluded": excluded,
        "blockers": [],
    }


def item_analysis(
    responses: Sequence[Mapping[str, object]],
    *,
    policy: Mapping[str, object],
    source_superseded: bool = False,
    complaint_count: int = 0,
) -> dict[str, object]:
    """Compute auditable item metrics; only policy decides whether review is required."""
    if not responses:
        return {
            "sample_size": 0,
            "response_distribution": {},
            "percent_correct": None,
            "difficulty_index": None,
            "discrimination_index": None,
            "distractor_performance": {},
            "abnormal_patterns": [],
            "complaint_count": complaint_count,
            "source_superseded": source_superseded,
            "review_status": "INSUFFICIENT_DATA",
            "review_reasons": [],
        }

    sample_size = len(responses)
    distribution: Counter[str] = Counter()
    correct_count = 0
    correct_scores: list[tuple[Decimal, bool]] = []
    distractor = defaultdict(lambda: {"selected": 0, "high_group": 0, "low_group": 0})
    for row in responses:
        selected = str(row.get("selected_option") or "")
        if selected:
            distribution[selected] += 1
        correct = bool(row.get("correct"))
        correct_count += int(correct)
        total_score = Decimal(str(row.get("total_score") or 0))
        correct_scores.append((total_score, correct))

    ordered = sorted(correct_scores, key=lambda value: value[0])
    group_fraction = Decimal(str(policy.get("discrimination_group_fraction") or 0))
    group_size = int((Decimal(sample_size) * group_fraction).to_integral_value(rounding="ROUND_FLOOR")) if group_fraction > 0 else 0
    discrimination = None
    if group_size > 0 and sample_size >= group_size * 2:
        low = ordered[:group_size]
        high = ordered[-group_size:]
        high_correct = Decimal(sum(int(value[1]) for value in high)) / Decimal(group_size)
        low_correct = Decimal(sum(int(value[1]) for value in low)) / Decimal(group_size)
        discrimination = high_correct - low_correct

    percent_correct = (Decimal(correct_count) / Decimal(sample_size)) * Decimal("100")
    difficulty = Decimal(correct_count) / Decimal(sample_size)
    review_reasons: list[str] = []
    min_sample = int(policy.get("minimum_sample_size") or 0)
    if min_sample and sample_size < min_sample:
        return {
            "sample_size": sample_size,
            "response_distribution": dict(distribution),
            "percent_correct": percent_correct,
            "difficulty_index": difficulty,
            "discrimination_index": discrimination,
            "distractor_performance": dict(distractor),
            "abnormal_patterns": [],
            "complaint_count": complaint_count,
            "source_superseded": source_superseded,
            "review_status": "INSUFFICIENT_DATA",
            "review_reasons": [],
        }

    min_difficulty = policy.get("minimum_difficulty_index")
    max_difficulty = policy.get("maximum_difficulty_index")
    min_discrimination = policy.get("minimum_discrimination_index")
    complaint_trigger = policy.get("complaint_review_threshold")
    if min_difficulty is not None and difficulty < Decimal(str(min_difficulty)):
        review_reasons.append("Item difficulty is below the controlled review range.")
    if max_difficulty is not None and difficulty > Decimal(str(max_difficulty)):
        review_reasons.append("Item difficulty is above the controlled review range.")
    if min_discrimination is not None and discrimination is not None and discrimination < Decimal(str(min_discrimination)):
        review_reasons.append("Item discrimination is below the controlled review threshold.")
    if complaint_trigger is not None and complaint_count >= int(complaint_trigger):
        review_reasons.append("Repeated item complaints reached the controlled review threshold.")
    if source_superseded:
        review_reasons.append("The controlled source revision referenced by this item has been superseded.")

    return {
        "sample_size": sample_size,
        "response_distribution": dict(distribution),
        "percent_correct": percent_correct,
        "difficulty_index": difficulty,
        "discrimination_index": discrimination,
        "distractor_performance": dict(distractor),
        "abnormal_patterns": [],
        "complaint_count": complaint_count,
        "source_superseded": source_superseded,
        "review_status": "REVIEW_REQUIRED" if review_reasons else "CLEAR",
        "review_reasons": review_reasons,
    }
