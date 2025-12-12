"""Initial schema with positions, alerts, and symbols_cache tables.

Revision ID: 001_initial_schema
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create positions table
    op.create_table(
        "positions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("entry_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("exit_date", sa.Date(), nullable=True),
        sa.Column("exit_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("exit_reason", sa.String(20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "entry_date", name="uq_positions_symbol_entry_date"),
    )
    op.create_index("ix_positions_symbol", "positions", ["symbol"])
    op.create_index("ix_positions_status", "positions", ["status"])

    # Create alerts table
    op.create_table(
        "alerts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_key", sa.Text(), nullable=False),
        sa.Column("alert_type", sa.String(20), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key", name="uq_alerts_event_key"),
    )
    op.create_index("ix_alerts_symbol", "alerts", ["symbol"])
    op.create_index("ix_alerts_sent_at", "alerts", ["sent_at"])

    # Create symbols_cache table
    op.create_table(
        "symbols_cache",
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("symbol"),
    )


def downgrade() -> None:
    op.drop_table("symbols_cache")
    op.drop_index("ix_alerts_sent_at", table_name="alerts")
    op.drop_index("ix_alerts_symbol", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("ix_positions_status", table_name="positions")
    op.drop_index("ix_positions_symbol", table_name="positions")
    op.drop_table("positions")
