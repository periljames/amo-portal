"""A retained S3 object is not released from custody until DB commit succeeds."""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from amodb.apps.platform import storage_quota_upload as uploads


def test_rolled_back_uncommitted_object_is_deleted(monkeypatch):
    deleted = []
    monkeypatch.setattr(uploads.storage, "delete", deleted.append)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with Session(engine) as db:
        db.execute(text("SELECT 1"))
        uploads._track_uncommitted_object(db, "s3://managed/tenant-a/pending.pdf")
        db.rollback()
        assert deleted == ["s3://managed/tenant-a/pending.pdf"]
        assert not db.info.get(uploads._PENDING_OBJECTS)
    engine.dispose()


def test_committed_object_is_not_deleted(monkeypatch):
    deleted = []
    monkeypatch.setattr(uploads.storage, "delete", deleted.append)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with Session(engine) as db:
        db.execute(text("SELECT 1"))
        uploads._track_uncommitted_object(db, "s3://managed/tenant-a/committed.pdf")
        db.commit()
        assert deleted == []
        assert not db.info.get(uploads._PENDING_OBJECTS)
    engine.dispose()


def test_nested_commit_does_not_release_outer_custody(monkeypatch):
    deleted = []
    monkeypatch.setattr(uploads.storage, "delete", deleted.append)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with Session(engine) as db:
        db.execute(text("SELECT 1"))
        uploads._track_uncommitted_object(db, "s3://managed/tenant-a/outer.pdf")
        with db.begin_nested():
            db.execute(text("SELECT 2"))
        assert db.info.get(uploads._PENDING_OBJECTS)
        db.rollback()
        assert deleted == ["s3://managed/tenant-a/outer.pdf"]
    engine.dispose()
