"""Shared SQLAlchemy metadata/declarative base and the Phase 1 bootstrap schema.

Phase 1 intentionally does not implement the industrial asset hierarchy (Phase 2). It
defines only a `system_metadata` key/value table, used to record platform bootstrap facts
(e.g. when the schema was first initialized, which extensions are present) that later
health/ops tooling can read without depending on any domain table existing yet.

A consistent naming convention is set for constraints/indexes so Alembic autogenerate
produces stable, predictable migration names as the schema grows in later phases.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, MetaData, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    # column_0N_name (all columns, not just the first) — several tenant-scoped tables
    # have more than one UNIQUE constraint starting with tenant_id (the tenant_unique()
    # constraint plus a business uniqueness rule), which would otherwise collide.
    "uq": "uq_%(table_name)s_%(column_0N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    metadata = metadata


class SystemMetadata(Base):
    """Key/value store for platform bootstrap facts. Not a business/domain table."""

    __tablename__ = "system_metadata"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(String(1024), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
