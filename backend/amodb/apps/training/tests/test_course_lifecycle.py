from types import SimpleNamespace

from amodb.apps.training import course_lifecycle


def _course(**kwargs):
    defaults = {
        "id": "course",
        "course_id": "COURSE",
        "course_name": "Course",
        "kind": None,
        "status": None,
        "group_code": None,
        "prerequisite_course_id": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_kind_never_comes_from_course_title_or_code():
    assert course_lifecycle.training_kind_for_course(
        _course(course_id="HF-INIT", course_name="Initial Human Factors")
    ) == "OTHER"
    assert course_lifecycle.training_kind_for_course(
        _course(course_id="HF-REF", course_name="Human Factors Recurrent")
    ) == "OTHER"


def test_legacy_controlled_values_normalize_without_rewriting_source():
    course = _course(kind="REFRESHER", course_id="HF-REF")
    assert course_lifecycle.training_kind_for_course(course) == "RECURRENT"
    assert course.course_id == "HF-REF"


def test_explicit_group_links_initial_and_recurrent():
    initial = _course(id="init", course_id="HF-I", kind="INITIAL", group_code="HF")
    recurrent = _course(id="rec", course_id="HF-R", kind="RECURRENT", group_code="HF")
    assert course_lifecycle.explicit_recurrence_key(initial, [initial, recurrent]) == "group:hf"
    assert course_lifecycle.explicit_recurrence_key(recurrent, [initial, recurrent]) == "group:hf"


def test_declared_prerequisite_links_without_suffix_inference():
    initial = _course(id="init", course_id="A100", kind="INITIAL")
    recurrent = _course(id="rec", course_id="B900", kind="RECURRENT", prerequisite_course_id="A100")
    assert course_lifecycle.explicit_recurrence_key(initial, [initial, recurrent]) == "prerequisite:a100"
    assert course_lifecycle.explicit_recurrence_key(recurrent, [initial, recurrent]) == "prerequisite:a100"


def test_similarly_named_unrelated_courses_remain_separate():
    first = _course(id="a", course_id="EWIS-INIT", course_name="EWIS Initial")
    second = _course(id="b", course_id="EWIS-REF", course_name="EWIS Refresher")
    assert course_lifecycle.explicit_recurrence_key(first, [first, second]) == "course:a"
    assert course_lifecycle.explicit_recurrence_key(second, [first, second]) == "course:b"


def test_validation_flags_bad_recurrent_prerequisite():
    unrelated = _course(id="x", course_id="X", kind="ONE_OFF")
    recurrent = _course(id="r", course_id="R", kind="RECURRENT", prerequisite_course_id="X")
    problems = course_lifecycle.validate_lifecycle_relationships([unrelated, recurrent])
    assert len(problems) == 1
    assert "not explicitly classified as Initial" in problems[0].problem
