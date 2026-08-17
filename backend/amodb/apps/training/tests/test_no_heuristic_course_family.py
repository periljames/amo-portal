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
