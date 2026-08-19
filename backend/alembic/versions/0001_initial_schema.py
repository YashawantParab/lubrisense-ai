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
    # TimescaleDB and pgvector are both present in the reference local/CI Postgres image
    # (TECHNICAL_DECISIONS.md ADR-014) and are created unconditionally there. A standard
    # hosted PostgreSQL target (e.g. a managed Render/Supabase/RDS instance prepared for
    # the public hosted demo — see docs/HOSTED_DEPLOYMENT.md) commonly ships pgvector but
    # not TimescaleDB, whose shared library must be installed at the server level before
    # `CREATE EXTENSION` can succeed at all — attempting it unconditionally would abort
    # this migration outright on such a target. `pg_available_extensions` lists what the
    # server has the library for, regardless of tenant/schema, so checking it first lets
    # this migration degrade to a standard (non-hypertable) `telemetry` table on hosted
    # Postgres without changing anything about the reference TimescaleDB-backed path (see
    # ADR-175 in TECHNICAL_DECISIONS.md).
    timescaledb_available = bool(
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb'"))
        .scalar()
    )
    if timescaledb_available:
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
