"""Atomic replay adapter for explicitly registered JSON creation workflows.

Existing permission dependencies still run on every request. Opted-in handlers
flush their intermediate commits; the domain rows and receipt commit together
after the public response has validated successfully.
"""
from __future__ import annotations

import inspect
from functools import wraps
from typing import get_type_hints

from fastapi import Header, HTTPException
from pydantic import TypeAdapter

from . import command_service


class _CommandSession:
    def __init__(self, session):
        self._session = session
        self.rolled_back = False

    def __getattr__(self, name):
        return getattr(self._session, name)

    def commit(self):
        self._session.flush()

    def rollback(self):
        self.rolled_back = True
        self._session.rollback()

    def refresh(self, *args, **kwargs):
        self._session.flush()
        return self._session.refresh(*args, **kwargs)


def offline_create(path: str, response_model, *, status_code: int = 201, authorize=None):
    """Add exactly-once replay to a reviewed creation handler, never arbitrary routes."""
    def decorate(handler):
        signature = inspect.signature(handler)
        hints = get_type_hints(handler)
        parameters = [parameter.replace(annotation=hints.get(name, parameter.annotation))
                      for name, parameter in signature.parameters.items()]
        parameters.extend([
            inspect.Parameter("_offline_command", inspect.Parameter.KEYWORD_ONLY, annotation=str | None,
                              default=Header(None, alias="X-AMO-Offline-Command")),
            inspect.Parameter("_offline_key", inspect.Parameter.KEYWORD_ONLY, annotation=str | None,
                              default=Header(None, alias="Idempotency-Key")),
        ])
        adapter = TypeAdapter(response_model)

        @wraps(handler)
        def execute(*args, **kwargs):
            enabled = kwargs.pop("_offline_command", None)
            key = kwargs.pop("_offline_key", None)
            if enabled != "1":
                return handler(*args, **kwargs)
            if not isinstance(key, str) or not key.strip():
                raise HTTPException(422, detail="An Idempotency-Key is required for offline commands.")
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            db = bound.arguments["db"]
            user = bound.arguments["current_user"]
            amo_id = getattr(user, "effective_amo_id", None) or user.amo_id
            concrete_path = path.format_map({name: str(value) for name, value in bound.arguments.items()})
            route_key = f"portal.create:{concrete_path.rstrip('/')}"
            try:
                if authorize is not None:
                    authorize(bound.arguments)
                claim = command_service.begin_command(
                    db, amo_id=str(amo_id), actor_user_id=str(user.id), method="POST",
                    route_key=route_key, idempotency_key=key, payload=bound.arguments.get("payload"),
                )
                if claim.replayed:
                    if claim.row.status == "SUCCEEDED":
                        return claim.row.response_json
                    raise HTTPException(409, detail={"error_code": "COMMAND_IN_PROGRESS", "retryable": True})
                transaction = _CommandSession(db)
                bound.arguments["db"] = transaction
                result = handler(*bound.args, **bound.kwargs)
                if transaction.rolled_back:
                    raise HTTPException(409, detail={"error_code": "OFFLINE_COMMAND_ROLLED_BACK", "retryable": False})
                public = adapter.dump_python(adapter.validate_python(result, from_attributes=True), mode="json")
                command_service.complete_command(claim.row, response=public, status_code=status_code)
                db.commit()
                return public
            except command_service.CommandConflict as error:
                db.rollback()
                processing = "already being processed" in str(error)
                raise HTTPException(409, detail={
                    "error_code": "COMMAND_IN_PROGRESS" if processing else "IDEMPOTENCY_CONFLICT",
                    "detail": str(error), "retryable": processing,
                }) from error
            except Exception:
                db.rollback()
                raise

        execute.__signature__ = signature.replace(parameters=parameters, return_annotation=hints.get("return", signature.return_annotation))
        execute.offline_command_path = path
        return execute
    return decorate
