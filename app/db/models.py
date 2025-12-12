"""SQLAlchemy database models."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class PositionStatus(str, Enum):
    """Position status enum."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"


class ExitReason(str, Enum):
    """Exit reason enum."""

    STOP_LOSS = "STOP_LOSS"
    TIME_EXIT = "TIME_EXIT"


class AlertType(str, Enum):
    """Alert type enum."""

    ENTRY = "ENTRY"
    EXIT = "EXIT"


class Position(Base):
    """Position model representing a trading position."""

    __tablename__ = "positions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=PositionStatus.OPEN.value,
    )
    exit_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    exit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    exit_reason: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("symbol", "entry_date", name="uq_positions_symbol_entry_date"),
        Index("ix_positions_status", "status"),
    )


class Alert(Base):
    """Alert model for notifications to be sent via n8n."""

    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    event_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    alert_type: Mapped[str] = mapped_column(String(20), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (Index("ix_alerts_sent_at", "sent_at"),)


class SymbolsCache(Base):
    """Cache for S&P500 symbols to avoid rate limiting."""

    __tablename__ = "symbols_cache"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
