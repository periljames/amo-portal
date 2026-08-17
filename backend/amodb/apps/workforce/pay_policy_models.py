from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import relationship

from ...database import Base
from ...user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EmploymentContractPayPolicy(Base):
    __tablename__ = "employment_contract_pay_policies"
    __table_args__ = (
        UniqueConstraint("amo_id", "contract_id", name="uq_contract_pay_policy_contract"),
        CheckConstraint("normal_duty_multiplier >= 1.000", name="ck_contract_pay_normal_floor"),
        CheckConstraint("ordinary_ot_multiplier >= 1.500", name="ck_contract_pay_ot_floor"),
        CheckConstraint("rest_day_multiplier >= 2.000", name="ck_contract_pay_rest_floor"),
        CheckConstraint("public_holiday_multiplier >= 2.000", name="ck_contract_pay_ph_floor"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id = Column(String(36), ForeignKey("employment_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    normal_duty_multiplier = Column(Numeric(6, 3), nullable=False, default=1)
    ordinary_ot_multiplier = Column(Numeric(6, 3), nullable=False, default=1.5)
    rest_day_multiplier = Column(Numeric(6, 3), nullable=False, default=2)
    public_holiday_multiplier = Column(Numeric(6, 3), nullable=False, default=2)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    contract = relationship("EmploymentContract", lazy="joined")
