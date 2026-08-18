from __future__ import annotations

from datetime import date
from typing import Callable


def bridge_demand_items(base: Callable, *, settings_getter: Callable):
    def demand_items(db, *, amo_id: str, year: int):
        items = list(base(db, amo_id=amo_id, year=year))
        settings = settings_getter(db, amo_id=amo_id)
        lead_days = int(settings.default_planning_lead_days)
        today = date.today()
        evaluation_date = today if year == today.year else date(year, 1, 1) if year > today.year else date(year, 12, 31)
        result = []
        for item in items:
            obligations = []
            for obligation in item.participant_obligations:
                due = obligation.planned_due_date
                if obligation.source_type == "REQUIREMENT" and obligation.last_completion_date is None:
                    status = "NOT_DONE"
                elif due and due < evaluation_date:
                    status = "OVERDUE"
                elif due and (due - evaluation_date).days <= lead_days:
                    status = "DUE_SOON"
                else:
                    status = "EXPIRING"
                obligations.append(obligation.model_copy(update={"obligation_status": status}))
            result.append(item.model_copy(update={"participant_obligations": obligations}))
        return result
    return demand_items


__all__ = ["bridge_demand_items"]
