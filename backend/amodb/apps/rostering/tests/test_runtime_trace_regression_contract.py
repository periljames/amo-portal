from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_roster_notification_resilience_contract_covers_email_log_width_and_session_boundary():
    policy = (ROOT / "notification_resilience_policy.py").read_text(encoding="utf-8")

    # Runtime trace 2026-08-23: roster compliance correlation ids exceeded
    # email_logs.correlation_id VARCHAR(64), and the failed shared-session flush
    # left the authoritative roster transaction in PendingRollbackError.
    assert "_MAX_IDENTIFIER_LENGTH = 64" in policy
    assert "hashlib.sha256" in policy
    assert "db=None" in policy
    assert "authoritative roster" in policy
