"""Tests for strategy engine logic."""
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import strategy constants
from app.services.strategy_engine import (
    ENTRY_RETURN_MAX,
    ENTRY_RETURN_MIN,
    MAX_HOLDING_DAYS,
    STOP_LOSS_THRESHOLD,
    StrategyEngine,
)


class TestEntryConditions:
    """Tests for entry signal conditions."""

    def test_entry_return_bounds(self):
        """Test that entry return bounds are correctly defined."""
        assert ENTRY_RETURN_MIN == Decimal("-0.30")  # -30%
        assert ENTRY_RETURN_MAX == Decimal("-0.05")  # -5%

    @pytest.mark.parametrize(
        "earnings_return,should_trigger",
        [
            (Decimal("-0.30"), True),   # Exactly at lower bound
            (Decimal("-0.05"), True),   # Exactly at upper bound
            (Decimal("-0.15"), True),   # Middle of range
            (Decimal("-0.10"), True),   # -10%
            (Decimal("-0.25"), True),   # -25%
            (Decimal("-0.31"), False),  # Below lower bound
            (Decimal("-0.04"), False),  # Above upper bound
            (Decimal("0.00"), False),   # No change
            (Decimal("0.10"), False),   # Positive return
            (Decimal("-0.50"), False),  # Too negative
        ],
    )
    def test_entry_condition_range(self, earnings_return: Decimal, should_trigger: bool):
        """Test entry condition for various earnings returns."""
        result = ENTRY_RETURN_MIN <= earnings_return <= ENTRY_RETURN_MAX
        assert result == should_trigger, (
            f"Earnings return {earnings_return} should "
            f"{'trigger' if should_trigger else 'not trigger'} entry"
        )

    def test_entry_price_calculation(self):
        """Test earnings day return calculation."""
        # Example: stock dropped from 100 to 88 (-12%)
        prev_close = Decimal("100.00")
        as_of_close = Decimal("88.00")
        earnings_return = as_of_close / prev_close - 1

        assert earnings_return == Decimal("-0.12")
        assert ENTRY_RETURN_MIN <= earnings_return <= ENTRY_RETURN_MAX


class TestExitConditions:
    """Tests for exit signal conditions."""

    def test_exit_thresholds(self):
        """Test that exit thresholds are correctly defined."""
        assert STOP_LOSS_THRESHOLD == Decimal("-0.10")  # -10%
        assert MAX_HOLDING_DAYS == 50

    @pytest.mark.parametrize(
        "pnl,should_stop_loss",
        [
            (Decimal("-0.10"), True),   # Exactly at threshold
            (Decimal("-0.11"), True),   # Below threshold
            (Decimal("-0.20"), True),   # Way below threshold
            (Decimal("-0.09"), False),  # Above threshold
            (Decimal("0.00"), False),   # Breakeven
            (Decimal("0.10"), False),   # Profit
        ],
    )
    def test_stop_loss_condition(self, pnl: Decimal, should_stop_loss: bool):
        """Test stop loss condition for various PnL values."""
        result = pnl <= STOP_LOSS_THRESHOLD
        assert result == should_stop_loss, (
            f"PnL {pnl} should {'trigger' if should_stop_loss else 'not trigger'} stop loss"
        )

    @pytest.mark.parametrize(
        "holding_days,should_time_exit",
        [
            (50, True),   # Exactly at threshold
            (51, True),   # Above threshold
            (100, True),  # Way above threshold
            (49, False),  # Below threshold
            (0, False),   # Day of entry
            (25, False),  # Half way
        ],
    )
    def test_time_exit_condition(self, holding_days: int, should_time_exit: bool):
        """Test time exit condition for various holding periods."""
        result = holding_days >= MAX_HOLDING_DAYS
        assert result == should_time_exit, (
            f"Holding days {holding_days} should "
            f"{'trigger' if should_time_exit else 'not trigger'} time exit"
        )

    def test_pnl_calculation(self):
        """Test PnL calculation."""
        entry_price = Decimal("100.00")
        exit_price = Decimal("90.00")
        pnl = exit_price / entry_price - 1

        assert pnl == Decimal("-0.10")
        assert pnl <= STOP_LOSS_THRESHOLD

    def test_holding_days_calculation(self):
        """Test holding days calculation (calendar days)."""
        entry_date = date(2025, 1, 1)
        as_of_date = date(2025, 2, 20)
        holding_days = (as_of_date - entry_date).days

        assert holding_days == 50
        assert holding_days >= MAX_HOLDING_DAYS


class TestEventKeyIdempotency:
    """Tests for event key generation and idempotency."""

    def test_entry_event_key_format(self):
        """Test entry event key format."""
        symbol = "AAPL"
        entry_date = date(2025, 12, 1)
        expected = "ENTRY|AAPL|2025-12-01"

        # Simulate the key generation
        key = f"ENTRY|{symbol}|{entry_date.isoformat()}"
        assert key == expected

    def test_exit_event_key_format(self):
        """Test exit event key format."""
        symbol = "AAPL"
        entry_date = date(2025, 12, 1)
        exit_date = date(2025, 12, 20)
        exit_reason = "STOP_LOSS"
        expected = "EXIT|AAPL|2025-12-01|2025-12-20|STOP_LOSS"

        # Simulate the key generation
        key = f"EXIT|{symbol}|{entry_date.isoformat()}|{exit_date.isoformat()}|{exit_reason}"
        assert key == expected

    def test_entry_event_key_uniqueness(self):
        """Test that different entries produce different keys."""
        key1 = "ENTRY|AAPL|2025-12-01"
        key2 = "ENTRY|AAPL|2025-12-02"
        key3 = "ENTRY|MSFT|2025-12-01"

        assert key1 != key2  # Different dates
        assert key1 != key3  # Different symbols
        assert key2 != key3  # Both different

    def test_exit_event_key_uniqueness(self):
        """Test that different exits produce different keys."""
        key1 = "EXIT|AAPL|2025-12-01|2025-12-20|STOP_LOSS"
        key2 = "EXIT|AAPL|2025-12-01|2025-12-20|TIME_EXIT"
        key3 = "EXIT|AAPL|2025-12-01|2025-12-21|STOP_LOSS"

        assert key1 != key2  # Different exit reasons
        assert key1 != key3  # Different exit dates

    def test_same_entry_produces_same_key(self):
        """Test that identical entries produce the same key (idempotency)."""
        symbol = "AAPL"
        entry_date = date(2025, 12, 1)

        key1 = f"ENTRY|{symbol}|{entry_date.isoformat()}"
        key2 = f"ENTRY|{symbol}|{entry_date.isoformat()}"

        assert key1 == key2


class TestMessageFormatting:
    """Tests for alert message formatting."""

    def test_entry_message_format(self):
        """Test entry alert message format."""
        symbol = "AAPL"
        as_of = date(2025, 12, 1)
        earnings_return = Decimal("-0.1234")
        entry_price = Decimal("123.45")

        message = (
            f"[ENTRY] {symbol} {as_of.isoformat()}\n"
            f"Earnings day return: {earnings_return * 100:.2f}%\n"
            f"Entry price (close): {entry_price:.2f}"
        )

        expected = (
            "[ENTRY] AAPL 2025-12-01\n"
            "Earnings day return: -12.34%\n"
            "Entry price (close): 123.45"
        )
        assert message == expected

    def test_exit_stop_loss_message_format(self):
        """Test exit (stop loss) alert message format."""
        symbol = "AAPL"
        exit_date = date(2025, 12, 20)
        exit_reason = "STOP_LOSS"
        pnl = Decimal("-0.1012")
        exit_price = Decimal("111.11")
        holding_days = 19

        reason_label = "STOP_LOSS" if exit_reason == "STOP_LOSS" else "TIME_EXIT"
        message = (
            f"[EXIT-{reason_label}] {symbol} {exit_date.isoformat()}\n"
            f"PnL: {pnl * 100:.2f}%\n"
            f"Exit price (close): {exit_price:.2f}\n"
            f"Holding days: {holding_days}"
        )

        expected = (
            "[EXIT-STOP_LOSS] AAPL 2025-12-20\n"
            "PnL: -10.12%\n"
            "Exit price (close): 111.11\n"
            "Holding days: 19"
        )
        assert message == expected

    def test_exit_time_exit_message_format(self):
        """Test exit (time exit) alert message format."""
        symbol = "MSFT"
        exit_date = date(2025, 2, 20)
        exit_reason = "TIME_EXIT"
        pnl = Decimal("0.05")
        exit_price = Decimal("315.00")
        holding_days = 50

        reason_label = "STOP_LOSS" if exit_reason == "STOP_LOSS" else "TIME_EXIT"
        message = (
            f"[EXIT-{reason_label}] {symbol} {exit_date.isoformat()}\n"
            f"PnL: {pnl * 100:.2f}%\n"
            f"Exit price (close): {exit_price:.2f}\n"
            f"Holding days: {holding_days}"
        )

        expected = (
            "[EXIT-TIME_EXIT] MSFT 2025-02-20\n"
            "PnL: 5.00%\n"
            "Exit price (close): 315.00\n"
            "Holding days: 50"
        )
        assert message == expected
