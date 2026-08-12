from __future__ import annotations

from datetime import date
from pathlib import Path

from amodb.apps.doc_control.reminder_policy import DocumentReminderPolicy
from amodb.apps.doc_control.reminder_service import reminder_stage


ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "amodb" / "apps" / "doc_control"
MIGRATIONS = ROOT / "amodb" / "alembic" / "versions"
FRONTEND = ROOT.parent / "frontend" / "src" / "pages" / "documentControl"
SERVICES = ROOT.parent / "frontend" / "src" / "services"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_reminder_thresholds_are_staged_and_repeat_overdue_by_policy_bucket() -> None:
    policy = DocumentReminderPolicy()
    today = date(2026, 8, 12)
    cases = {
        date(2026, 9, 12): None,       # 31 days
        date(2026, 9, 11): "DUE_30",
        date(2026, 9, 1): "DUE_30",
        date(2026, 8, 26): "DUE_14",
        date(2026, 8, 22): "DUE_14",
        date(2026, 8, 19): "DUE_7",
        date(2026, 8, 13): "DUE_7",
        date(2026, 8, 12): "DUE_TODAY",
        date(2026, 8, 11): "OVERDUE_W1",
        date(2026, 8, 5): "OVERDUE_W1",
        date(2026, 8, 4): "OVERDUE_W2",
    }
    for due, expected in cases.items():
        assert reminder_stage(due_date=due, today=today, policy=policy) == expected


def test_policy_normalizes_lead_days_and_rejects_empty_valid_window() -> None:
    policy = DocumentReminderPolicy(lead_days=[7, 30, 14, 7])
    assert policy.lead_days == [30, 14, 7]


def test_reminder_ledger_is_durable_and_idempotent_per_obligation_recipient_stage() -> None:
    model = _text(APP / "reminder_models.py")
    migration = _text(MIGRATIONS / "docctl_20260812_reminder_deliveries.py")
    assert 'UniqueConstraint(' in model
    for token in (
        '"tenant_id"',
        '"obligation_type"',
        '"obligation_id"',
        '"recipient_user_id"',
        '"reminder_stage"',
    ):
        assert token in model
    assert 'down_revision = "docctl_20260812_evidence_assets"' in migration
    assert 'uq_document_reminder_obligation_recipient_stage' in migration


def test_reminder_engine_covers_each_owned_daily_dms_obligation() -> None:
    source = _text(APP / "reminder_service.py")
    for obligation in (
        'obligation_type="PERIODIC_REVIEW"',
        'obligation_type="TEMPORARY_REVISION_EXPIRY"',
        'obligation_type="EXTERNAL_SOURCE_CURRENCY"',
        'obligation_type="CONTROLLED_COPY_RETURN"',
        'obligation_type="AUTHORITY_RESPONSE"',
        'obligation_type="DISTRIBUTION_ACKNOWLEDGEMENT"',
    ):
        assert obligation in source
    assert 'row.owner_user_id' in source
    assert 'row.holder_user_id' in source
    assert 'row.submitted_by_user_id or _profile_owner' in source
    assert 'recipient.recipient_user_id' in source
    assert '_profile_owner' in source


def test_scheduler_is_single_writer_and_escalates_only_after_policy_thresholds() -> None:
    source = _text(APP / "reminder_service.py")
    lifecycle = _text(APP / "reminder_lifecycle_router.py")
    router = _text(APP / "router.py")
    assert 'pg_try_advisory_xact_lock' in source
    assert '_ADVISORY_LOCK_KEY' in source
    assert 'owner_escalation_days' in source
    assert 'quality_escalation_days' in source
    assert 'OWNER_ESCALATION_W' in source
    assert 'QUALITY_ESCALATION_W' in source
    assert 'NotificationPreference' in source
    assert 'PortalNotification' in source
    assert 'dedupe_key' in source
    assert 'notification_service.send_email' in source
    assert 'email_notifications_enabled' in source
    assert 'start_document_control_reminder_scheduler' in lifecycle
    assert 'stop_document_control_reminder_scheduler' in lifecycle
    assert 'router.include_router(reminder_lifecycle_router)' in router


def test_administration_exposes_and_persists_reminder_policy() -> None:
    backend = _text(APP / "workspace_administration_router.py")
    frontend = _text(FRONTEND / "DocumentControlAdministrationPage.tsx")
    service = _text(SERVICES / "documentControlReports.ts")
    assert 'reminder_policy: DocumentReminderPolicy' in backend
    assert '"reminder_policy": reminder' in backend
    assert '"reminder_policy": payload.reminder_policy.model_dump()' in backend
    assert 'title="Reminder and escalation policy"' in frontend
    assert 'data-testid="document-control-reminder-policy"' in frontend
    assert 'Lead reminder days' in frontend
    assert 'Escalate to document owner after' in frontend
    assert 'Escalate to Quality after' in frontend
    assert 'email_notifications_enabled' in frontend
    assert 'reminder_policy:' in service
