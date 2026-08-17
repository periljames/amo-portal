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

print("PR #506 workflow completion compatibility patch applied.")
