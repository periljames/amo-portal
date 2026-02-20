from __future__ import annotations

from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.entitlements import require_module
from amodb.security import get_current_active_user

from . import models, schemas

router = APIRouter(prefix="/quality/training", tags=["quality-training"], dependencies=[Depends(require_module("quality"))])


def _tenant(user: account_models.User) -> str:
    return str(user.amo_id)


def _audit(db: Session, tenant_id: str, object_type: str, object_id: str, action: str, actor: str | None, before: dict | None, after: dict | None) -> None:
    db.add(models.TrainingAuditEvent(tenant_id=tenant_id, object_type=object_type, object_id=object_id, action=action, actor_user_id=actor, diff_json={"before": before or {}, "after": after or {}}))


def _compute_due(completion_date: date, months: int | None) -> date | None:
    if not months:
        return None
    return completion_date + timedelta(days=months * 30)


@router.get("", summary="Training dashboard")
def dashboard(db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    tenant_id = _tenant(user)
    today = date.today()
    soon_30 = today + timedelta(days=30)
    soon_60 = datetime.utcnow() + timedelta(days=60)
    soon_14 = datetime.utcnow() + timedelta(days=14)
    due_30 = db.query(models.CompletionRecord).filter(models.CompletionRecord.tenant_id == tenant_id, models.CompletionRecord.next_due_date != None, models.CompletionRecord.next_due_date >= today, models.CompletionRecord.next_due_date <= soon_30).count()
    overdue = db.query(models.CompletionRecord).filter(models.CompletionRecord.tenant_id == tenant_id, models.CompletionRecord.next_due_date != None, models.CompletionRecord.next_due_date < today).count()
    auth_expiring = db.query(models.TrainingAuthorisation).filter(models.TrainingAuthorisation.tenant_id == tenant_id, models.TrainingAuthorisation.expires_at != None, models.TrainingAuthorisation.expires_at <= soon_60, models.TrainingAuthorisation.expires_at >= datetime.utcnow()).count()
    sessions_14 = db.query(models.TrainingSession).filter(models.TrainingSession.tenant_id == tenant_id, models.TrainingSession.start_datetime <= soon_14, models.TrainingSession.start_datetime >= datetime.utcnow()).count()
    completions_30 = db.query(models.CompletionRecord).filter(models.CompletionRecord.tenant_id == tenant_id, models.CompletionRecord.completion_date >= today - timedelta(days=30)).count()
    missing_evidence = db.query(models.CompletionRecord).filter(models.CompletionRecord.tenant_id == tenant_id, models.CompletionRecord.evidence_asset_ids == None).count()
    return {"training_due_30_days": due_30, "training_overdue": overdue, "authorisations_expiring_60_days": auth_expiring, "sessions_next_14_days": sessions_14, "completions_last_30_days": completions_30, "evidence_missing": missing_evidence}


@router.get("/catalog", response_model=list[schemas.CourseRead])
def list_courses(db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    return db.query(models.TrainingCourse).filter(models.TrainingCourse.tenant_id == _tenant(user)).all()


@router.post("/catalog", response_model=schemas.CourseRead)
def create_course(payload: schemas.CourseCreate, db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    tenant_id = _tenant(user)
    entity = models.TrainingCourse(tenant_id=tenant_id, **payload.model_dump())
    db.add(entity)
    db.flush()
    _audit(db, tenant_id, "Course", entity.course_id, "create", user.id, None, payload.model_dump())
    db.commit()
    db.refresh(entity)
    return entity


@router.get("/catalog/{course_id}", response_model=schemas.CourseRead)
def get_course(course_id: str, db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    row = db.query(models.TrainingCourse).filter(models.TrainingCourse.tenant_id == _tenant(user), models.TrainingCourse.course_id == course_id).first()
    if not row:
        raise HTTPException(404, "Course not found")
    return row


@router.get("/sessions", response_model=list[schemas.SessionRead])
def list_sessions(db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    return db.query(models.TrainingSession).filter(models.TrainingSession.tenant_id == _tenant(user)).all()


@router.post("/sessions", response_model=schemas.SessionRead)
def create_session(payload: schemas.SessionCreate, db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    entity = models.TrainingSession(tenant_id=_tenant(user), **payload.model_dump())
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity


@router.get("/sessions/{session_id}")
def get_session(session_id: str, db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    tenant_id = _tenant(user)
    session = db.query(models.TrainingSession).filter(models.TrainingSession.tenant_id == tenant_id, models.TrainingSession.session_id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    attendees = db.query(models.SessionAttendee).filter(models.SessionAttendee.tenant_id == tenant_id, models.SessionAttendee.session_id == session_id).all()
    return {"session": schemas.SessionRead.model_validate(session), "attendees": [schemas.AttendeeRead.model_validate(a) for a in attendees]}


@router.post("/sessions/{session_id}/attendees", response_model=schemas.AttendeeRead)
def upsert_attendee(session_id: str, payload: schemas.AttendeeUpsert, db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    tenant_id = _tenant(user)
    attendee = db.query(models.SessionAttendee).filter(models.SessionAttendee.tenant_id == tenant_id, models.SessionAttendee.session_id == session_id, models.SessionAttendee.staff_id == payload.staff_id).first()
    if attendee:
        for k, v in payload.model_dump().items():
            setattr(attendee, k, v)
        attendee.attendance_marked_at = datetime.utcnow()
    else:
        attendee = models.SessionAttendee(tenant_id=tenant_id, session_id=session_id, attendance_marked_at=datetime.utcnow(), **payload.model_dump())
        db.add(attendee)
    db.commit()
    db.refresh(attendee)
    return attendee


@router.post("/sessions/{session_id}/complete")
def complete_session(session_id: str, db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    tenant_id = _tenant(user)
    session = db.query(models.TrainingSession).filter(models.TrainingSession.tenant_id == tenant_id, models.TrainingSession.session_id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    attendees = db.query(models.SessionAttendee).filter(models.SessionAttendee.tenant_id == tenant_id, models.SessionAttendee.session_id == session_id).all()
    course = db.query(models.TrainingCourse).filter(models.TrainingCourse.tenant_id == tenant_id, models.TrainingCourse.course_id == session.course_id).first()
    for attendee in attendees:
        completion_date = session.end_datetime.date()
        due = _compute_due(completion_date, course.recurrence_interval_months if course and course.is_recurrent else None)
        record = models.CompletionRecord(tenant_id=tenant_id, completion_id=f"COMP-{session_id}-{attendee.staff_id}", staff_id=attendee.staff_id, course_id=session.course_id, completion_date=completion_date, outcome=attendee.result_outcome or "Deferred", score_optional=attendee.score_optional, source_session_id=session_id, next_due_date=due, evidence_asset_ids=attendee.evidence_asset_ids)
        db.add(record)
    session.status = "Completed"
    db.commit()
    return {"status": "ok", "records_written": len(attendees)}


@router.get("/staff")
def staff_list(db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    tenant_id = _tenant(user)
    staff = db.query(account_models.User).filter(account_models.User.amo_id == tenant_id).all()
    today = date.today()
    out = []
    for s in staff:
        records = db.query(models.CompletionRecord).filter(models.CompletionRecord.tenant_id == tenant_id, models.CompletionRecord.staff_id == s.id).all()
        due_dates = [r.next_due_date for r in records if r.next_due_date]
        next_due = min(due_dates) if due_dates else None
        overdue_count = len([d for d in due_dates if d < today])
        status = "Current" if not overdue_count else "Expired"
        out.append({"staff_id": s.id, "name": s.full_name, "department": getattr(s.department, 'name', None), "role": str(s.role), "authorisation_status": status if s.is_active else "Not Current", "next_due_date": next_due, "overdue_count": overdue_count})
    return out


@router.get("/staff/{staff_id}")
def staff_profile(staff_id: str, db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    tenant_id = _tenant(user)
    s = db.query(account_models.User).filter(account_models.User.amo_id == tenant_id, account_models.User.id == staff_id).first()
    if not s:
        raise HTTPException(404, "Staff not found")
    completions = db.query(models.CompletionRecord).filter(models.CompletionRecord.tenant_id == tenant_id, models.CompletionRecord.staff_id == staff_id).all()
    auths = db.query(models.TrainingAuthorisation).filter(models.TrainingAuthorisation.tenant_id == tenant_id, models.TrainingAuthorisation.staff_id == staff_id).all()
    return {"profile": {"name": s.full_name, "department": getattr(s.department, 'name', None), "role": str(s.role), "license_identifier": s.licence_number, "employment_status": "Active" if s.is_active else "Inactive"}, "completed": [schemas.CompletionRead.model_validate(c) for c in completions], "authorisations": auths}


@router.get("/matrix")
def matrix_list(db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    tenant_id = _tenant(user)
    return db.query(models.RoleTrainingRequirement).filter(models.RoleTrainingRequirement.tenant_id == tenant_id).all()


@router.get("/reports/overdue.csv", response_class=PlainTextResponse)
def report_overdue(db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    tenant_id = _tenant(user)
    rows = db.query(models.CompletionRecord).filter(models.CompletionRecord.tenant_id == tenant_id, models.CompletionRecord.next_due_date < date.today()).all()
    lines = ["staff_id,course_id,next_due_date,outcome"]
    lines.extend([f"{r.staff_id},{r.course_id},{r.next_due_date},{r.outcome}" for r in rows])
    return "\n".join(lines)


@router.get("/settings", response_model=schemas.SettingsRead)
def get_settings(db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    tenant_id = _tenant(user)
    s = db.query(models.TrainingTenantSettings).filter(models.TrainingTenantSettings.tenant_id == tenant_id).first()
    if not s:
        s = models.TrainingTenantSettings(tenant_id=tenant_id)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


@router.put("/settings", response_model=schemas.SettingsRead)
def put_settings(payload: schemas.SettingsUpdate, db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    tenant_id = _tenant(user)
    s = db.query(models.TrainingTenantSettings).filter(models.TrainingTenantSettings.tenant_id == tenant_id).first()
    if not s:
        s = models.TrainingTenantSettings(tenant_id=tenant_id)
        db.add(s)
    before = {
        "default_recurrence_interval_months": s.default_recurrence_interval_months,
        "default_grace_window_days": s.default_grace_window_days,
        "certificate_mandatory_default": s.certificate_mandatory_default,
        "attendance_sheet_mandatory_default": s.attendance_sheet_mandatory_default,
    }
    for k, v in payload.model_dump().items():
        setattr(s, k, v)
    _audit(db, tenant_id, "Settings", tenant_id, "update", user.id, before, payload.model_dump())
    db.commit()
    db.refresh(s)
    return s


@router.get("/currency/{staff_id}")
def currency_summary(staff_id: str, db: Session = Depends(get_db), user: account_models.User = Depends(get_current_active_user)):
    tenant_id = _tenant(user)
    overdue = db.query(models.CompletionRecord).filter(models.CompletionRecord.tenant_id == tenant_id, models.CompletionRecord.staff_id == staff_id, models.CompletionRecord.next_due_date < date.today()).count()
    if overdue > 0:
        status = "Expired"
    else:
        status = "Current"
    return {"staff_id": staff_id, "status": status}
