# backend/amodb/database.py
"""
Database configuration for AMOdb.

Key goals:
- Separate read and write engines (ready for replicas later).
- Sensible direct connection pooling for small/medium deployments.
- External-pooler mode for horizontally scaled API/worker fleets.
- Backwards compatibility: `engine`, `SessionLocal` and `get_db` still work.
"""

import os
import logging

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

# -------------------------------------------------------------------
# CONFIG FROM ENV
# -------------------------------------------------------------------
#
# WRITE:
#   DATABASE_WRITE_URL  (preferred)
#   DATABASE_URL        (fallback)
#
# READ:
#   DATABASE_READ_URL   (if you add a replica)
#   otherwise defaults to WRITE URL
#
# SCALE:
#   DB_EXTERNAL_POOLER=true when the DSN points at PgBouncer/a managed DB proxy.
#   In that mode SQLAlchemy does not create an independent pool per API/worker
#   process; the external pooler owns the connection budget.
# -------------------------------------------------------------------

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

# Direct-pool tuning. Do not increase this blindly when scaling process count;
# use PgBouncer or a managed database proxy and DB_EXTERNAL_POOLER=true instead.
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "20"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "5"))
POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE_SEC", "1800"))

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

# -------------------------------------------------------------------
# ENGINES
# -------------------------------------------------------------------

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
        # PgBouncer / managed proxies already multiplex connections. A process-
        # local QueuePool on top multiplies connection pressure by API+worker
        # process count and defeats the external connection budget.
        return {
            "pool_pre_ping": True,
            "poolclass": NullPool,
            "future": True,
        }
    return COMMON_ENGINE_KWARGS


# All writes go here (and reads if you have a single DB)
write_engine = create_engine(WRITE_DB_URL, **_engine_kwargs(WRITE_DB_URL))

# Read engine – if READ and WRITE point at the same DSN, reuse the same engine
# so the app shares one pool instead of opening two independent pools against the
# same PostgreSQL server. When a read replica is configured, read-heavy platform
# and tenant endpoints can scale independently from the write primary.
if READ_DB_URL == WRITE_DB_URL:
    read_engine = write_engine
else:
    read_engine = create_engine(READ_DB_URL, **_engine_kwargs(READ_DB_URL))

# -------------------------------------------------------------------
# SESSIONS
# -------------------------------------------------------------------

WriteSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=write_engine,
    expire_on_commit=False,
    future=True,
)

ReadSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=read_engine,
    expire_on_commit=False,
    future=True,
)

# Declarative base for all models with stable naming conventions for Alembic.
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

# -------------------------------------------------------------------
# DEPENDENCIES (for FastAPI)
# -------------------------------------------------------------------

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
    """Close a SQLAlchemy session without noisy traceback spam during shutdown."""
    if db is None:
        return
    try:
        db.close()
    except Exception as exc:  # pragma: no cover - depends on DB shutdown timing
        if _is_shutdown_disconnect(exc):
            try:
                db.invalidate()
            except Exception:
                pass
            logger.debug("Ignored database disconnect while closing session during shutdown: %s", exc)
            return
        logger.debug("Database session close failed", exc_info=True)


def dispose_engines() -> None:
    """Dispose read/write pools without creating duplicate waits on the same engine."""
    seen: set[int] = set()
    for current_engine in (write_engine, read_engine):
        marker = id(current_engine)
        if marker in seen:
            continue
        seen.add(marker)
        try:
            current_engine.dispose()
        except Exception as exc:  # pragma: no cover - defensive shutdown path
            if not _is_shutdown_disconnect(exc):
                logger.debug("Database engine dispose failed", exc_info=True)


def get_write_db():
    """Dependency for endpoints that perform INSERT / UPDATE / DELETE."""
    db = WriteSessionLocal()
    try:
        yield db
    finally:
        close_session_safely(db)


def get_read_db():
    """Dependency for read-only endpoints, optionally backed by a replica."""
    db = ReadSessionLocal()
    try:
        yield db
    finally:
        close_session_safely(db)


# -------------------------------------------------------------------
# BACKWARDS-COMPATIBILITY (existing imports)
# -------------------------------------------------------------------

engine = write_engine
SessionLocal = WriteSessionLocal
get_db = get_write_db
