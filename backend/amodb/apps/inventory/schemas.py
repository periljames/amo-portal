from __future__ import annotations

from datetime import datetime, date
from typing import List, Optional

from pydantic import BaseModel, Field

from . import models


class InventoryPartCreate(BaseModel):
    part_number: str
    description: Optional[str] = None
    uom: str = "EA"
    is_serialized: bool = False
    is_lot_controlled: bool = False


class InventoryPartRead(InventoryPartCreate):
    id: int
    amo_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class InventoryLocationCreate(BaseModel):
    code: str
    name: str


class InventoryLocationRead(InventoryLocationCreate):
    id: int
    amo_id: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class InventoryMovementBase(BaseModel):
    part_number: str
    quantity: float = Field(..., gt=0)
    uom: str = "EA"
    lot_number: Optional[str] = None
    serial_number: Optional[str] = None
    from_location_id: Optional[int] = None
    to_location_id: Optional[int] = None
    work_order_id: Optional[int] = None
    task_card_id: Optional[int] = None
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    notes: Optional[str] = None
    idempotency_key: Optional[str] = None


class InventoryReceiveRequest(InventoryMovementBase):
    part_description: Optional[str] = None
    is_serialized: Optional[bool] = None
    is_lot_controlled: Optional[bool] = None
    condition: Optional[models.InventoryConditionEnum] = None
    received_date: Optional[date] = None


class InventoryInspectRequest(BaseModel):
    part_number: str
    lot_number: Optional[str] = None
    serial_number: Optional[str] = None
    location_id: int
    condition: models.InventoryConditionEnum
    notes: Optional[str] = None
    idempotency_key: Optional[str] = None


class InventoryTransferRequest(InventoryMovementBase):
    from_location_id: int
    to_location_id: int


class InventoryIssueRequest(InventoryMovementBase):
    to_location_id: Optional[int] = None


class InventoryReturnRequest(InventoryMovementBase):
    from_location_id: Optional[int] = None


class InventoryScrapRequest(InventoryMovementBase):
    reason_code: str


class InventoryLedgerRead(BaseModel):
    id: int
    amo_id: str
    part_id: int
    lot_id: Optional[int] = None
    serial_id: Optional[int] = None
    quantity: float
    uom: str
    event_type: models.InventoryMovementTypeEnum
    condition: Optional[models.InventoryConditionEnum] = None
    from_location_id: Optional[int] = None
    to_location_id: Optional[int] = None
    work_order_id: Optional[int] = None
    task_card_id: Optional[int] = None
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    reason_code: Optional[str] = None
    notes: Optional[str] = None
    occurred_at: datetime
    created_at: datetime
    created_by_user_id: Optional[str] = None

    class Config:
        from_attributes = True


class InventoryOnHandItem(BaseModel):
    part_number: str
    lot_number: Optional[str] = None
    serial_number: Optional[str] = None
    location_id: Optional[int] = None
    condition: Optional[models.InventoryConditionEnum] = None
    quantity: float


class PurchaseOrderLineCreate(BaseModel):
    part_id: Optional[int] = None
    description: Optional[str] = None
    quantity: float = Field(..., gt=0)
    uom: str = "EA"
    unit_price: float = 0.0


class PurchaseOrderCreate(BaseModel):
    po_number: str
    vendor_id: Optional[int] = None
    currency: str = "USD"
    notes: Optional[str] = None
    lines: List[PurchaseOrderLineCreate] = Field(default_factory=list)
    idempotency_key: Optional[str] = None


class PurchaseOrderRead(PurchaseOrderCreate):
    id: int
    amo_id: str
    status: models.PurchaseOrderStatusEnum
    approved_by_user_id: Optional[str] = None
    approved_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class GoodsReceiptLineCreate(BaseModel):
    part_id: Optional[int] = None
    lot_number: Optional[str] = None
    serial_number: Optional[str] = None
    quantity: float = Field(..., gt=0)
    uom: str = "EA"
    condition: Optional[models.InventoryConditionEnum] = None
    location_id: Optional[int] = None


class GoodsReceiptCreate(BaseModel):
    purchase_order_id: Optional[int] = None
    received_at: Optional[datetime] = None
    notes: Optional[str] = None
    lines: List[GoodsReceiptLineCreate] = Field(default_factory=list)
    idempotency_key: Optional[str] = None


class GoodsReceiptRead(GoodsReceiptCreate):
    id: int
    amo_id: str
    status: models.GoodsReceiptStatusEnum
    received_by_user_id: Optional[str] = None

    class Config:
        from_attributes = True
