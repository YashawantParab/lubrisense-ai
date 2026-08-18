"""Initial schema: required extensions and system_metadata bootstrap table.

Revision ID: 0001
Revises:
Create Date: 2026-08-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # TimescaleDB and pgvector must both be present in the target Postgres image.
    # See TECHNICAL_DECISIONS.md ADR-014 for the chosen local image and why both
    # extensions coexist cleanly in it.
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "system_metadata",
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("value", sa.String(length=1024), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_system_metadata")),
    )


def downgrade() -> None:
    op.drop_table("system_metadata")
    # Extensions are intentionally not dropped on downgrade: dropping timescaledb/vector
    # can be destructive to unrelated data and is out of scope for a schema rollback.
