"""Contracts for correcting, ending and transferring reporting assignments."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class ReportingAssignmentUpdate(BaseModel):
    reporting_manager_user_id: Optional[str] = None
    assignment_type: Optional[str] = Field(default=None, max_length=32)
    effective_to: Optional[date] = None
    fte_percent: Optional[Decimal] = Field(default=None, gt=0, le=100)
    matrix_reporting: Optional[bool] = None
    matrix_reason: Optional[str] = Field(default=None, max_length=2000)
    display_title: Optional[str] = Field(default=None, min_length=2, max_length=128)
    delegation_limitations: Optional[str] = Field(default=None, max_length=4000)
    notes: Optional[str] = Field(default=None, max_length=4000)


class ReportingAssignmentEnd(BaseModel):
    end_on: date
    reason: str = Field(min_length=2, max_length=2000)


class ReportingAssignmentTransfer(BaseModel):
    target_position_id: str
    effective_from: date
    reporting_manager_user_id: Optional[str] = None
    assignment_type: str = Field(default="SUBSTANTIVE", max_length=32)
    fte_percent: Decimal = Field(default=Decimal("100"), gt=0, le=100)
    matrix_reporting: bool = False
    matrix_reason: Optional[str] = Field(default=None, max_length=2000)
    display_title: Optional[str] = Field(default=None, min_length=2, max_length=128)
    appointment_reference: Optional[str] = Field(default=None, max_length=128)
    authority_acceptance_reference: Optional[str] = Field(default=None, max_length=128)
    authority_accepted_on: Optional[date] = None
    delegation_limitations: Optional[str] = Field(default=None, max_length=4000)
    reason: str = Field(min_length=2, max_length=2000)

    @model_validator(mode="after")
    def validate_matrix_reason(self):
        if self.matrix_reporting and not str(self.matrix_reason or "").strip():
            raise ValueError("A reason is required for matrix reporting.")
        return self
