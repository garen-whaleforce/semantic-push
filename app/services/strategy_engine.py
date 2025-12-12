"""Strategy engine for entry/exit signal generation."""
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Alert, AlertType, ExitReason, Position, PositionStatus, SymbolsCache
from app.services.fmp_client import FMPClient

logger = logging.getLogger(__name__)

# Strategy constants
ENTRY_RETURN_MIN = Decimal("-0.30")  # -30%
ENTRY_RETURN_MAX = Decimal("-0.05")  # -5%
STOP_LOSS_THRESHOLD = Decimal("-0.10")  # -10%
MAX_HOLDING_DAYS = 50


class StrategyEngine:
    """Strategy engine for processing entry and exit signals."""

    def __init__(self, db: AsyncSession, fmp_client: FMPClient) -> None:
        self.db = db
        self.fmp = fmp_client

    async def get_sp500_symbols(self) -> list[str]:
        """
        Get S&P500 symbols, using cache if available.
        Cache is stored in DB to persist across restarts.
        """
        from app.core.config import get_settings

        settings = get_settings()
        cache_ttl = timedelta(hours=settings.sp500_cache_ttl_hours)

        # Check cache
        result = await self.db.execute(select(SymbolsCache))
        cached = result.scalars().all()

        if cached:
            # Check if cache is still valid
            oldest = min(c.updated_at for c in cached)
            if datetime.now(oldest.tzinfo) - oldest < cache_ttl:
                logger.info(f"Using cached SP500 symbols ({len(cached)} symbols)")
                return [c.symbol for c in cached]

        # Fetch fresh data
        logger.info("Fetching fresh SP500 symbols from FMP")
        symbols = await self.fmp.get_sp500_constituents()

        if not symbols:
            # If fetch fails, use existing cache if available
            if cached:
                logger.warning("FMP fetch failed, using stale cache")
                return [c.symbol for c in cached]
            return []

        # Update cache - delete old and insert new
        await self.db.execute(SymbolsCache.__table__.delete())

        for symbol in symbols:
            stmt = insert(SymbolsCache).values(
                symbol=symbol,
                updated_at=datetime.utcnow(),
            )
            await self.db.execute(stmt)

        await self.db.commit()
        logger.info(f"Cached {len(symbols)} SP500 symbols")
        return symbols

    def _generate_entry_event_key(self, symbol: str, entry_date: date) -> str:
        """Generate unique event key for entry alert."""
        return f"ENTRY|{symbol}|{entry_date.isoformat()}"

    def _generate_exit_event_key(
        self, symbol: str, entry_date: date, exit_date: date, exit_reason: str
    ) -> str:
        """Generate unique event key for exit alert."""
        return f"EXIT|{symbol}|{entry_date.isoformat()}|{exit_date.isoformat()}|{exit_reason}"

    def _format_entry_message(
        self, symbol: str, as_of: date, earnings_return: Decimal, entry_price: Decimal
    ) -> str:
        """Format entry alert message for LINE notification."""
        return (
            f"[ENTRY] {symbol} {as_of.isoformat()}\n"
            f"Earnings day return: {earnings_return * 100:.2f}%\n"
            f"Entry price (close): {entry_price:.2f}"
        )

    def _format_exit_message(
        self,
        symbol: str,
        exit_date: date,
        exit_reason: str,
        pnl: Decimal,
        exit_price: Decimal,
        holding_days: int,
    ) -> str:
        """Format exit alert message for LINE notification."""
        reason_label = "STOP_LOSS" if exit_reason == ExitReason.STOP_LOSS.value else "TIME_EXIT"
        return (
            f"[EXIT-{reason_label}] {symbol} {exit_date.isoformat()}\n"
            f"PnL: {pnl * 100:.2f}%\n"
            f"Exit price (close): {exit_price:.2f}\n"
            f"Holding days: {holding_days}"
        )

    async def scan_entries(self, as_of: date) -> int:
        """
        Scan for entry signals on the given date.

        Entry conditions:
        1. Symbol is in S&P500
        2. Symbol has earnings on as_of date
        3. Earnings day return is between -30% and -5%

        Returns number of new entry alerts created.
        """
        logger.info(f"Scanning entries for {as_of}")
        new_alerts = 0

        # Get SP500 symbols
        sp500_symbols = set(await self.get_sp500_symbols())
        if not sp500_symbols:
            logger.warning("No SP500 symbols available")
            return 0

        # Get earnings calendar for as_of
        earnings_symbols = await self.fmp.get_earnings_calendar(as_of)
        logger.info(f"Found {len(earnings_symbols)} symbols with earnings on {as_of}")

        # Filter to SP500 only
        candidates = [s for s in earnings_symbols if s in sp500_symbols]
        logger.info(f"Filtered to {len(candidates)} SP500 symbols with earnings")

        for symbol in candidates:
            try:
                # Get price data
                price_data = await self.fmp.get_price_data_for_date(symbol, as_of)
                if price_data is None:
                    logger.debug(f"{symbol}: No price data for {as_of}, skipping")
                    continue

                as_of_close, prev_close = price_data

                # Calculate earnings day return
                earnings_return = as_of_close / prev_close - 1

                # Check entry condition
                if not (ENTRY_RETURN_MIN <= earnings_return <= ENTRY_RETURN_MAX):
                    logger.debug(
                        f"{symbol}: Earnings return {earnings_return:.2%} outside range, skipping"
                    )
                    continue

                logger.info(
                    f"{symbol}: Entry signal - earnings return {earnings_return:.2%}, "
                    f"entry price {as_of_close}"
                )

                # Create position (if not exists)
                position_stmt = insert(Position).values(
                    symbol=symbol,
                    entry_date=as_of,
                    entry_price=as_of_close,
                    status=PositionStatus.OPEN.value,
                )
                position_stmt = position_stmt.on_conflict_do_nothing(
                    index_elements=["symbol", "entry_date"]
                )
                await self.db.execute(position_stmt)

                # Create alert (if not exists)
                event_key = self._generate_entry_event_key(symbol, as_of)
                message = self._format_entry_message(
                    symbol, as_of, earnings_return, as_of_close
                )

                alert_stmt = insert(Alert).values(
                    event_key=event_key,
                    alert_type=AlertType.ENTRY.value,
                    symbol=symbol,
                    as_of=as_of,
                    message=message,
                )
                alert_stmt = alert_stmt.on_conflict_do_nothing(index_elements=["event_key"])
                result = await self.db.execute(alert_stmt)

                if result.rowcount > 0:
                    new_alerts += 1

            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
                continue

        await self.db.commit()
        logger.info(f"Entry scan complete: {new_alerts} new alerts")
        return new_alerts

    async def scan_exits(self, as_of: date) -> int:
        """
        Scan for exit signals on all open positions.

        Exit conditions:
        1. PnL <= -10% (stop loss)
        2. Holding days >= 50 (time exit)

        Returns number of new exit alerts created.
        """
        logger.info(f"Scanning exits for {as_of}")
        new_alerts = 0

        # Get all open positions
        result = await self.db.execute(
            select(Position).where(Position.status == PositionStatus.OPEN.value)
        )
        open_positions = result.scalars().all()
        logger.info(f"Found {len(open_positions)} open positions")

        for position in open_positions:
            try:
                # Get current close price
                close_price = await self.fmp.get_close_price(position.symbol, as_of)
                if close_price is None:
                    logger.debug(
                        f"{position.symbol}: No price data for {as_of}, skipping exit check"
                    )
                    continue

                # Calculate metrics
                holding_days = (as_of - position.entry_date).days
                pnl = close_price / position.entry_price - 1

                exit_reason: Optional[str] = None

                # Check exit conditions
                if pnl <= STOP_LOSS_THRESHOLD:
                    exit_reason = ExitReason.STOP_LOSS.value
                    logger.info(
                        f"{position.symbol}: Stop loss triggered - PnL {pnl:.2%}"
                    )
                elif holding_days >= MAX_HOLDING_DAYS:
                    exit_reason = ExitReason.TIME_EXIT.value
                    logger.info(
                        f"{position.symbol}: Time exit - {holding_days} days held"
                    )

                if exit_reason is None:
                    continue

                # Update position
                await self.db.execute(
                    update(Position)
                    .where(Position.id == position.id)
                    .values(
                        status=PositionStatus.CLOSED.value,
                        exit_date=as_of,
                        exit_price=close_price,
                        exit_reason=exit_reason,
                    )
                )

                # Create alert (if not exists)
                event_key = self._generate_exit_event_key(
                    position.symbol, position.entry_date, as_of, exit_reason
                )
                message = self._format_exit_message(
                    position.symbol,
                    as_of,
                    exit_reason,
                    pnl,
                    close_price,
                    holding_days,
                )

                alert_stmt = insert(Alert).values(
                    event_key=event_key,
                    alert_type=AlertType.EXIT.value,
                    symbol=position.symbol,
                    as_of=as_of,
                    message=message,
                )
                alert_stmt = alert_stmt.on_conflict_do_nothing(index_elements=["event_key"])
                result = await self.db.execute(alert_stmt)

                if result.rowcount > 0:
                    new_alerts += 1

            except Exception as e:
                logger.error(f"Error processing exit for {position.symbol}: {e}")
                continue

        await self.db.commit()
        logger.info(f"Exit scan complete: {new_alerts} new alerts")
        return new_alerts

    async def run_daily_job(self, as_of: date) -> tuple[int, int]:
        """
        Run the complete daily job: entry scan + exit scan.

        Returns tuple of (new_entry_alerts, new_exit_alerts).
        """
        logger.info(f"Running daily job for {as_of}")

        new_entries = await self.scan_entries(as_of)
        new_exits = await self.scan_exits(as_of)

        logger.info(
            f"Daily job complete: {new_entries} entries, {new_exits} exits"
        )
        return new_entries, new_exits
