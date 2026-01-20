from __future__ import annotations

import enum
from datetime import datetime, date

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from amodb.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class InventoryMovementTypeEnum(str, enum.Enum):
    RECEIVE = "RECEIVE"
    INSPECT = "INSPECT"
    TRANSFER = "TRANSFER"
    ISSUE = "ISSUE"
    RETURN = "RETURN"
    SCRAP = "SCRAP"
    VENDOR_RETURN = "VENDOR_RETURN"
    ADJUSTMENT = "ADJUSTMENT"
    CYCLE_COUNT = "CYCLE_COUNT"


class InventoryConditionEnum(str, enum.Enum):
    QUARANTINE = "QUARANTINE"
    SERVICEABLE = "SERVICEABLE"
    UNSERVICEABLE = "UNSERVICEABLE"


class PurchaseOrderStatusEnum(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class GoodsReceiptStatusEnum(str, enum.Enum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"


class InventoryPart(Base):
    __tablename__ = "inventory_parts"
    __table_args__ = (
        UniqueConstraint("amo_id", "part_number", name="uq_inventory_part_number"),
        Index("ix_inventory_parts_amo_part", "amo_id", "part_number"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    part_number = Column(String(64), nullable=False, index=True)
    description = Column(String(255), nullable=True)
    uom = Column(String(16), nullable=False, default="EA")
    is_serialized = Column(Boolean, nullable=False, default=False)
    is_lot_controlled = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    lots = relationship("InventoryLot", back_populates="part", lazy="selectin")
    serials = relationship("InventorySerial", back_populates="part", lazy="selectin")


class InventoryLocation(Base):
    __tablename__ = "inventory_locations"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_inventory_location_code"),
        Index("ix_inventory_locations_amo", "amo_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(32), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class InventoryLot(Base):
    __tablename__ = "inventory_lots"
    __table_args__ = (
        UniqueConstraint("amo_id", "part_id", "lot_number", name="uq_inventory_lot"),
        Index("ix_inventory_lots_part", "part_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    part_id = Column(Integer, ForeignKey("inventory_parts.id", ondelete="CASCADE"), nullable=False, index=True)
    lot_number = Column(String(64), nullable=False, index=True)
    expiry_date = Column(Date, nullable=True)
    received_date = Column(Date, nullable=True)

    part = relationship("InventoryPart", back_populates="lots", lazy="joined")


class InventorySerial(Base):
    __tablename__ = "inventory_serials"
    __table_args__ = (
        UniqueConstraint("amo_id", "part_id", "serial_number", name="uq_inventory_serial"),
        Index("ix_inventory_serials_part", "part_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    part_id = Column(Integer, ForeignKey("inventory_parts.id", ondelete="CASCADE"), nullable=False, index=True)
    serial_number = Column(String(64), nullable=False, index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    part = relationship("InventoryPart", back_populates="serials", lazy="joined")


class InventoryMovementLedger(Base):
    __tablename__ = "inventory_movement_ledger"
    __table_args__ = (
        Index("ix_inventory_ledger_amo_date", "amo_id", "occurred_at"),
        Index("ix_inventory_ledger_part", "part_id", "occurred_at"),
        UniqueConstraint("amo_id", "idempotency_key", name="uq_inventory_ledger_idempotency"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    idempotency_key = Column(String(128), nullable=True, index=True)

    part_id = Column(Integer, ForeignKey("inventory_parts.id", ondelete="CASCADE"), nullable=False, index=True)
    lot_id = Column(Integer, ForeignKey("inventory_lots.id", ondelete="SET NULL"), nullable=True, index=True)
    serial_id = Column(Integer, ForeignKey("inventory_serials.id", ondelete="SET NULL"), nullable=True, index=True)

    quantity = Column(Float, nullable=False)
    uom = Column(String(16), nullable=False, default="EA")
    event_type = Column(
        SAEnum(InventoryMovementTypeEnum, name="inventory_movement_type_enum", native_enum=False),
        nullable=False,
        index=True,
    )
    condition = Column(
        SAEnum(InventoryConditionEnum, name="inventory_condition_enum", native_enum=False),
        nullable=True,
        index=True,
    )

    from_location_id = Column(Integer, ForeignKey("inventory_locations.id", ondelete="SET NULL"), nullable=True)
    to_location_id = Column(Integer, ForeignKey("inventory_locations.id", ondelete="SET NULL"), nullable=True)

    work_order_id = Column(Integer, ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True)
    task_card_id = Column(Integer, ForeignKey("task_cards.id", ondelete="SET NULL"), nullable=True)

    reference_type = Column(String(64), nullable=True)
    reference_id = Column(String(64), nullable=True)
    reason_code = Column(String(64), nullable=True)
    notes = Column(Text, nullable=True)

    occurred_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    part = relationship("InventoryPart", lazy="joined")
    lot = relationship("InventoryLot", lazy="joined")
    serial = relationship("InventorySerial", lazy="joined")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("amo_id", "po_number", name="uq_purchase_order_number"),
        Index("ix_purchase_orders_amo", "amo_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    po_number = Column(String(64), nullable=False, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True)
    status = Column(
        SAEnum(PurchaseOrderStatusEnum, name="purchase_order_status_enum", native_enum=False),
        nullable=False,
        default=PurchaseOrderStatusEnum.DRAFT,
        index=True,
    )
    currency = Column(String(8), nullable=False, default="USD")
    requested_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    lines = relationship("PurchaseOrderLine", back_populates="purchase_order", lazy="selectin")


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (Index("ix_purchase_order_lines_po", "purchase_order_id"),)

    id = Column(Integer, primary_key=True, index=True)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False)
    part_id = Column(Integer, ForeignKey("inventory_parts.id", ondelete="SET NULL"), nullable=True)
    description = Column(String(255), nullable=True)
    quantity = Column(Float, nullable=False)
    uom = Column(String(16), nullable=False, default="EA")
    unit_price = Column(Float, nullable=False, default=0.0)

    purchase_order = relationship("PurchaseOrder", back_populates="lines", lazy="joined")
    part = relationship("InventoryPart", lazy="joined")


class GoodsReceipt(Base):
    __tablename__ = "goods_receipts"
    __table_args__ = (Index("ix_goods_receipts_amo", "amo_id"),)

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    received_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(
        SAEnum(GoodsReceiptStatusEnum, name="goods_receipt_status_enum", native_enum=False),
        nullable=False,
        default=GoodsReceiptStatusEnum.DRAFT,
        index=True,
    )
    notes = Column(Text, nullable=True)

    lines = relationship("GoodsReceiptLine", back_populates="receipt", lazy="selectin")


class GoodsReceiptLine(Base):
    __tablename__ = "goods_receipt_lines"
    __table_args__ = (Index("ix_goods_receipt_lines_receipt", "goods_receipt_id"),)

    id = Column(Integer, primary_key=True, index=True)
    goods_receipt_id = Column(Integer, ForeignKey("goods_receipts.id", ondelete="CASCADE"), nullable=False)
    part_id = Column(Integer, ForeignKey("inventory_parts.id", ondelete="SET NULL"), nullable=True)
    lot_number = Column(String(64), nullable=True)
    serial_number = Column(String(64), nullable=True)
    quantity = Column(Float, nullable=False)
    uom = Column(String(16), nullable=False, default="EA")
    condition = Column(
        SAEnum(InventoryConditionEnum, name="goods_receipt_condition_enum", native_enum=False),
        nullable=True,
    )
    location_id = Column(Integer, ForeignKey("inventory_locations.id", ondelete="SET NULL"), nullable=True)

    receipt = relationship("GoodsReceipt", back_populates="lines", lazy="joined")
    part = relationship("InventoryPart", lazy="joined")
    location = relationship("InventoryLocation", lazy="joined")
