"""MOPM 3.13 review currency shared by display and supplier-use gates."""
from datetime import date, datetime, timedelta, timezone


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            pass
    return None


def review_assessment(*, approved_at=None, last_reviewed_on=None, review_interval_days=None,
                      next_review_due_on=None, today=None):
    today = today or datetime.now(timezone.utc).date()
    reviewed = _date(last_reviewed_on) or _date(approved_at)
    if reviewed is None or reviewed > today:
        return {"current":False,"code":"PROVIDER_REVIEW_DATE_UNCONFIRMED","due_on":None}
    interval = min(int(review_interval_days or 365),365)
    due = reviewed + timedelta(days=interval)
    recorded = _date(next_review_due_on)
    if recorded:
        due = min(due,recorded)
    return {"current":due > today,"code":"PROVIDER_REVIEW_OVERDUE" if due <= today else None,"due_on":due}


def apply_review_status(provider, *, today=None):
    assessment = review_assessment(approved_at=provider.get("approved_at"),
        last_reviewed_on=provider.get("last_reviewed_on"), review_interval_days=provider.get("review_interval_days"),
        next_review_due_on=provider.get("next_review_due_on"), today=today)
    provider["recorded_next_review_due_on"] = provider.get("next_review_due_on")
    provider["next_review_due_on"] = assessment["due_on"]
    # Prospective providers need initial qualification, rather than an overdue review.
    needs_review = provider.get("status") not in {"PROSPECTIVE", "UNDER_REVIEW", "REJECTED", "ARCHIVED"}
    provider["review_due"] = needs_review and not assessment["current"]
    provider["review_currency_code"] = assessment["code"]
    return provider
