"""Keep retained-document artifacts consistent with the surrounding DB transaction."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import event
from sqlalchemy.orm import Session

from . import knowledge_service


_PENDING_ARTIFACTS_KEY = "documentation_pending_artifact_paths"
_original_create_documentation_record = knowledge_service.create_documentation_record


def _track_pending_artifact(session: Session, path_value: str) -> None:
    paths = session.info.setdefault(_PENDING_ARTIFACTS_KEY, set())
    paths.add(str(Path(path_value).resolve()))


def _clear_pending_artifacts(session: Session) -> None:
    session.info.pop(_PENDING_ARTIFACTS_KEY, None)


def _cleanup_pending_artifacts(session: Session) -> None:
    paths = set(session.info.pop(_PENDING_ARTIFACTS_KEY, set()))
    for path_value in paths:
        try:
            Path(path_value).unlink(missing_ok=True)
        except OSError:
            # Cleanup must never mask the transaction error. Operations can use the
            # persisted audit/error logs to investigate a filesystem permission fault.
            continue


@event.listens_for(Session, "after_commit")
def _documentation_artifacts_after_commit(session: Session) -> None:
    _clear_pending_artifacts(session)


@event.listens_for(Session, "after_rollback")
def _documentation_artifacts_after_rollback(session: Session) -> None:
    _cleanup_pending_artifacts(session)


def _create_documentation_record_transactional(*args, **kwargs):
    session = args[0] if args else kwargs.get("db")
    row = _original_create_documentation_record(*args, **kwargs)
    if session is not None and getattr(row, "artifact_storage_path", None):
        _track_pending_artifact(session, row.artifact_storage_path)
    return row


knowledge_service.create_documentation_record = _create_documentation_record_transactional


__all__ = [
    "_cleanup_pending_artifacts",
    "_clear_pending_artifacts",
    "_track_pending_artifact",
]
