# backend/amodb/apps/work/router.py
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...database import get_db
from . import models, schemas

router = APIRouter(prefix="/work-orders", tags=["work_orders"])


@router.get("/", response_model=List[schemas.WorkOrderRead])
def list_work_orders(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    q = (
        db.query(models.WorkOrder)
        .order_by(models.WorkOrder.wo_number.asc())
        .offset(skip)
        .limit(limit)
    )
    return q.all()


@router.get("/{work_order_id}", response_model=schemas.WorkOrderRead)
def get_work_order(work_order_id: int, db: Session = Depends(get_db)):
    wo = db.query(models.WorkOrder).filter(models.WorkOrder.id == work_order_id).first()
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")
    return wo


@router.get("/by-number/{wo_number}", response_model=schemas.WorkOrderRead)
def get_work_order_by_number(wo_number: str, db: Session = Depends(get_db)):
    wo = db.query(models.WorkOrder).filter(models.WorkOrder.wo_number == wo_number).first()
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")
    return wo


@router.post("/", response_model=schemas.WorkOrderRead, status_code=status.HTTP_201_CREATED)
def create_work_order(
    payload: schemas.WorkOrderCreate,
    db: Session = Depends(get_db),
):
    existing = (
        db.query(models.WorkOrder)
        .filter(models.WorkOrder.wo_number == payload.wo_number)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Work order {payload.wo_number} already exists.",
        )

    wo = models.WorkOrder(
        wo_number=payload.wo_number,
        aircraft_serial_number=payload.aircraft_serial_number,
        amo_code=payload.amo_code,
        description=payload.description,
        check_type=payload.check_type,
        due_date=payload.due_date,
        open_date=payload.open_date,
        is_scheduled=payload.is_scheduled,
        status=payload.status,
    )
    db.add(wo)
    db.flush()

    for t in payload.tasks:
        task = models.WorkOrderTask(
            work_order_id=wo.id,
            task_code=t.task_code,
            description=t.description,
            is_non_routine=t.is_non_routine,
            status=t.status,
        )
        db.add(task)

    db.commit()
    db.refresh(wo)
    return wo


@router.put("/{work_order_id}", response_model=schemas.WorkOrderRead)
def update_work_order(
    work_order_id: int,
    payload: schemas.WorkOrderUpdate,
    db: Session = Depends(get_db),
):
    wo = db.query(models.WorkOrder).filter(models.WorkOrder.id == work_order_id).first()
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(wo, field, value)

    db.add(wo)
    db.commit()
    db.refresh(wo)
    return wo


@router.delete("/{work_order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_work_order(work_order_id: int, db: Session = Depends(get_db)):
    wo = db.query(models.WorkOrder).filter(models.WorkOrder.id == work_order_id).first()
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")

    db.delete(wo)
    db.commit()
    return
