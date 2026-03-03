from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from ...database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TechnicalRecordSetting(Base):
    __tablename__ = "technical_record_settings"

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    utilisation_manual_only = Column(Boolean, nullable=False, default=False)
    ad_sb_use_hours_cycles = Column(Boolean, nullable=False, default=False)
    record_retention_years = Column(Integer, nullable=False, default=5)
    allow_manual_maintenance_records = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class AircraftUtilisation(Base):
    __tablename__ = "technical_aircraft_utilisation"
    __table_args__ = (
        CheckConstraint("hours >= 0", name="ck_tr_util_hours_nonneg"),
        CheckConstraint("cycles >= 0", name="ck_tr_util_cycles_nonneg"),
        Index("ix_tr_util_amo_tail_date", "amo_id", "tail_id", "entry_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    tail_id = Column(String(50), ForeignKey("aircraft.serial_number", ondelete="CASCADE"), nullable=False, index=True)
    entry_date = Column(Date, nullable=False, index=True)
    hours = Column(Float, nullable=False)
    cycles = Column(Float, nullable=False)
    source = Column(String(16), nullable=False, default="Manual")
    conflict_flag = Column(Boolean, nullable=False, default=False)
    correction_reason = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class LogbookEntry(Base):
    __tablename__ = "technical_logbook_entries"
    __table_args__ = (Index("ix_tr_logbook_amo_tail_date", "amo_id", "tail_id", "entry_date"),)

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    tail_id = Column(String(50), ForeignKey("aircraft.serial_number", ondelete="CASCADE"), nullable=False, index=True)
    log_type = Column(String(16), nullable=False, default="Tech")
    entry_date = Column(Date, nullable=False, index=True)
    text = Column(Text, nullable=False)
    linked_wo_id = Column(Integer, ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True, index=True)
    linked_crs_id = Column(Integer, ForeignKey("crs.id", ondelete="SET NULL"), nullable=True, index=True)
    evidence_asset_ids = Column(JSON, nullable=False, default=list)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class Deferral(Base):
    __tablename__ = "technical_deferrals"
    __table_args__ = (Index("ix_tr_deferrals_amo_expiry", "amo_id", "expiry_at"),)

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    tail_id = Column(String(50), ForeignKey("aircraft.serial_number", ondelete="CASCADE"), nullable=False, index=True)
    defect_ref = Column(String(64), nullable=False, index=True)
    deferral_type = Column(String(32), nullable=False)
    deferred_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    expiry_at = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="Open", index=True)
    linked_wo_id = Column(Integer, ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True)
    linked_crs_id = Column(Integer, ForeignKey("crs.id", ondelete="SET NULL"), nullable=True)
    extension_history_json = Column(JSON, nullable=False, default=list)
    closure_notes = Column(Text, nullable=True)


class MaintenanceRecord(Base):
    __tablename__ = "technical_maintenance_records"
    __table_args__ = (
        Index("ix_tr_maint_records_amo_tail_date", "amo_id", "tail_id", "performed_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    tail_id = Column(String(50), ForeignKey("aircraft.serial_number", ondelete="CASCADE"), nullable=False, index=True)
    performed_at = Column(DateTime(timezone=True), nullable=False, index=True)
    description = Column(Text, nullable=False)
    reference_data_text = Column(Text, nullable=False)
    certifying_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    outcome = Column(String(64), nullable=False)
    linked_wo_id = Column(Integer, ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True)
    linked_wp_id = Column(String(64), nullable=True)
    evidence_asset_ids = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class AirworthinessItem(Base):
    __tablename__ = "technical_airworthiness_items"
    __table_args__ = (
        UniqueConstraint("amo_id", "item_type", "reference", name="uq_tr_airworthiness_ref"),
        Index("ix_tr_airworthiness_type_status", "amo_id", "item_type", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    item_type = Column(String(4), nullable=False, index=True)
    reference = Column(String(64), nullable=False, index=True)
    applicability_json = Column(JSON, nullable=False, default=dict)
    status = Column(String(32), nullable=False, default="Open")
    next_due_date = Column(Date, nullable=True)
    next_due_hours = Column(Float, nullable=True)
    next_due_cycles = Column(Float, nullable=True)


class AirworthinessComplianceEvent(Base):
    __tablename__ = "technical_airworthiness_compliance_events"
    __table_args__ = (Index("ix_tr_airworthiness_events_item", "amo_id", "item_id", "performed_at"),)

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("technical_airworthiness_items.id", ondelete="CASCADE"), nullable=False, index=True)
    tail_id = Column(String(50), ForeignKey("aircraft.serial_number", ondelete="SET NULL"), nullable=True)
    component_id = Column(Integer, ForeignKey("aircraft_components.id", ondelete="SET NULL"), nullable=True)
    performed_at = Column(DateTime(timezone=True), nullable=False)
    method_text = Column(Text, nullable=False)
    linked_wo_id = Column(Integer, ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True)
    evidence_asset_ids = Column(JSON, nullable=False, default=list)
    next_due_date = Column(Date, nullable=True)
    next_due_hours = Column(Float, nullable=True)
    next_due_cycles = Column(Float, nullable=True)


class ExceptionQueueItem(Base):
    __tablename__ = "technical_exception_queue"
    __table_args__ = (Index("ix_tr_exception_queue_amo_status", "amo_id", "status"),)

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    ex_type = Column(String(32), nullable=False, index=True)
    object_type = Column(String(64), nullable=False)
    object_id = Column(String(64), nullable=False)
    summary = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(16), nullable=False, default="Open", index=True)
    resolution_notes = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class AirworthinessWatchlist(Base):
    __tablename__ = "technical_airworthiness_watchlists"
    __table_args__ = (
        Index("ix_tr_watchlists_amo_status", "amo_id", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    status = Column(String(16), nullable=False, default="Active", index=True)
    criteria_json = Column(JSON, nullable=False, default=dict)
    run_count = Column(Integer, nullable=False, default=0)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class AirworthinessPublication(Base):
    __tablename__ = "technical_airworthiness_publications"
    __table_args__ = (
        UniqueConstraint("amo_id", "source", "doc_number", name="uq_tr_publication_source_doc"),
        Index("ix_tr_publications_amo_date", "amo_id", "published_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    source = Column(String(32), nullable=False, index=True)
    authority = Column(String(32), nullable=False, index=True)
    document_type = Column(String(32), nullable=False, index=True)
    doc_number = Column(String(96), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    ata_chapter = Column(String(16), nullable=True)
    effectivity_summary = Column(Text, nullable=True)
    keywords = Column(JSON, nullable=False, default=list)
    raw_metadata_json = Column(JSON, nullable=False, default=dict)
    source_link = Column(String(512), nullable=True)
    published_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class AirworthinessPublicationMatch(Base):
    __tablename__ = "technical_airworthiness_publication_matches"
    __table_args__ = (
        UniqueConstraint("amo_id", "watchlist_id", "publication_id", name="uq_tr_watchlist_publication_match"),
        Index("ix_tr_pub_match_amo_status", "amo_id", "review_status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    watchlist_id = Column(Integer, ForeignKey("technical_airworthiness_watchlists.id", ondelete="CASCADE"), nullable=False, index=True)
    publication_id = Column(Integer, ForeignKey("technical_airworthiness_publications.id", ondelete="CASCADE"), nullable=False, index=True)
    classification = Column(String(32), nullable=False, default="Potentially Applicable", index=True)
    matched_fleet_json = Column(JSON, nullable=False, default=list)
    matched_components_json = Column(JSON, nullable=False, default=list)
    review_status = Column(String(32), nullable=False, default="Matched", index=True)
    assigned_reviewer_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ComplianceAction(Base):
    __tablename__ = "technical_compliance_actions"
    __table_args__ = (
        Index("ix_tr_comp_actions_amo_status", "amo_id", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    publication_match_id = Column(Integer, ForeignKey("technical_airworthiness_publication_matches.id", ondelete="CASCADE"), nullable=False, index=True)
    decision = Column(String(48), nullable=False)
    status = Column(String(32), nullable=False, default="Under Review", index=True)
    due_date = Column(Date, nullable=True)
    due_hours = Column(Float, nullable=True)
    due_cycles = Column(Float, nullable=True)
    recurring_interval_days = Column(Integer, nullable=True)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    package_ref = Column(String(64), nullable=True)
    work_order_ref = Column(String(64), nullable=True)
    evidence_json = Column(JSON, nullable=False, default=list)
    decision_notes = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class ComplianceActionHistory(Base):
    __tablename__ = "technical_compliance_action_history"
    __table_args__ = (Index("ix_tr_comp_hist_amo_action", "amo_id", "compliance_action_id"),)

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    compliance_action_id = Column(Integer, ForeignKey("technical_compliance_actions.id", ondelete="CASCADE"), nullable=False, index=True)
    from_status = Column(String(32), nullable=True)
    to_status = Column(String(32), nullable=False)
    event_type = Column(String(32), nullable=False)
    event_notes = Column(Text, nullable=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
