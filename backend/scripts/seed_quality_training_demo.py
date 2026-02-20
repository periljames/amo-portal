from datetime import datetime, timedelta, date

from amodb.database import WriteSessionLocal
from amodb.apps.accounts import models as account_models
from amodb.apps.quality_training import models


def run():
    db = WriteSessionLocal()
    amo = db.query(account_models.AMO).first()
    if not amo:
        print("No AMO found")
        return
    tenant_id = amo.id
    users = db.query(account_models.User).filter(account_models.User.amo_id == tenant_id).limit(10).all()
    if not users:
        print("No staff found")
        return

    courses = [
        models.TrainingCourse(tenant_id=tenant_id, course_id="TRN-INIT-001", name="Human Factors Initial", category="HF", delivery_mode="Class", is_recurrent=False, active_flag=True, recurrence_interval_months=None, grace_window_days=30, owner_department="Quality", minimum_outcome_type="PassFail", evidence_requirements_json={"certificate_required": True, "attendance_required": True, "other_required_text": ""}),
        models.TrainingCourse(tenant_id=tenant_id, course_id="TRN-REC-001", name="SMS Recurrent", category="SMS", delivery_mode="Online", is_recurrent=True, active_flag=True, recurrence_interval_months=12, grace_window_days=30, owner_department="Quality", minimum_outcome_type="PassFail", evidence_requirements_json={"certificate_required": True, "attendance_required": True, "other_required_text": ""}),
        models.TrainingCourse(tenant_id=tenant_id, course_id="TRN-REC-002", name="EWIS Recurrent", category="EWIS", delivery_mode="OJT", is_recurrent=True, active_flag=True, recurrence_interval_months=24, grace_window_days=45, owner_department="Production", minimum_outcome_type="Score", minimum_score_optional=70, evidence_requirements_json={"certificate_required": False, "attendance_required": True, "other_required_text": ""}),
    ]
    for c in courses:
        if not db.query(models.TrainingCourse).filter_by(tenant_id=tenant_id, course_id=c.course_id).first():
            db.add(c)

    sessions = [
        models.TrainingSession(tenant_id=tenant_id, session_id="SES-001", course_id="TRN-REC-001", start_datetime=datetime.utcnow() + timedelta(days=3), end_datetime=datetime.utcnow() + timedelta(days=3, hours=2), location_text="HQ Classroom", instructor_user_id=users[0].id, status="Planned"),
        models.TrainingSession(tenant_id=tenant_id, session_id="SES-002", course_id="TRN-REC-002", start_datetime=datetime.utcnow() - timedelta(days=10), end_datetime=datetime.utcnow() - timedelta(days=10, hours=-2), location_text="Hangar B", instructor_user_id=users[1].id if len(users) > 1 else users[0].id, status="Completed"),
    ]
    for s in sessions:
        if not db.query(models.TrainingSession).filter_by(tenant_id=tenant_id, session_id=s.session_id).first():
            db.add(s)

    db.flush()
    for idx, user in enumerate(users[:10]):
        due = date.today() + timedelta(days=30 - idx * 8)
        if not db.query(models.CompletionRecord).filter_by(tenant_id=tenant_id, completion_id=f"COMP-{idx}").first():
            db.add(models.CompletionRecord(tenant_id=tenant_id, completion_id=f"COMP-{idx}", staff_id=user.id, course_id="TRN-REC-001", completion_date=date.today() - timedelta(days=300), outcome="Completed", next_due_date=due, evidence_asset_ids=None if idx % 3 == 0 else {"certificate": f"CERT-{idx}.pdf", "attendance_sheet": f"ATT-{idx}.pdf"}))
        if idx < 2 and not db.query(models.TrainingAuthorisation).filter_by(tenant_id=tenant_id, auth_id=f"AUTH-{idx}").first():
            db.add(models.TrainingAuthorisation(tenant_id=tenant_id, auth_id=f"AUTH-{idx}", staff_id=user.id, auth_type="Certifying Staff", granted_at=datetime.utcnow() - timedelta(days=200), expires_at=datetime.utcnow() + timedelta(days=45 + idx), granted_by_user_id=users[0].id, status="Current"))

    db.commit()
    print("Seeded quality training demo data")


if __name__ == "__main__":
    run()
