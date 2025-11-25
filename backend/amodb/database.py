# backend/amodb/database.py
"""
Database configuration for AMOdb.

Key goals:
- Separate read and write engines (ready for replicas later).
- Sensible connection pooling for 24/7 uptime.
- Backwards compatibility: `engine`, `SessionLocal` and `get_db` still work.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

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
# Example value:
#   postgresql+psycopg2://amodb_app:password@192.168.5.55:5432/amodb
# -------------------------------------------------------------------

WRITE_DB_URL = os.getenv("DATABASE_WRITE_URL") or os.getenv("DATABASE_URL")
READ_DB_URL = os.getenv("DATABASE_READ_URL") or WRITE_DB_URL

if not WRITE_DB_URL:
    raise RuntimeError(
        "DATABASE_URL or DATABASE_WRITE_URL is not set. Example:\n"
        "postgresql+psycopg2://amodb_app:StrongPass!@192.168.5.55:5432/amodb"
    )

# Pool tuning – tuned for low-latency, small-to-medium AMO deployments.
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))          # seconds
POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE_SEC", "1800"))    # 30 minutes

COMMON_ENGINE_KWARGS = {
    "pool_pre_ping": True,                # detect dead connections
    "pool_size": POOL_SIZE,
    "max_overflow": MAX_OVERFLOW,
    "pool_timeout": POOL_TIMEOUT,
    "pool_recycle": POOL_RECYCLE,
    "future": True,
}

# -------------------------------------------------------------------
# ENGINES
# -------------------------------------------------------------------

# All writes go here (and reads if you have a single DB)
write_engine = create_engine(WRITE_DB_URL, **COMMON_ENGINE_KWARGS)

# Read engine – today this can be the same as write, later a replica
read_engine = create_engine(READ_DB_URL, **COMMON_ENGINE_KWARGS)

# -------------------------------------------------------------------
# SESSIONS
# -------------------------------------------------------------------

WriteSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=write_engine,
    future=True,
)

ReadSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=read_engine,
    future=True,
)

# Declarative base for all models
Base = declarative_base()

# -------------------------------------------------------------------
# DEPENDENCIES (for FastAPI)
# -------------------------------------------------------------------

def get_write_db():
    """
    Dependency for endpoints that perform INSERT / UPDATE / DELETE.
    """
    db = WriteSessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_read_db():
    """
    Dependency for read-only endpoints.

    For now this may hit the same server, but your application code
    is already split. When you add a read replica, you only need to
    change DATABASE_READ_URL.
    """
    db = ReadSessionLocal()
    try:
        yield db
    finally:
        db.close()


# -------------------------------------------------------------------
# BACKWARDS-COMPATIBILITY (existing imports)
# -------------------------------------------------------------------

# Older code uses `engine`, `SessionLocal` and `get_db`.
# They now point to the WRITE side.
engine = write_engine
SessionLocal = WriteSessionLocal
get_db = get_write_db
