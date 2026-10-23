"""Versioned controlled-change workflow; historical decisions remain untouched."""
from datetime import date, timedelta

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text


class ChangeAuthorityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    approval_required: bool = True
    notification_required: bool = True
    physical_address_change: bool = False
    justification: str = Field(default="Authority approval and written notification required.", min_length=10, max_length=2000)

    @model_validator(mode="after")
    def notification_for_approval(self):
        if (self.approval_required or self.physical_address_change) and not self.notification_required:
            raise ValueError("Approval and physical address changes require written notification.")
        return self


def governed(mission):
    return (getattr(mission, "scope", None) or {}).get("change_workflow_version") == 2


def assert_current_version(mission, expected):
    if expected is not None and expected.isoformat().replace("+00:00", "Z") != mission.updated_at.isoformat().replace("+00:00", "Z"):
        raise HTTPException(409, "This change was updated by another action. Refresh before saving.")


def policy(mission):
    return ChangeAuthorityPolicy.model_validate((mission.scope or {}).get("authority_policy", {}))


def event(mission, action):
    return next((d for d in reversed(list(mission.decisions or []))
                 if (d.evidence_snapshot or {}).get("workflow_action") == action and d.status == "APPROVED"), None)


def next_action(mission):
    if mission.status in {"COMPLETE", "CANCELLED"}:
        return None
    if governed(mission) and event(mission, "IMPLEMENTATION"):
        return "EFFECTIVENESS_REVIEW"
    stages = {"GATE_REVIEW": "QUALITY_SELF_EVALUATION", "READY_FOR_APPROVAL": "ACCOUNTABLE_EXECUTIVE",
              "APPROVED": "AUTHORITY_SUBMISSION", "SUBMITTED_TO_AUTHORITY": "AUTHORITY_ACCEPTANCE"}
    if not governed(mission):
        return stages.get(mission.status)
    requirements = policy(mission)
    if mission.status == "APPROVED" and not requirements.notification_required:
        return "IMPLEMENTATION"
    if mission.status == "SUBMITTED_TO_AUTHORITY":
        if not requirements.approval_required or event(mission, "AUTHORITY_ACCEPTANCE"):
            return "IMPLEMENTATION"
    return stages.get(mission.status)


def retained_evidence(db, *, amo_id, asset_id=None, search="", authority_only=False):
    return db.execute(text("""SELECT a.id AS asset_id,a.filename,a.sha256,a.size_bytes,a.category
        FROM document_evidence_assets a WHERE a.tenant_id=:amo
          AND (:authority_only = false OR a.category='AUTHORITY')
          AND (CAST(:asset AS TEXT) IS NULL OR a.id=:asset)
          AND LOWER(a.filename) LIKE :search
          AND NOT EXISTS (SELECT 1 FROM document_retention_dispositions d
            WHERE d.tenant_id=a.tenant_id AND d.source_type='EVIDENCE_ASSET'
              AND d.source_id=a.id AND d.status='DISPOSED')
        ORDER BY a.created_at DESC LIMIT 50"""),
        {"amo": amo_id, "asset": asset_id, "search": f"%{search.lower()}%", "authority_only": authority_only}).mappings().all()


def evidence_or_422(db, *, amo_id, asset_id, authority_only=False):
    rows = retained_evidence(db, amo_id=amo_id, asset_id=asset_id, authority_only=authority_only) if asset_id else []
    if not rows or len(rows[0]["sha256"] or "") != 64 or (rows[0]["size_bytes"] or 0) <= 0:
        raise HTTPException(422, "Select available retained evidence belonging to this AMO.")
    return dict(rows[0])


def assert_current_readiness(db, mission, expected_template):
    """Human verification is attributable; source existence/checksum is rechecked."""
    if not governed(mission):
        return
    gates = {g.gate_code: g for g in mission.gates if g.gate_type == "HARD"}
    if not {g["gate_code"] for g in expected_template}.issubset(gates):
        raise HTTPException(409, "Required MOPM readiness gates are missing.")
    for gate in gates.values():
        if gate.status != "PASS" or gate.evidence_status != "VERIFIED" or gate.source_type != "DOCUMENT_EVIDENCE" or not gate.passed_by_user_id:
            raise HTTPException(409, "Every hard gate needs retained evidence and an attributable review.")
        current = evidence_or_422(db, amo_id=mission.amo_id, asset_id=gate.source_id)
        snapshot = gate.source_snapshot or {}
        if snapshot.get("sha256") != current["sha256"] or len(snapshot.get("review_note", "").strip()) < 10:
            raise HTTPException(409, "Readiness evidence changed or its review is incomplete. Reassess the gate.")


def assert_delivery_evidence_current(db, mission):
    for action, key in (("AUTHORITY_SUBMISSION", "authority_evidence"), ("AUTHORITY_ACCEPTANCE", "authority_evidence"), ("IMPLEMENTATION", "evidence")):
        prior = event(mission, action)
        if prior:
            snapshot = (prior.evidence_snapshot or {}).get(key) or {}
            current = evidence_or_422(db, amo_id=mission.amo_id, asset_id=snapshot.get("asset_id"), authority_only=key == "authority_evidence")
            if current["sha256"] != snapshot.get("sha256"):
                raise HTTPException(409, "Required approval or implementation evidence has changed.")


def assert_implementation_date(mission, effective_date):
    if effective_date > date.today():
        raise HTTPException(422, "Record implementation after it takes place; use the target date for planning.")
    requirements = policy(mission)
    prior_type = "AUTHORITY_ACCEPTANCE" if requirements.approval_required else "AUTHORITY_SUBMISSION" if requirements.notification_required else "ACCOUNTABLE_EXECUTIVE"
    prior = next((d for d in reversed(list(mission.decisions)) if d.decision_type == prior_type and d.status == "APPROVED"), None)
    if not prior or effective_date < prior.decided_at.date():
        raise HTTPException(409, "Implementation cannot predate the required approval or notification.")
    if requirements.physical_address_change:
        notification = next((d for d in reversed(list(mission.decisions)) if d.decision_type == "AUTHORITY_SUBMISSION" and d.status == "APPROVED"), None)
        notified_on = (notification.evidence_snapshot or {}).get("notified_on") if notification else None
        if not notified_on or effective_date < date.fromisoformat(notified_on) + timedelta(days=14):
            raise HTTPException(409, "Physical address changes require at least 14 days' written advance notification.")
