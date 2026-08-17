from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"Expected patch anchor not found in {path}: {old[:100]!r}")
    file_path.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "backend/amodb/apps/training/models.py",
    '    CONFIRMED = "CONFIRMED"\n    ATTENDED = "ATTENDED"',
    '    CONFIRMED = "CONFIRMED"\n    WAITLISTED = "WAITLISTED"\n    ATTENDED = "ATTENDED"',
)
replace_once(
    "backend/amodb/apps/training/models.py",
    'class DeferralStatus(str, enum.Enum):\n    PENDING = "PENDING"\n    APPROVED = "APPROVED"\n    REJECTED = "REJECTED"\n    CANCELLED = "CANCELLED"',
    'class DeferralStatus(str, enum.Enum):\n    PENDING = "PENDING"\n    RETURNED_FOR_INFORMATION = "RETURNED_FOR_INFORMATION"\n    APPROVED = "APPROVED"\n    REJECTED = "REJECTED"\n    EXPIRED = "EXPIRED"\n    CANCELLED = "CANCELLED"',
)
replace_once(
    "backend/amodb/apps/training/models.py",
    'class TrainingFileReviewStatus(str, enum.Enum):\n    PENDING = "PENDING"\n    APPROVED = "APPROVED"\n    REJECTED = "REJECTED"',
    'class TrainingFileReviewStatus(str, enum.Enum):\n    PENDING = "PENDING"\n    APPROVED = "APPROVED"\n    RETURNED = "RETURNED"\n    REJECTED = "REJECTED"',
)

replace_once(
    "backend/amodb/apps/training/schemas.py",
    'description="SCHEDULED / INVITED / CONFIRMED / ATTENDED / NO_SHOW / CANCELLED / DEFERRED.",',
    'description="SCHEDULED / INVITED / CONFIRMED / WAITLISTED / ATTENDED / NO_SHOW / CANCELLED / DEFERRED.",',
)
replace_once(
    "backend/amodb/apps/training/schemas.py",
    'review_status: TrainingFileReviewStatus = Field(..., description="PENDING / APPROVED / REJECTED.")',
    'review_status: TrainingFileReviewStatus = Field(..., description="PENDING / APPROVED / RETURNED / REJECTED.")',
)

replace_once(
    "backend/amodb/apps/training/router.py",
    '    auto_approved = bool(is_editor and owner.id != current_user.id or is_editor)',
    '    # Governance: upload permission is not review permission. Every evidence\n    # upload enters independent review, including files uploaded by Training editors.\n    auto_approved = False',
)
replace_once(
    "backend/amodb/apps/training/router.py",
    '    if not f:\n        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training file not found.")\n\n    f.review_status = payload.review_status',
    '    if not f:\n        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training file not found.")\n\n    if str(f.owner_user_id) == str(current_user.id) or str(f.uploaded_by_user_id or "") == str(current_user.id):\n        raise HTTPException(\n            status_code=status.HTTP_409_CONFLICT,\n            detail="Training evidence must be reviewed by someone other than the learner/uploader.",\n        )\n    if payload.review_status == training_models.TrainingFileReviewStatus.RETURNED and not (payload.review_comment or "").strip():\n        raise HTTPException(\n            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,\n            detail="Returned evidence requires a reviewer comment explaining what must be corrected.",\n        )\n\n    f.review_status = payload.review_status',
)
replace_once(
    "backend/amodb/apps/training/router.py",
    '        title = "Evidence approved" if payload.review_status == training_models.TrainingFileReviewStatus.APPROVED else "Evidence rejected"',
    '        if payload.review_status == training_models.TrainingFileReviewStatus.APPROVED:\n            title = "Evidence approved"\n        elif payload.review_status == training_models.TrainingFileReviewStatus.RETURNED:\n            title = "Evidence returned for correction"\n        else:\n            title = "Evidence rejected"',
)
replace_once(
    "backend/amodb/apps/training/router.py",
    '    if not deferral:\n        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deferral request not found.")\n\n    data = payload.model_dump(exclude_unset=True)\n    status_value = data.get("status")',
    '    if not deferral:\n        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deferral request not found.")\n\n    if str(current_user.id) in {str(deferral.user_id), str(deferral.requested_by_user_id or "")}:\n        raise HTTPException(\n            status_code=status.HTTP_409_CONFLICT,\n            detail="The learner/requester cannot decide their own deferral.",\n        )\n\n    data = payload.model_dump(exclude_unset=True)\n    status_value = data.get("status")\n    if status_value == training_models.DeferralStatus.RETURNED_FOR_INFORMATION and not (data.get("decision_comment") or "").strip():\n        raise HTTPException(\n            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,\n            detail="Returned deferrals require a reviewer comment explaining what information is needed.",\n        )',
)

replace_once(
    "frontend/src/types/training.ts",
    'export type TrainingParticipantStatus = "SCHEDULED" | "INVITED" | "CONFIRMED" | "ATTENDED" | "NO_SHOW" | "CANCELLED" | "DEFERRED";',
    'export type TrainingParticipantStatus = "SCHEDULED" | "INVITED" | "CONFIRMED" | "WAITLISTED" | "ATTENDED" | "NO_SHOW" | "CANCELLED" | "DEFERRED";',
)
replace_once(
    "frontend/src/types/training.ts",
    'export type DeferralStatus = "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED";',
    'export type DeferralStatus = "PENDING" | "RETURNED_FOR_INFORMATION" | "APPROVED" | "REJECTED" | "EXPIRED" | "CANCELLED";',
)
replace_once(
    "frontend/src/types/training.ts",
    'export type TrainingFileReviewStatus = "PENDING" | "APPROVED" | "REJECTED";',
    'export type TrainingFileReviewStatus = "PENDING" | "APPROVED" | "RETURNED" | "REJECTED";',
)
replace_once(
    "frontend/src/services/training.ts",
    '  status?: "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED";',
    '  status?: "PENDING" | "RETURNED_FOR_INFORMATION" | "APPROVED" | "REJECTED" | "EXPIRED" | "CANCELLED";',
)

# FastAPI evaluates route annotations from module globals. Request models for this
# completion layer are scoped to its installer, so keep those annotations eager.
replace_once(
    "backend/amodb/apps/training/workflow_completion.py",
    "from __future__ import annotations\n\n",
    "# Request models in this module are intentionally scoped with their route installers.\n# Keep annotations eager so FastAPI resolves those local request model types correctly.\n\n",
)

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

replace_once(
    "frontend/src/pages/MyTrainingPage.tsx",
    'import MyTrainingTaskInbox from "../components/training/MyTrainingTaskInbox";\nimport "../styles/myTrainingOperations.css";',
    'import MyTrainingTaskInbox from "../components/training/MyTrainingTaskInbox";\nimport TrainingLearnerActionCentre from "../components/training/TrainingLearnerActionCentre";\nimport "../styles/myTrainingOperations.css";',
)
replace_once(
    "frontend/src/pages/MyTrainingPage.tsx",
    '      <MyTrainingTaskInbox\n        criticalItems={criticalInboxItems}\n        eventInvitations={eventInvitations}\n        workflowTasks={tasks}\n        assessmentTasks={assessmentTasks}\n        loading={taskInboxLoading}\n        error={taskInboxError}\n        onRefresh={() => void refreshTaskInbox()}\n        onRsvp={(invitationId, response) => respondToSessionInvitation(invitationId, response)}\n      />\n\n      {errorMessage && (',
    '      <MyTrainingTaskInbox\n        criticalItems={criticalInboxItems}\n        eventInvitations={eventInvitations}\n        workflowTasks={tasks}\n        assessmentTasks={assessmentTasks}\n        loading={taskInboxLoading}\n        error={taskInboxError}\n        onRefresh={() => void refreshTaskInbox()}\n        onRsvp={(invitationId, response) => respondToSessionInvitation(invitationId, response)}\n      />\n\n      <TrainingLearnerActionCentre />\n\n      {errorMessage && (',
)

replace_once(
    "backend/amodb/jobs/training_notification_automation.py",
    '                    if inserted:\n                        summary["created"] += 1\n\n        return summary',
    '                    if inserted:\n                        summary["created"] += 1\n\n        try:\n            from amodb.apps.training.workflow_completion import run_workflow_escalations\n\n            workflow_summary = run_workflow_escalations(db, now=clock)\n            db.commit()\n            for key, value in workflow_summary.items():\n                summary[f"workflow_{key}"] = int(value)\n        except Exception:\n            db.rollback()\n            summary["errors"] += 1\n            logger.exception("training workflow escalation pass failed")\n\n        return summary',
)

print("PR #506 workflow completion compatibility patch applied.")
