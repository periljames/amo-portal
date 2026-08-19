from types import SimpleNamespace

from amodb.apps.quality.audit_session_router import SESSION_STAGE_ORDER, project_audit_session


def _workflow(**states):
    stages = [
        SimpleNamespace(id=stage_id, complete=complete, helper=f"{stage_id} helper")
        for stage_id, complete in states.items()
    ]
    return SimpleNamespace(
        audit_id="11111111-1111-4111-8111-111111111111",
        stages=stages,
        current_stage_id=next((stage.id for stage in stages if not stage.complete), stages[-1].id),
        percent_complete=50,
    )


def test_session_projection_requires_issued_preparation_before_live():
    workflow = _workflow(
        **{
            "war-room": True,
            "checklist": True,
            "findings": False,
            "report": False,
            "cars": False,
            "evidence": False,
            "closeout": False,
        }
    )

    session = project_audit_session(
        workflow,
        preparation_issued=False,
        execution_status="OPEN",
        follow_up_status="OPEN",
        archive_count=0,
    )

    assert tuple(stage["id"] for stage in session["stages"]) == SESSION_STAGE_ORDER
    assert session["current_stage_id"] == "prepare"
    assert session["stages"][0]["complete"] is True
    assert session["stages"][1]["complete"] is False


def test_session_projection_keeps_execution_and_follow_up_separate():
    workflow = _workflow(
        **{
            "war-room": True,
            "checklist": True,
            "findings": True,
            "report": True,
            "cars": False,
            "evidence": True,
            "closeout": False,
        }
    )

    session = project_audit_session(
        workflow,
        preparation_issued=True,
        execution_status="CLOSED",
        follow_up_status="OPEN",
        archive_count=0,
    )

    assert session["current_stage_id"] == "follow-up"
    assert next(stage for stage in session["stages"] if stage["id"] == "closing")["complete"] is True
    assert next(stage for stage in session["stages"] if stage["id"] == "follow-up")["complete"] is False


def test_archive_is_independent_final_gate():
    workflow = _workflow(
        **{
            "war-room": True,
            "checklist": True,
            "findings": True,
            "report": True,
            "cars": True,
            "evidence": True,
            "closeout": True,
        }
    )

    session = project_audit_session(
        workflow,
        preparation_issued=True,
        execution_status="CLOSED",
        follow_up_status="COMPLETE",
        archive_count=0,
    )
    assert session["current_stage_id"] == "archive"
    assert session["percent_complete"] == 83

    archived = project_audit_session(
        workflow,
        preparation_issued=True,
        execution_status="CLOSED",
        follow_up_status="COMPLETE",
        archive_count=1,
    )
    assert archived["current_stage_id"] == "archive"
    assert archived["percent_complete"] == 100
    assert archived["stages"][-1]["complete"] is True
