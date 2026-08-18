"""Shared building blocks for tenant-scoped ORM models.

See TECHNICAL_DECISIONS.md (tenant-composite-foreign-key ADR) and
docs/ASSET_HIERARCHY.md for the full rationale. Summary: every tenant-owned table carries
`UNIQUE(tenant_id, id)` in addition to its primary key, so every parent/child relationship
can use a *composite* foreign key `(tenant_id, parent_id) -> parent(tenant_id, id)` instead
of a plain `parent_id -> parent(id)` foreign key. That makes it impossible at the database
level to create a child row whose parent belongs to a different tenant — cross-tenant
references fail an INSERT/UPDATE outright, not just an application-level check.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantScopedMixin:
    """`id` + `tenant_id` for every tenant-owned table.

    Every concrete model must also add `tenant_unique()` to its own `__table_args__` —
    it cannot be supplied here via `declared_attr` without fighting subclasses that need
    to append their *own* additional `__table_args__` (composite FKs, unique codes,
    indexes), so it is kept as an explicit, greppable one-liner at each call site instead.
    """

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False, index=True
    )


def tenant_unique() -> UniqueConstraint:
    """The `UNIQUE(tenant_id, id)` every tenant-scoped table needs so children can hang a
    composite foreign key off it. Must be called fresh per table (a `UniqueConstraint`
    instance cannot be shared across tables)."""
    return UniqueConstraint("tenant_id", "id")


def composite_tenant_fk(
    fk_column: str,
    referred_table: str,
    *,
    nullable: bool = False,
    use_alter: bool = False,
) -> ForeignKeyConstraint:
    """A `(tenant_id, fk_column) -> referred_table(tenant_id, id)` composite foreign key.

    `nullable` only documents intent at the call site (whether `fk_column` itself is
    nullable is controlled by the column definition) — Postgres allows a composite FK to
    reference NULLs in any column of the FK by simply not checking that row (MATCH SIMPLE,
    the default), so a nullable `fk_column` composite FK behaves exactly like a nullable
    plain FK: NULL is allowed, any non-NULL value must resolve to a same-tenant parent.

    `use_alter=True` emits this constraint as a separate `ALTER TABLE ... ADD CONSTRAINT`
    after every table is created, instead of inline in `CREATE TABLE`. Required for the
    LubricationSystem <-> Reservoir/Pump/Controller relationship, which is a genuine
    creation-order cycle (each side has a FK to the other) — see
    docs/ASSET_HIERARCHY.md and the LubricationSystem model for the specific columns.
    """
    del nullable  # documentation-only, see docstring
    name = f"fk_{referred_table}_via_{fk_column}" if use_alter else None
    return ForeignKeyConstraint(
        ["tenant_id", fk_column],
        [f"{referred_table}.tenant_id", f"{referred_table}.id"],
        use_alter=use_alter,
        name=name,
    )
