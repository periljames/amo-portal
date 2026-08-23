from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import models as platform_models


_INSTALLED = False
def install_command_queue() -> None:
    """Route Platform commands through the durable lease-fenced queue.

    API requests enqueue allowlisted commands; only a lease-owning worker executes
    their native action.
    """

    global _INSTALLED
    if _INSTALLED:
        return

    from . import services

    original_create = services.create_command_job

    # Preserve the native allowlisted action for the lease-owning worker, expose
    # execute_command_job as enqueue-only, and strip the caller-controlled
    # `approved=true` shortcut before job creation.
    if hasattr(services, "queue_command_job") and hasattr(services, "process_command_queue_job"):
        native_action = getattr(services, "_execute_command_action", None)
        if native_action is None:
            raise RuntimeError("Native Platform command queue is missing its worker action executor")
        def secure_create_command_job(
            db: Session,
            *,
            payload: dict[str, Any],
            actor_id: str,
        ) -> platform_models.PlatformCommandJob:
            safe_payload = dict(payload or {})
            safe_payload.pop("approved", None)
            return original_create(db, payload=safe_payload, actor_id=actor_id)

        def queue_native_execution(
            db: Session,
            job: platform_models.PlatformCommandJob,
            *,
            actor_id: str,
        ) -> None:
            services.queue_command_job(db, job, actor_id=actor_id)

        services.create_command_job = secure_create_command_job
        services.execute_command_job = queue_native_execution
        _INSTALLED = True
        return

    raise RuntimeError("Platform command service is missing native queue support")
