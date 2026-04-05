from __future__ import annotations
from decimal import Decimal
from datetime import datetime, date as date_type
from typing import Optional
from pydantic import BaseModel, Field
from app.models.record import RecordType
from enum import Enum

class AggregationPeriod(str, Enum):
    month = "month"
    quarter = "quarter"
    year = "year"


# ── Request schemas ──

class RecordCreate(BaseModel):
    amount: Decimal = Field(..., gt=0)
    type: RecordType
    category: str = Field(..., min_length=1, max_length=100)
    date: date_type
    description: Optional[str] = None


class RecordUpdate(BaseModel):
    amount: Optional[Decimal] = Field(None, gt=0)
    type: Optional[RecordType] = None
    category: Optional[str] = Field(None, min_length=1, max_length=100)
    date: Optional[date_type] = None
    description: Optional[str] = None


# ── Response schemas ──

class RecordOut(BaseModel):
    id: int
    amount: Decimal
    type: RecordType
    category: str
    date: date_type
    description: Optional[str]
    created_by: int
    updated_by: Optional[int]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Dashboard schemas ──

class DashboardSummary(BaseModel):
    total_income: Decimal
    total_expense: Decimal
    net_balance: Decimal
    income_trend: float
    expense_trend: float
    balance_trend: float


class CategoryBreakdown(BaseModel):
    category: str
    total: Decimal


class TrendPoint(BaseModel):
    period: str
    income: Decimal
    expense: Decimal
