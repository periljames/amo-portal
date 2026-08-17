from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"Expected patch anchor not found in {path}: {old[:140]!r}")
    file_path.write_text(text.replace(old, new, 1), encoding="utf-8")


# FastAPI must resolve the installer-local Pydantic request models eagerly.
replace_once(
    "backend/amodb/apps/training/workflow_completion.py",
    "from __future__ import annotations\n\n",
    "# Request models in this module are scoped with their route installers.\n# Keep annotations eager so FastAPI resolves those local request types correctly.\n\n",
)

# External-learning approval return and completion return are distinct. A request
# returned before approval must be corrected/resubmitted before it can progress.
replace_once(
    "backend/amodb/apps/training/workflow_completion.py",
    '    class ExternalLearningTransition(BaseModel):\n        action: Literal["APPROVE", "RETURN", "REJECT", "SUBMIT_COMPLETION", "VERIFY_COMPLETION"]\n        comment: str = Field(..., min_length=2, max_length=4000)\n        completion_date: date | None = None\n        certificate_reference: str | None = Field(None, max_length=255)\n        evidence_file_ids: list[str] = Field(default_factory=list)\n        exam_score: int | None = Field(None, ge=0, le=100)\n        hours_completed: int | None = Field(None, ge=0)',
    '    class ExternalLearningTransition(BaseModel):\n        action: Literal["APPROVE", "RETURN", "REJECT", "RESUBMIT_REQUEST", "SUBMIT_COMPLETION", "VERIFY_COMPLETION"]\n        comment: str = Field(..., min_length=2, max_length=4000)\n        provider_name: str | None = Field(None, min_length=2, max_length=255)\n        planned_start: date | None = None\n        planned_end: date | None = None\n        reason: str | None = Field(None, min_length=2, max_length=4000)\n        completion_date: date | None = None\n        certificate_reference: str | None = Field(None, max_length=255)\n        evidence_file_ids: list[str] = Field(default_factory=list)\n        exam_score: int | None = Field(None, ge=0, le=100)\n        hours_completed: int | None = Field(None, ge=0)',
)
replace_once(
    "backend/amodb/apps/training/workflow_completion.py",
    '        elif payload.action == "SUBMIT_COMPLETION":\n            if str(current_user.id) != learner_id and not router_module._is_training_editor(current_user):\n                raise HTTPException(status_code=403, detail="Only the learner may submit external-learning completion evidence.")\n\n        if payload.action == "APPROVE":',
    '        elif payload.action in {"SUBMIT_COMPLETION", "RESUBMIT_REQUEST"}:\n            if str(current_user.id) not in {learner_id, str(data.get("requester_user_id") or "")} and not router_module._is_training_editor(current_user):\n                raise HTTPException(status_code=403, detail="Only the learner/requester may update this external-learning request.")\n\n        if payload.action == "RESUBMIT_REQUEST":\n            if prior != "RETURNED" or data.get("return_stage") == "COMPLETION":\n                raise HTTPException(status_code=409, detail="Only a request returned before approval may be corrected and resubmitted.")\n            next_start = payload.planned_start or (date.fromisoformat(str(data["planned_start"])) if data.get("planned_start") else None)\n            next_end = payload.planned_end or (date.fromisoformat(str(data["planned_end"])) if data.get("planned_end") else None)\n            if next_start and next_end and next_end < next_start:\n                raise HTTPException(status_code=422, detail="External learning end date cannot precede the start date.")\n            if payload.provider_name:\n                data["provider_name"] = payload.provider_name\n            if payload.planned_start:\n                data["planned_start"] = payload.planned_start.isoformat()\n            if payload.planned_end is not None:\n                data["planned_end"] = payload.planned_end.isoformat()\n            if payload.reason:\n                data["reason"] = payload.reason\n            data["request_resubmitted_at"] = _now().isoformat()\n            data.pop("return_stage", None)\n            workflow.status = "SUBMITTED"\n            workflow.submitted_at = _now()\n        elif payload.action == "APPROVE":',
)
replace_once(
    "backend/amodb/apps/training/workflow_completion.py",
    '            data["return_comment"] = payload.comment\n            data["returned_at"] = _now().isoformat()',
    '            data["return_comment"] = payload.comment\n            data["returned_at"] = _now().isoformat()\n            data["return_stage"] = "COMPLETION" if prior == "COMPLETION_SUBMITTED" else "REQUEST"',
)
replace_once(
    "backend/amodb/apps/training/workflow_completion.py",
    '        elif payload.action == "SUBMIT_COMPLETION":\n            if prior not in {"APPROVED", "RETURNED"}:\n                raise HTTPException(status_code=409, detail=f"Cannot submit completion from {prior}.")',
    '        elif payload.action == "SUBMIT_COMPLETION":\n            if prior != "APPROVED" and not (prior == "RETURNED" and data.get("return_stage") == "COMPLETION"):\n                raise HTTPException(status_code=409, detail=f"Cannot submit completion from {prior}.")\n            data.pop("return_stage", None)',
)

# Mount the learner action centre on the existing My Training page.
replace_once(
    "frontend/src/pages/MyTrainingPage.tsx",
    'import MyTrainingTaskInbox from "../components/training/MyTrainingTaskInbox";\n',
    'import MyTrainingTaskInbox from "../components/training/MyTrainingTaskInbox";\nimport TrainingLearnerActionCentre from "../components/training/TrainingLearnerActionCentre";\n',
)
replace_once(
    "frontend/src/pages/MyTrainingPage.tsx",
    '            <MyTrainingTaskInbox />\n\n            {/* Summary row */}',
    '            <MyTrainingTaskInbox />\n            <TrainingLearnerActionCentre />\n\n            {/* Summary row */}',
)

# Run deferral/evidence expiry and SLA escalation from the production scheduler.
replace_once(
    "backend/amodb/jobs/training_notification_automation.py",
    '            except Exception:\n                db.rollback()\n                summary["failed_tenants"] += 1\n                logger.exception("Training notification automation failed for tenant %s", settings.amo_id)\n        return summary',
    '            except Exception:\n                db.rollback()\n                summary["failed_tenants"] += 1\n                logger.exception("Training notification automation failed for tenant %s", settings.amo_id)\n\n        try:\n            from amodb.apps.training.workflow_completion import run_workflow_escalations\n\n            workflow_summary = run_workflow_escalations(db, now=clock)\n            db.commit()\n            for key, value in workflow_summary.items():\n                summary[f"workflow_{key}"] = int(value)\n        except Exception:\n            db.rollback()\n            summary["errors"] += 1\n            logger.exception("Training workflow escalation pass failed")\n\n        return summary',
)

print("PR #506 final workflow integration patch applied.")
