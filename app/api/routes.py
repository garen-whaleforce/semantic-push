"""FastAPI routes for the strategy engine API."""
import logging
import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Alert
from app.models.schemas import (
    AlertResponse,
    DailyJobResponse,
    HealthResponse,
    MarkSentResponse,
)
from app.services.fmp_client import FMPClient
from app.services.strategy_engine import StrategyEngine

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(ok=True)


@router.post("/jobs/daily", response_model=DailyJobResponse)
async def run_daily_job(
    as_of: Annotated[date, Query(description="Date to run the daily job for (YYYY-MM-DD)")],
    db: AsyncSession = Depends(get_db),
) -> DailyJobResponse:
    """
    Run the daily entry and exit scan.

    This endpoint is idempotent - running it multiple times for the same date
    will not create duplicate positions or alerts.
    """
    logger.info(f"API: Running daily job for {as_of}")

    fmp_client = FMPClient()
    try:
        engine = StrategyEngine(db, fmp_client)
        new_entries, new_exits = await engine.run_daily_job(as_of)

        return DailyJobResponse(
            as_of=as_of,
            new_entry_alerts=new_entries,
            new_exit_alerts=new_exits,
        )
    finally:
        await fmp_client.close()


@router.get("/alerts/pending", response_model=list[AlertResponse])
async def get_pending_alerts(
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    db: AsyncSession = Depends(get_db),
) -> list[AlertResponse]:
    """
    Get pending alerts that have not been sent yet.

    Returns alerts where sent_at is NULL, ordered by created_at ascending.
    """
    result = await db.execute(
        select(Alert)
        .where(Alert.sent_at.is_(None))
        .order_by(Alert.created_at.asc())
        .limit(limit)
    )
    alerts = result.scalars().all()

    return [
        AlertResponse(
            id=a.id,
            alert_type=a.alert_type,
            symbol=a.symbol,
            as_of=a.as_of,
            message=a.message,
        )
        for a in alerts
    ]


@router.post("/alerts/{alert_id}/mark-sent", response_model=MarkSentResponse)
async def mark_alert_sent(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> MarkSentResponse:
    """
    Mark an alert as sent.

    This endpoint is idempotent - calling it on an already-sent alert
    will return success with the existing sent_at timestamp.
    """
    # Get the alert
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()

    if alert is None:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    # If already sent, return success with existing timestamp
    if alert.sent_at is not None:
        return MarkSentResponse(
            success=True,
            id=alert.id,
            sent_at=alert.sent_at,
        )

    # Mark as sent
    now = datetime.utcnow()
    await db.execute(
        update(Alert).where(Alert.id == alert_id).values(sent_at=now)
    )
    await db.commit()

    return MarkSentResponse(
        success=True,
        id=alert.id,
        sent_at=now,
    )
