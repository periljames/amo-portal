import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Read the DATABASE_URL from environment variables.
# Example:
# postgresql+psycopg2://postgres:Q1w2e3r4t5y6!@192.168.5.55:5432/amodb
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Example:\n"
        "postgresql+psycopg2://postgres:Q1w2e3r4t5y6!@192.168.5.55:5432/amodb"
    )

# SQLAlchemy engine and session
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    future=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
)

# Base class for declarative models
Base = declarative_base()


# Dependency used in FastAPI routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
