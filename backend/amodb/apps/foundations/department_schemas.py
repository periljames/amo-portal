# backend/amodb/apps/foundations/department_schemas.py
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class DepartmentCatalogCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    default_route: Optional[str] = Field(default=None, max_length=255)
    sort_order: int = Field(default=100, ge=0, le=100000)
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def normalise_code(cls, value: str) -> str:
        cleaned = "_".join(value.strip().upper().replace("-", "_").split())
        if not cleaned:
            raise ValueError("Department code is required.")
        return cleaned

    @field_validator("name")
    @classmethod
    def normalise_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Department name is required.")
        return cleaned


class DepartmentCatalogUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=64)
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    default_route: Optional[str] = Field(default=None, max_length=255)
    sort_order: Optional[int] = Field(default=None, ge=0, le=100000)
    is_active: Optional[bool] = None

    @field_validator("code")
    @classmethod
    def normalise_code(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = "_".join(value.strip().upper().replace("-", "_").split())
        if not cleaned:
            raise ValueError("Department code is required.")
        return cleaned

    @field_validator("name")
    @classmethod
    def normalise_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Department name is required.")
        return cleaned


class DepartmentCatalogRead(BaseModel):
    id: str
    amo_id: str
    code: str
    name: str
    default_route: Optional[str] = None
    sort_order: int
    is_active: bool
    assigned_user_count: int = 0

    class Config:
        from_attributes = True
