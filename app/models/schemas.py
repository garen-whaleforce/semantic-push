"""Pydantic schemas for API request/response models."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Health check response."""

    ok: bool


class DailyJobRequest(BaseModel):
    """Request for daily job execution."""

    as_of: date


class DailyJobResponse(BaseModel):
    """Response from daily job execution."""

    as_of: date
    new_entry_alerts: int
    new_exit_alerts: int


class AlertResponse(BaseModel):
    """Alert response for n8n."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    alert_type: str
    symbol: str
    as_of: date
    message: str


class MarkSentResponse(BaseModel):
    """Response for marking alert as sent."""

    success: bool
    id: uuid.UUID
    sent_at: Optional[datetime] = None


class PositionResponse(BaseModel):
    """Position response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    symbol: str
    entry_date: date
    entry_price: Decimal
    status: str
    exit_date: Optional[date] = None
    exit_price: Optional[Decimal] = None
    exit_reason: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response."""

    detail: str
