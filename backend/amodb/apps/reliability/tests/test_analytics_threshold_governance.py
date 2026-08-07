from amodb.apps.reliability.analytics_threshold_hardening import governed_metric_status


def test_rate_metrics_are_not_classified_against_unapproved_generic_limits():
    assert governed_metric_status("dispatch_reliability_pct", 96.5) == "NEUTRAL"
    assert governed_metric_status("nff_rate_pct", 28.0) == "NEUTRAL"
    assert governed_metric_status("effectiveness_pass_pct", 75.0) == "NEUTRAL"
    assert governed_metric_status("action_completion_pct", 80.0) == "NEUTRAL"


def test_explicit_zero_tolerance_operational_counts_remain_actionable():
    assert governed_metric_status("overdue_deferrals", 0) == "GOOD"
    assert governed_metric_status("overdue_deferrals", 1) == "ALERT"
    assert governed_metric_status("overdue_actions", 3) == "ALERT"
    assert governed_metric_status("data_quality_open", 0) == "GOOD"


def test_missing_metrics_remain_no_data():
    assert governed_metric_status("dispatch_reliability_pct", None) == "NO_DATA"
