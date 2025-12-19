# backend/amodb/apps/crs/models.py
from __future__ import annotations

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
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from ...database import Base


class CRS(Base):
    """
    Main CRS record.

    Chain:
      Aircraft -> WorkOrder -> TaskCard(s) -> CRS

    Notes:
    - CRS records are compliance artifacts; deletion should be restricted operationally.
    - We add indexes that match typical query paths: by aircraft, by work order, by issue date.
    """

    __tablename__ = "crs"

    __table_args__ = (
        # Common reporting query: all CRS for an aircraft over time
        Index("ix_crs_aircraft_issue_date", "aircraft_serial_number", "crs_issue_date"),
        # Audit trace by creator
        Index("ix_crs_created_by", "created_by_id"),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Identity / barcode
    crs_serial = Column(String(50), unique=True, index=True, nullable=False)
    barcode_value = Column(String(255), nullable=False)

    # Links
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    work_order_id = Column(
        Integer,
        ForeignKey("work_orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # For quick filtering (A, C, 200HR)
    check_type = Column(String(20), nullable=True, index=True)

    # Section 1 – Releasing authority & job header
    releasing_authority = Column(String(10), nullable=False)  # 'KCAA', 'ECAA', 'GCAA'
    operator_contractor = Column(String(255), nullable=False)
    job_no = Column(String(100), nullable=True)
    wo_no = Column(String(100), nullable=True)
    location = Column(String(255), nullable=True)

    # Aircraft & engines (snapshot)
    aircraft_type = Column(String(100), nullable=False)
    aircraft_reg = Column(String(50), nullable=False, index=True)
    msn = Column(String(50), nullable=True)

    lh_engine_type = Column(String(100), nullable=True)
    rh_engine_type = Column(String(100), nullable=True)
    lh_engine_sno = Column(String(100), nullable=True)
    rh_engine_sno = Column(String(100), nullable=True)

    aircraft_tat = Column(Float, nullable=True)
    aircraft_tac = Column(Float, nullable=True)
    lh_hrs = Column(Float, nullable=True)
    lh_cyc = Column(Float, nullable=True)
    rh_hrs = Column(Float, nullable=True)
    rh_cyc = Column(Float, nullable=True)

    # Work / deferred maintenance
    maintenance_carried_out = Column(Text, nullable=False)
    deferred_maintenance = Column(Text, nullable=True)
    date_of_completion = Column(Date, nullable=False, index=True)

    # Maintenance data – check boxes
    amp_used = Column(Boolean, nullable=False, default=False)
    amm_used = Column(Boolean, nullable=False, default=False)
    mtx_data_used = Column(Boolean, nullable=False, default=False)

    amp_reference = Column(String(255), nullable=True)
    amp_revision = Column(String(50), nullable=True)
    amp_issue_date = Column(Date, nullable=True)

    amm_reference = Column(String(255), nullable=True)
    amm_revision = Column(String(50), nullable=True)
    amm_issue_date = Column(Date, nullable=True)

    add_mtx_data = Column(String(255), nullable=True)
    work_order_no = Column(String(100), nullable=True)

    # Expiry / next check (Section 12 & 13)
    airframe_limit_unit = Column(String(10), nullable=False)  # 'HOURS' / 'CYCLES'
    expiry_date = Column(Date, nullable=True, index=True)
    hrs_to_expiry = Column(Float, nullable=True)
    sum_airframe_tat_expiry = Column(Float, nullable=True)
    next_maintenance_due = Column(String(255), nullable=True)

    # Certificate issued by (Section 14)
    issuer_full_name = Column(String(255), nullable=False)
    issuer_auth_ref = Column(String(255), nullable=False)
    issuer_license = Column(String(100), nullable=False)
    crs_issue_date = Column(Date, nullable=False, index=True)
    crs_issuing_stamp = Column(String(255), nullable=True)

    # Audit trail / retention
    # NOTE: users.id is a GUID (String(36)) from the accounts app.
    created_by_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
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

    is_archived = Column(Boolean, nullable=False, default=False, index=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    signoffs = relationship(
        "CRSSignoff",
        back_populates="crs",
        cascade="all, delete-orphan",
        lazy="selectin",  # avoids row explosion from joined loading
        passive_deletes=True,
    )

    aircraft = relationship("Aircraft", back_populates="crs_list", lazy="joined")
    work_order = relationship("WorkOrder", back_populates="crs_list", lazy="joined")

    def __repr__(self) -> str:
        return f"<CRS id={self.id} serial={self.crs_serial} aircraft={self.aircraft_serial_number}>"


class CRSSignoff(Base):
    """
    Category rows (A – Aeroplanes, C – Engines, etc.).

    Long-run protection:
    - prevent duplicate category rows for the same CRS (unique constraint)
    - index CRS FK for faster joins
    """

    __tablename__ = "crs_signoff"

    __table_args__ = (
        UniqueConstraint("crs_id", "category", name="uq_crs_signoff_crs_category"),
        Index("ix_crs_signoff_crs", "crs_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    crs_id = Column(
        Integer,
        ForeignKey("crs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    category = Column(String(50), nullable=False)  # e.g. 'AEROPLANES', 'C-ENGINES'
    sign_date = Column(Date, nullable=True)

    full_name_and_signature = Column(String(255), nullable=True)
    internal_auth_ref = Column(String(255), nullable=True)
    stamp = Column(String(255), nullable=True)

    crs = relationship("CRS", back_populates="signoffs", lazy="joined")

    def __repr__(self) -> str:
        return f"<CRSSignoff id={self.id} crs_id={self.crs_id} category={self.category}>"
