from pathlib import Path
from types import SimpleNamespace

from amodb.apps.training import compliance
from amodb.apps.training import models as training_models


def _course(pk: str, code: str, kind, **overrides):
    values = {
        "id": pk,
        "course_id": code,
        "course_name": code,
        "kind": kind,
        "status": getattr(kind, "value", str(kind)),
        "group_code": None,
        "prerequisite_course_id": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_compliance_family_key_does_not_strip_init_ref_suffixes():
    initial = _course("a", "HF-INIT", training_models.TrainingKind.INITIAL)
    recurrent = _course("b", "HF-REF", training_models.TrainingKind.REFRESHER)
    assert compliance._course_family_key(initial) != compliance._course_family_key(recurrent)


def test_compliance_family_key_respects_explicit_group_code():
    initial = _course("a", "HF-INIT", training_models.TrainingKind.INITIAL, group_code="HF")
    recurrent = _course("b", "HF-REF", training_models.TrainingKind.REFRESHER, group_code="HF")
    assert compliance._course_family_key(initial) == compliance._course_family_key(recurrent) == "group:hf"


def test_legacy_runtime_heuristics_and_synthetic_completion_paths_stay_deleted():
    repo = Path(__file__).resolve().parents[5]
    router_source = (repo / "backend/amodb/apps/training/router.py").read_text(encoding="utf-8")
    compliance_source = (repo / "backend/amodb/apps/training/compliance.py").read_text(encoding="utf-8")
    frontend_source = (repo / "frontend/src/pages/TrainingCompetencePage.tsx").read_text(encoding="utf-8")

    assert "_seed_refresher_records_from_initial" not in router_source
    assert "AUTO-SEEDED FROM INITIAL" not in router_source
    assert "_course_family_key_from_course" not in router_source
    assert "_normalized_course_text" not in compliance_source
    assert "function coursePhase" not in frontend_source
    assert "function familyKey" not in frontend_source
