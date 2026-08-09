# backend/amodb/database.py
"""Database configuration for AMOdb.

Key goals:
- Separate read and write engines.
- Bounded direct pools for small/medium deployments.
- External-pooler mode for horizontally scaled API/worker fleets.
- Transaction-level statement/idle guards that also work through PgBouncer.
- Optional read-only enforcement for read-session workloads.
- Backwards compatibility: ``engine``, ``SessionLocal`` and ``get_db``.
"""

import logging
import os

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

WRITE_DB_URL = os.getenv("DATABASE_WRITE_URL") or os.getenv("DATABASE_URL")
READ_DB_URL = os.getenv("DATABASE_READ_URL") or WRITE_DB_URL

if not WRITE_DB_URL:
    raise RuntimeError(
        "DATABASE_URL or DATABASE_WRITE_URL is not set. Example:\n"
        "postgresql+psycopg2://amodb_app:StrongPass!@192.168.5.55:5432/amodb"
    )


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _sqlite_allowed_for_tests(url: str) -> bool:
    app_env = (os.getenv("APP_ENV") or os.getenv("ENV") or "").strip().lower()
    allow_flag = (os.getenv("ALLOW_SQLITE_FOR_TESTS") or "").strip().lower()
    return url.startswith("sqlite") and app_env in {"test", "testing", "ci"} and allow_flag in {"1", "true", "yes", "on"}


if WRITE_DB_URL.startswith("sqlite") and not _sqlite_allowed_for_tests(WRITE_DB_URL):
    raise RuntimeError(
        "SQLite runtime database URLs are not allowed. Use PostgreSQL for runtime AMO Portal deployments. "
        "For isolated tests only, set APP_ENV=test and ALLOW_SQLITE_FOR_TESTS=1."
    )

EXTERNAL_POOLER = _env_bool("DB_EXTERNAL_POOLER", False)
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "20"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "5"))
POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE_SEC", "1800"))
STATEMENT_TIMEOUT_MS = max(1000, min(600000, int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "30000") or "30000")))
IDLE_IN_TRANSACTION_TIMEOUT_MS = max(5000, min(1800000, int(os.getenv("DB_IDLE_IN_TRANSACTION_TIMEOUT_MS", "60000") or "60000")))
READ_ONLY_TRANSACTIONS = _env_bool("DB_READ_ONLY_TRANSACTIONS", False)

COMMON_ENGINE_KWARGS = {
    "pool_pre_ping": True,
    "pool_size": POOL_SIZE,
    "max_overflow": MAX_OVERFLOW,
    "pool_timeout": POOL_TIMEOUT,
    "pool_recycle": POOL_RECYCLE,
    "pool_use_lifo": True,
    "pool_reset_on_return": "rollback",
    "future": True,
}


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        kwargs = {
            k: v
            for k, v in COMMON_ENGINE_KWARGS.items()
            if k not in {"pool_size", "max_overflow", "pool_timeout", "pool_recycle", "pool_use_lifo"}
        }
        kwargs["connect_args"] = {"check_same_thread": False}
        return kwargs
    if EXTERNAL_POOLER:
        # PgBouncer / managed DB proxies already multiplex connections. A local
        # QueuePool per API or worker process would multiply the connection budget.
        return {"pool_pre_ping": True, "poolclass": NullPool, "future": True}
    return dict(COMMON_ENGINE_KWARGS)


write_engine = create_engine(WRITE_DB_URL, **_engine_kwargs(WRITE_DB_URL))
if READ_DB_URL == WRITE_DB_URL:
    read_engine = write_engine
else:
    read_engine = create_engine(READ_DB_URL, **_engine_kwargs(READ_DB_URL))


class ReadOnlySession(Session):
    """Marker session class for optional transaction-level read-only enforcement."""


@event.listens_for(Session, "after_begin", propagate=True)
def _apply_transaction_guards(session: Session, transaction, connection) -> None:
    """Apply PostgreSQL guards inside each transaction.

    ``SET LOCAL`` is transaction-scoped, so it is safe with direct connections and
    transaction-pooled PgBouncer: settings cannot leak to a later borrower.
    """

    if getattr(connection.dialect, "name", "") != "postgresql":
        return
    connection.exec_driver_sql(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
    connection.exec_driver_sql(f"SET LOCAL idle_in_transaction_session_timeout = {IDLE_IN_TRANSACTION_TIMEOUT_MS}")
    if READ_ONLY_TRANSACTIONS and isinstance(session, ReadOnlySession):
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")


WriteSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=write_engine,
    expire_on_commit=False,
    future=True,
)
ReadSessionLocal = sessionmaker(
    class_=ReadOnlySession,
    autocommit=False,
    autoflush=False,
    bind=read_engine,
    expire_on_commit=False,
    future=True,
)

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata = MetaData(naming_convention=NAMING_CONVENTION)
Base = declarative_base(metadata=metadata)
logger = logging.getLogger(__name__)


def _is_shutdown_disconnect(exc: BaseException) -> bool:
    message = str(exc).lower()
    expected_fragments = (
        "server closed the connection unexpectedly",
        "no connection to the server",
        "connection already closed",
        "connection was closed",
        "connection reset",
        "terminating connection",
        "closed the connection",
    )
    return any(fragment in message for fragment in expected_fragments)


def close_session_safely(db: Session | None) -> None:
    if db is None:
        return
    try:
        db.close()
    except Exception as exc:  # pragma: no cover
        if _is_shutdown_disconnect(exc):
            try:
                db.invalidate()
            except Exception:
                pass
            logger.debug("Ignored database disconnect while closing session during shutdown: %s", exc)
            return
        logger.debug("Database session close failed", exc_info=True)


def dispose_engines() -> None:
    seen: set[int] = set()
    for current_engine in (write_engine, read_engine):
        marker = id(current_engine)
        if marker in seen:
            continue
        seen.add(marker)
        try:
            current_engine.dispose()
        except Exception as exc:  # pragma: no cover
            if not _is_shutdown_disconnect(exc):
                logger.debug("Database engine dispose failed", exc_info=True)


def get_write_db():
    db = WriteSessionLocal()
    try:
        yield db
    finally:
        close_session_safely(db)


def get_read_db():
    db = ReadSessionLocal()
    try:
        yield db
    finally:
        close_session_safely(db)


engine = write_engine
SessionLocal = WriteSessionLocal
get_db = get_write_db
