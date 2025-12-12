"""Tests for FMP client."""
import os
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# Set environment before imports
os.environ["FMP_API_KEY"] = "test_api_key"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost:5432/test"

from app.services.fmp_client import FMPClient


class TestFMPClient:
    """Tests for FMP API client."""

    @pytest.fixture
    def fmp_client(self) -> FMPClient:
        """Create FMP client instance."""
        return FMPClient()

    @pytest.mark.asyncio
    async def test_get_sp500_constituents_parses_response(self, fmp_client: FMPClient):
        """Test SP500 constituents parsing."""
        mock_response = [
            {"symbol": "AAPL", "name": "Apple Inc."},
            {"symbol": "MSFT", "name": "Microsoft Corporation"},
            {"symbol": "GOOGL", "name": "Alphabet Inc."},
        ]

        with patch.object(fmp_client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            result = await fmp_client.get_sp500_constituents()

            assert result == ["AAPL", "MSFT", "GOOGL"]
            mock_request.assert_called_once_with("sp500_constituent")

    @pytest.mark.asyncio
    async def test_get_sp500_constituents_handles_empty_response(self, fmp_client: FMPClient):
        """Test handling of empty SP500 response."""
        with patch.object(fmp_client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = []
            result = await fmp_client.get_sp500_constituents()
            assert result == []

    @pytest.mark.asyncio
    async def test_get_earnings_calendar_parses_response(self, fmp_client: FMPClient):
        """Test earnings calendar parsing."""
        test_date = date(2025, 1, 15)
        mock_response = [
            {"symbol": "AAPL", "date": "2025-01-15"},
            {"symbol": "MSFT", "date": "2025-01-15"},
        ]

        with patch.object(fmp_client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            result = await fmp_client.get_earnings_calendar(test_date)

            assert result == ["AAPL", "MSFT"]
            mock_request.assert_called_once_with(
                "earning_calendar",
                params={"from": "2025-01-15", "to": "2025-01-15"},
            )

    @pytest.mark.asyncio
    async def test_get_historical_prices_parses_response(self, fmp_client: FMPClient):
        """Test historical prices parsing."""
        mock_response = {
            "symbol": "AAPL",
            "historical": [
                {"date": "2025-01-15", "close": 150.0},
                {"date": "2025-01-14", "close": 148.0},
            ],
        }

        with patch.object(fmp_client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            result = await fmp_client.get_historical_prices("AAPL", timeseries=20)

            assert len(result) == 2
            assert result[0]["date"] == "2025-01-15"
            assert result[0]["close"] == 150.0

    @pytest.mark.asyncio
    async def test_get_price_data_for_date_returns_tuple(self, fmp_client: FMPClient):
        """Test getting price data for specific date."""
        mock_historical = [
            {"date": "2025-01-15", "close": 150.0},
            {"date": "2025-01-14", "close": 148.0},
            {"date": "2025-01-13", "close": 147.0},
        ]

        with patch.object(
            fmp_client, "get_historical_prices", new_callable=AsyncMock
        ) as mock_prices:
            mock_prices.return_value = mock_historical
            result = await fmp_client.get_price_data_for_date("AAPL", date(2025, 1, 15))

            assert result is not None
            as_of_close, prev_close = result
            assert as_of_close == Decimal("150.0")
            assert prev_close == Decimal("148.0")

    @pytest.mark.asyncio
    async def test_get_price_data_for_date_returns_none_for_non_trading_day(
        self, fmp_client: FMPClient
    ):
        """Test that non-trading days return None."""
        mock_historical = [
            {"date": "2025-01-15", "close": 150.0},
            {"date": "2025-01-14", "close": 148.0},
        ]

        with patch.object(
            fmp_client, "get_historical_prices", new_callable=AsyncMock
        ) as mock_prices:
            mock_prices.return_value = mock_historical
            # Ask for a date not in the list (weekend)
            result = await fmp_client.get_price_data_for_date("AAPL", date(2025, 1, 18))

            assert result is None

    @pytest.mark.asyncio
    async def test_get_close_price_returns_decimal(self, fmp_client: FMPClient):
        """Test getting close price returns Decimal."""
        mock_historical = [
            {"date": "2025-01-15", "close": 150.0},
            {"date": "2025-01-14", "close": 148.0},
        ]

        with patch.object(
            fmp_client, "get_historical_prices", new_callable=AsyncMock
        ) as mock_prices:
            mock_prices.return_value = mock_historical
            result = await fmp_client.get_close_price("AAPL", date(2025, 1, 15))

            assert result == Decimal("150.0")

    @pytest.mark.asyncio
    async def test_client_close(self, fmp_client: FMPClient):
        """Test client close method."""
        # Create a client
        fmp_client._client = MagicMock()
        fmp_client._client.is_closed = False
        fmp_client._client.aclose = AsyncMock()

        await fmp_client.close()

        fmp_client._client.aclose.assert_called_once()
