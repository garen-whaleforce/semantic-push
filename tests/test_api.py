"""Tests for API endpoints."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Mock the settings before importing app
with patch.dict(
    "os.environ",
    {
        "FMP_API_KEY": "test_api_key",
        "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test",
    },
):
    from app.main import app


client = TestClient(app)


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_check(self):
        """Test that health endpoint returns ok."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"ok": True}


class TestDailyJobEndpoint:
    """Tests for daily job endpoint."""

    @patch("app.api.routes.FMPClient")
    @patch("app.api.routes.StrategyEngine")
    def test_daily_job_returns_correct_format(
        self, mock_engine_class: MagicMock, mock_fmp_class: MagicMock
    ):
        """Test that daily job returns expected response format."""
        # Setup mocks
        mock_fmp = MagicMock()
        mock_fmp.close = AsyncMock()
        mock_fmp_class.return_value = mock_fmp

        mock_engine = MagicMock()
        mock_engine.run_daily_job = AsyncMock(return_value=(2, 1))
        mock_engine_class.return_value = mock_engine

        response = client.post("/jobs/daily?asOf=2025-01-15")

        assert response.status_code == 200
        data = response.json()
        assert data["as_of"] == "2025-01-15"
        assert "new_entry_alerts" in data
        assert "new_exit_alerts" in data

    def test_daily_job_requires_as_of_param(self):
        """Test that daily job requires asOf parameter."""
        response = client.post("/jobs/daily")
        assert response.status_code == 422  # Validation error

    def test_daily_job_validates_date_format(self):
        """Test that daily job validates date format."""
        response = client.post("/jobs/daily?asOf=invalid-date")
        assert response.status_code == 422


class TestPendingAlertsEndpoint:
    """Tests for pending alerts endpoint."""

    @patch("app.api.routes.get_db")
    def test_pending_alerts_returns_list(self, mock_get_db: MagicMock):
        """Test that pending alerts returns a list."""
        # Create mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        async def get_mock_db():
            yield mock_session

        mock_get_db.return_value = get_mock_db()

        response = client.get("/alerts/pending")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_pending_alerts_accepts_limit(self):
        """Test that pending alerts accepts limit parameter."""
        with patch("app.api.routes.get_db") as mock_get_db:
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute = AsyncMock(return_value=mock_result)

            async def get_mock_db():
                yield mock_session

            mock_get_db.return_value = get_mock_db()

            response = client.get("/alerts/pending?limit=50")
            assert response.status_code == 200

    def test_pending_alerts_limit_validation(self):
        """Test that limit has bounds."""
        # Limit too high
        response = client.get("/alerts/pending?limit=1000")
        assert response.status_code == 422

        # Limit too low
        response = client.get("/alerts/pending?limit=0")
        assert response.status_code == 422


class TestMarkSentEndpoint:
    """Tests for mark-sent endpoint."""

    def test_mark_sent_returns_404_for_missing_alert(self):
        """Test that mark-sent returns 404 for non-existent alert."""
        with patch("app.api.routes.get_db") as mock_get_db:
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result)

            async def get_mock_db():
                yield mock_session

            mock_get_db.return_value = get_mock_db()

            alert_id = uuid.uuid4()
            response = client.post(f"/alerts/{alert_id}/mark-sent")
            assert response.status_code == 404

    def test_mark_sent_validates_uuid_format(self):
        """Test that mark-sent validates UUID format."""
        response = client.post("/alerts/invalid-uuid/mark-sent")
        assert response.status_code == 422
