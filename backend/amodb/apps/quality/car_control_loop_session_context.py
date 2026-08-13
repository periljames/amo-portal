from __future__ import annotations

from sqlalchemy import event, text
from sqlalchemy.orm import Session

from . import car_control_loop_guard_router, car_control_loop_router
from .tenant_security import set_postgres_tenant_context as _base_set_postgres_tenant_context

_CONTEXT_KEY = "quality_car_control_loop_tenant_context"


def set_persistent_control_loop_context(db: Session, *, amo_id: str, user_id: str) -> None:
    """Remember request context and set it transaction-locally for the active transaction."""

    db.info[_CONTEXT_KEY] = (str(amo_id), str(user_id))
    _base_set_postgres_tenant_context(db, amo_id=str(amo_id), user_id=str(user_id))


@event.listens_for(Session, "after_begin")
def _restore_control_loop_context_after_begin(session: Session, transaction, connection) -> None:  # noqa: ARG001
    context = session.info.get(_CONTEXT_KEY)
    if not context or connection.dialect.name != "postgresql":
        return
    amo_id, user_id = context
    connection.execute(text("SELECT set_config('app.tenant_id', :amo_id, true)"), {"amo_id": amo_id})
    connection.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": user_id})


# The route modules import this helper into their module globals. Replace those
# references after both routers are loaded so every control-loop request records
# its tenant/user context for automatic restoration after commit boundaries.
car_control_loop_router.set_postgres_tenant_context = set_persistent_control_loop_context
car_control_loop_guard_router.set_postgres_tenant_context = set_persistent_control_loop_context
