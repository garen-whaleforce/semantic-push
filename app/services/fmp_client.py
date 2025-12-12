"""FMP (Financial Modeling Prep) API client with retry logic."""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Optional, Union

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class FMPClientError(Exception):
    """Base exception for FMP client errors."""

    pass


class FMPRateLimitError(FMPClientError):
    """Rate limit exceeded."""

    pass


class FMPClient:
    """Client for FMP API with retry and backoff."""

    def __init__(self) -> None:
        self.settings = get_settings()
        # Use stable API base URL
        self.base_url = "https://financialmodelingprep.com/stable"
        self.api_key = self.settings.fmp_api_key
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _request(self, endpoint: str, params: Optional[dict] = None) -> Union[dict, list]:
        """Make a request to FMP API with retry logic."""
        client = await self._get_client()
        params = params or {}
        params["apikey"] = self.api_key

        url = f"{self.base_url}/{endpoint}"
        logger.debug(f"FMP request: {url}")

        response = await client.get(url, params=params)

        # Check for rate limit
        if response.status_code == 429:
            raise FMPRateLimitError("FMP API rate limit exceeded")

        response.raise_for_status()
        return response.json()

    async def get_sp500_constituents(self) -> list[str]:
        """Get list of S&P500 constituent symbols."""
        # Use stable endpoint: /stable/sp500-constituent
        data = await self._request("sp500-constituent")
        if not isinstance(data, list):
            logger.warning("Unexpected SP500 response format")
            return []
        return [item.get("symbol") for item in data if item.get("symbol")]

    async def get_earnings_calendar(self, as_of: date) -> list[str]:
        """
        Get symbols with earnings on a specific date.

        Returns list of symbols that have earnings announcement on as_of date.
        """
        date_str = as_of.strftime("%Y-%m-%d")
        # Use stable endpoint: /stable/earnings-calendar
        data = await self._request(
            "earnings-calendar",
            params={"from": date_str, "to": date_str},
        )

        if not isinstance(data, list):
            logger.warning("Unexpected earnings calendar response format")
            return []

        # Extract symbols with earnings on this date
        symbols = []
        for item in data:
            symbol = item.get("symbol")
            if symbol:
                symbols.append(symbol)

        return symbols

    async def get_historical_prices(
        self, symbol: str, timeseries: int = 20
    ) -> list[dict]:
        """
        Get historical daily prices for a symbol.

        Returns list of price data sorted by date (newest first).
        Each item has: date, open, high, low, close, volume, etc.
        """
        # Use stable endpoint: /stable/historical-price-eod/full
        data = await self._request(
            f"historical-price-eod/full",
            params={"symbol": symbol},
        )

        if not isinstance(data, list):
            logger.warning(f"Unexpected historical price response format for {symbol}")
            return []

        # Return only the requested number of records (newest first)
        return data[:timeseries]

    async def get_price_data_for_date(
        self, symbol: str, as_of: date
    ) -> Optional[tuple[Decimal, Decimal]]:
        """
        Get close price for as_of date and previous trading day.

        Returns:
            Tuple of (as_of_close, prev_trading_day_close) if found,
            None if as_of is not a trading day or data not available.
        """
        historical = await self.get_historical_prices(symbol, timeseries=20)

        if not historical:
            return None

        as_of_str = as_of.strftime("%Y-%m-%d")

        # Find as_of date in the list
        as_of_idx = None
        for i, item in enumerate(historical):
            if item.get("date") == as_of_str:
                as_of_idx = i
                break

        if as_of_idx is None:
            # as_of date not found - not a trading day or data not updated
            logger.debug(f"{symbol}: {as_of_str} not found in historical data")
            return None

        # Previous trading day is the next item in the list (data is sorted newest first)
        if as_of_idx + 1 >= len(historical):
            logger.debug(f"{symbol}: No previous trading day data available")
            return None

        as_of_close = historical[as_of_idx].get("close")
        prev_close = historical[as_of_idx + 1].get("close")

        if as_of_close is None or prev_close is None:
            logger.debug(f"{symbol}: Missing close price data")
            return None

        return Decimal(str(as_of_close)), Decimal(str(prev_close))

    async def get_close_price(self, symbol: str, as_of: date) -> Optional[Decimal]:
        """Get closing price for a symbol on a specific date."""
        historical = await self.get_historical_prices(symbol, timeseries=20)

        if not historical:
            return None

        as_of_str = as_of.strftime("%Y-%m-%d")

        for item in historical:
            if item.get("date") == as_of_str:
                close = item.get("close")
                if close is not None:
                    return Decimal(str(close))
                break

        return None
