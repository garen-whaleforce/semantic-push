"""Pytest configuration and fixtures."""
import os
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Set test environment variables before importing app modules
os.environ["FMP_API_KEY"] = "test_api_key"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost:5432/test"

from app.db.database import Base
from app.db.models import Alert, AlertType, Position, PositionStatus
from app.services.fmp_client import FMPClient


@pytest.fixture
def mock_fmp_client() -> MagicMock:
    """Create a mock FMP client."""
    client = MagicMock(spec=FMPClient)
    client.get_sp500_constituents = AsyncMock(return_value=["AAPL", "MSFT", "GOOGL", "AMZN"])
    client.get_earnings_calendar = AsyncMock(return_value=[])
    client.get_price_data_for_date = AsyncMock(return_value=None)
    client.get_close_price = AsyncMock(return_value=None)
    client.close = AsyncMock()
    return client


@pytest.fixture
def sample_position() -> dict:
    """Sample position data."""
    return {
        "id": uuid.uuid4(),
        "symbol": "AAPL",
        "entry_date": date(2025, 1, 15),
        "entry_price": Decimal("150.00"),
        "status": PositionStatus.OPEN.value,
    }


@pytest.fixture
def sample_alert() -> dict:
    """Sample alert data."""
    return {
        "id": uuid.uuid4(),
        "event_key": "ENTRY|AAPL|2025-01-15",
        "alert_type": AlertType.ENTRY.value,
        "symbol": "AAPL",
        "as_of": date(2025, 1, 15),
        "message": "[ENTRY] AAPL 2025-01-15\nEarnings day return: -12.34%\nEntry price (close): 150.00",
    }
