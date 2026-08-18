from amodb.jobs.training_notification_automation import reminder_policy, selected_milestone


EXPLICIT_POLICY = {
    "compliance_reminders": {
        "enabled": True,
        "due_days": [90, 60, 30, 15, 7, 1],
        "overdue_days": [30, 14, 7, 1],
    }
}


def test_unconfigured_training_reminder_policy_is_disabled():
    policy = reminder_policy({})
    assert policy.configured is False
    assert policy.enabled is False
    assert policy.due_days == ()
    assert policy.overdue_days == ()


def test_tenant_can_override_and_disable_compliance_reminders():
    policy = reminder_policy({
        "compliance_reminders": {
            "enabled": False,
            "due_days": [45, 10, 3, 3, -1],
            "overdue_days": [2, 5],
        }
    })
    assert policy.configured is True
    assert policy.enabled is False
    assert policy.due_days == (45, 10, 3)
    assert policy.overdue_days == (5, 2)


def test_enabled_policy_requires_tenant_defined_milestones():
    policy = reminder_policy({"compliance_reminders": {"enabled": True}})
    assert policy.configured is True
    assert policy.enabled is False
    assert policy.error is not None


def test_due_milestone_uses_single_nearest_crossed_threshold():
    policy = reminder_policy(EXPLICIT_POLICY)
    assert selected_milestone(91, policy) is None
    assert selected_milestone(90, policy) == ("DUE", 90)
    assert selected_milestone(31, policy) == ("DUE", 60)
    assert selected_milestone(20, policy) == ("DUE", 30)
    assert selected_milestone(6, policy) == ("DUE", 7)
    assert selected_milestone(0, policy) == ("DUE", 1)


def test_overdue_milestone_uses_latest_crossed_threshold():
    policy = reminder_policy(EXPLICIT_POLICY)
    assert selected_milestone(-1, policy) == ("OVERDUE", 1)
    assert selected_milestone(-8, policy) == ("OVERDUE", 7)
    assert selected_milestone(-17, policy) == ("OVERDUE", 14)
    assert selected_milestone(-45, policy) == ("OVERDUE", 30)
