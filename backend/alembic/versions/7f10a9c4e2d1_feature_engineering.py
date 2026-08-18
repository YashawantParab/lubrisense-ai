"""feature engineering

Revision ID: 7f10a9c4e2d1
Revises: 615a5631e98e
Create Date: 2026-08-18 14:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "7f10a9c4e2d1"
down_revision: str | None = "615a5631e98e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feature_vector",
        sa.Column("machine_id", sa.Uuid(), nullable=False),
        sa.Column("component_id", sa.Uuid(), nullable=True),
        sa.Column("entity_key", sa.String(length=100), nullable=False),
        sa.Column("feature_set", sa.String(length=80), nullable=False),
        sa.Column("feature_set_version", sa.String(length=20), nullable=False),
        sa.Column("as_of_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_values", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("missing_features", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("quality_summary", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("source_window", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("baseline_versions", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("rule_versions", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column(
            "feature_definition_versions", postgresql.JSONB(), server_default="{}", nullable=False
        ),
        sa.Column("feature_policy_version", sa.String(length=20), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "machine_id"],
            ["machine.tenant_id", "machine.id"],
            name=op.f("fk_feature_vector_tenant_idmachine_id_machine"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_feature_vector_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feature_vector")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_feature_vector_tenant_idid")),
        sa.UniqueConstraint(
            "tenant_id",
            "machine_id",
            "entity_key",
            "feature_set",
            "feature_set_version",
            "as_of_timestamp",
            name="uq_feature_vector_logical",
        ),
    )
    op.create_index(
        op.f("ix_feature_vector_as_of_timestamp"), "feature_vector", ["as_of_timestamp"]
    )
    op.create_index(op.f("ix_feature_vector_component_id"), "feature_vector", ["component_id"])
    op.create_index(op.f("ix_feature_vector_feature_set"), "feature_vector", ["feature_set"])
    op.create_index(op.f("ix_feature_vector_machine_id"), "feature_vector", ["machine_id"])
    op.create_index(op.f("ix_feature_vector_tenant_id"), "feature_vector", ["tenant_id"])
    op.create_index(
        "ix_feature_vector_tenant_machine_set_time",
        "feature_vector",
        ["tenant_id", "machine_id", "feature_set", sa.text("as_of_timestamp DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_feature_vector_tenant_machine_set_time", table_name="feature_vector")
    op.drop_index(op.f("ix_feature_vector_tenant_id"), table_name="feature_vector")
    op.drop_index(op.f("ix_feature_vector_machine_id"), table_name="feature_vector")
    op.drop_index(op.f("ix_feature_vector_feature_set"), table_name="feature_vector")
    op.drop_index(op.f("ix_feature_vector_component_id"), table_name="feature_vector")
    op.drop_index(op.f("ix_feature_vector_as_of_timestamp"), table_name="feature_vector")
    op.drop_table("feature_vector")
