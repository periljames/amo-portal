"""Keep retained-document artifacts consistent with the surrounding DB transaction."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import event
from sqlalchemy.orm import Session

from . import knowledge_service


_PENDING_ARTIFACTS_KEY = "documentation_pending_artifact_paths"
_OUTER_COMMIT_KEY = "documentation_outer_commit_pending"
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


def _mark_outer_commit_intent(session: Session) -> None:
    """Mark only commits of the outer transaction, never savepoint commits."""
    if not session.in_nested_transaction():
        session.info[_OUTER_COMMIT_KEY] = True


def _finalize_outer_commit(session: Session) -> None:
    """Finalize files only after an outer commit succeeds.

    SQLAlchemy emits ``after_commit`` for savepoint commits too. The marker is set
    by ``before_commit`` only when no nested transaction is active, so unrelated
    savepoint completion cannot release artifact custody early.
    """
    if session.info.pop(_OUTER_COMMIT_KEY, False):
        _clear_pending_artifacts(session)


def _cleanup_if_outer_transaction_ended(session: Session, transaction) -> None:
    """Remove uncommitted files when an outer transaction ends without commit.

    ``Session.close()`` may implicitly roll back without emitting ``after_rollback``.
    ``after_transaction_end`` is paired with every logical transaction. Nested
    savepoint endings are ignored; after a successful outer commit the pending set
    has already been cleared by ``_finalize_outer_commit``.
    """
    if getattr(transaction, "parent", None) is None:
        session.info.pop(_OUTER_COMMIT_KEY, None)
        if session.info.get(_PENDING_ARTIFACTS_KEY):
            _cleanup_pending_artifacts(session)


@event.listens_for(Session, "before_commit")
def _documentation_artifacts_before_commit(session: Session) -> None:
    _mark_outer_commit_intent(session)


@event.listens_for(Session, "after_commit")
def _documentation_artifacts_after_commit(session: Session) -> None:
    _finalize_outer_commit(session)


@event.listens_for(Session, "after_transaction_end")
def _documentation_artifacts_after_transaction_end(session: Session, transaction) -> None:
    _cleanup_if_outer_transaction_ended(session, transaction)


def _create_documentation_record_transactional(*args, **kwargs):
    session = args[0] if args else kwargs.get("db")
    row = _original_create_documentation_record(*args, **kwargs)
    if session is not None and getattr(row, "artifact_storage_path", None):
        _track_pending_artifact(session, row.artifact_storage_path)
    return row


knowledge_service.create_documentation_record = _create_documentation_record_transactional


__all__ = [
    "_cleanup_if_outer_transaction_ended",
    "_cleanup_pending_artifacts",
    "_clear_pending_artifacts",
    "_finalize_outer_commit",
    "_mark_outer_commit_intent",
    "_track_pending_artifact",
]
