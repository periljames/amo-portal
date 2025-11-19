# backend/amodb/apps/crs/models.py
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from ...database import Base


class CRS(Base):
    """
    Main CRS record.

    Note: some fields (aircraft_* and *_engine_*) will normally be
    read-only in the UI and filled from aircraft / engine tables.
    They are stored here as a snapshot so the PDF is reproducible.
    """

    __tablename__ = "crs"

    id = Column(Integer, primary_key=True, index=True)

    # Identity / barcode
    crs_serial = Column(String(50), unique=True, index=True, nullable=False)
    barcode_value = Column(String(255), nullable=False)

    # Section 1 – Releasing authority & job header
    releasing_authority = Column(String(10), nullable=False)  # 'KCAA', 'ECAA', 'GCAA'
    operator_contractor = Column(String(255), nullable=False)
    job_no = Column(String(100))
    wo_no = Column(String(100))
    location = Column(String(255))

    # Aircraft & engines (usually read-only – from DB)
    aircraft_type = Column(String(100), nullable=False)
    aircraft_reg = Column(String(50), nullable=False, index=True)
    msn = Column(String(50))

    lh_engine_type = Column(String(100))
    rh_engine_type = Column(String(100))
    lh_engine_sno = Column(String(100))
    rh_engine_sno = Column(String(100))

    aircraft_tat = Column(Float)
    aircraft_tac = Column(Float)
    lh_hrs = Column(Float)
    lh_cyc = Column(Float)
    rh_hrs = Column(Float)
    rh_cyc = Column(Float)

    # Work / deferred maintenance
    maintenance_carried_out = Column(Text, nullable=False)
    deferred_maintenance = Column(Text)
    date_of_completion = Column(Date, nullable=False)

    # Maintenance data – check boxes
    amp_used = Column(Boolean, nullable=False, default=False)
    amm_used = Column(Boolean, nullable=False, default=False)
    mtx_data_used = Column(Boolean, nullable=False, default=False)

    amp_reference = Column(String(255))
    amp_revision = Column(String(50))
    amp_issue_date = Column(Date)

    amm_reference = Column(String(255))
    amm_revision = Column(String(50))
    amm_issue_date = Column(Date)

    add_mtx_data = Column(String(255))
    work_order_no = Column(String(100))

    # Expiry / next check (Section 12 & 13)
    airframe_limit_unit = Column(String(10), nullable=False)  # 'HOURS' / 'CYCLES'
    expiry_date = Column(Date)
    hrs_to_expiry = Column(Float)
    sum_airframe_tat_expiry = Column(Float)  # SUM(Aircraft TAT, Hrs to Expiry)
    next_maintenance_due = Column(String(255))

    # Certificate issued by (Section 14)
    issuer_full_name = Column(String(255), nullable=False)
    issuer_auth_ref = Column(String(255), nullable=False)
    issuer_license = Column(String(100), nullable=False)  # Category (A&C) licence
    crs_issue_date = Column(Date, nullable=False)
    crs_issuing_stamp = Column(String(255))  # could be a path / code for the stamp

    # Audit trail / retention
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # 36-month retention – we *archive* here; purge job can clean after expires_at
    is_archived = Column(Boolean, nullable=False, default=False)
    archived_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))

    # Child rows – category sign-offs (“A – Aeroplanes”, “C – Engines”, etc)
    signoffs = relationship(
        "CRSSignoff",
        back_populates="crs",
        cascade="all, delete-orphan",
        lazy="joined",
    )


class CRSSignoff(Base):
    """
    One row in the category table (A – Aeroplanes, C – Engines, etc).

    The PDF has 7 rows; store them all in one table keyed by `category`.
    """

    __tablename__ = "crs_signoff"

    id = Column(Integer, primary_key=True, index=True)
    crs_id = Column(Integer, ForeignKey("crs.id", ondelete="CASCADE"), nullable=False)

    category = Column(String(50), nullable=False)  # e.g. 'AEROPLANES', 'C-ENGINES'
    sign_date = Column(Date)
    full_name_and_signature = Column(String(255))
    internal_auth_ref = Column(String(255))
    stamp = Column(String(255))

    crs = relationship("CRS", back_populates="signoffs")
