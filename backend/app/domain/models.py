"""Industrial asset hierarchy — Phase 2 domain model.

Implements the hierarchy defined in docs/DOMAIN_MODEL.md §3 and the physical
lubrication-system chain in §2:

    Tenant -> CustomerAccount -> Site -> Plant -> ProductionLine -> Machine -> Bearing
    Machine -> LubricationSystem -> {Reservoir, Pump, Controller, Distributor}
    LubricationSystem -> Circuit -> LubricationPoint -> Bearing
    Sensor attaches to exactly one of: Machine, Bearing, LubricationSystem, Reservoir,
        Pump, Circuit
    Gateway attaches to exactly one of: Site, Plant

These ORM models double as the Phase 2 domain layer (see TECHNICAL_DECISIONS.md,
domain-vs-ORM-separation ADR) — there is no separate parallel dataclass domain layer.
API request/response shape lives in app/api/schemas/, never these classes directly.

Every tenant-owned table uses the composite-tenant-foreign-key pattern from
app.domain.mixins: cross-tenant parent/child references are rejected by the database
itself, not just application code. See docs/ASSET_HIERARCHY.md for the full rationale and
an ER diagram.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import (
    AssessmentScope,
    BaselineMetricKind,
    BaselineState,
    BaselineStrategyType,
    ClockStatus,
    CommercialStatus,
    CommissioningState,
    Criticality,
    Eligibility,
    EvidenceStrength,
    IssueSeverity,
    IssueStatus,
    LubricationSystemType,
    MachineStatus,
    MachineType,
    OperationalStatus,
    QualityDimension,
    QualityIssueType,
    QualityState,
    QuarantineReason,
    RuleCategory,
    RuleFindingSeverity,
    RuleFindingState,
    RuleFindingType,
    SensorStatus,
    SensorType,
    ServiceTier,
    StalenessStatus,
    TelemetryQuality,
    TenantStatus,
)
from app.domain.enums import (
    SensorQualityState as SensorQualityStateEnum,
)
from app.domain.mixins import TenantScopedMixin, TimestampMixin, composite_tenant_fk, tenant_unique
from app.infrastructure.db_metadata import Base


def _enum_column(enum_cls: type, *, length: int = 32) -> SAEnum:
    """`native_enum=False` -> VARCHAR + CHECK constraint, not a Postgres native enum type.
    See TECHNICAL_DECISIONS.md (enum strategy ADR) for why."""
    return SAEnum(enum_cls, native_enum=False, length=length, validate_strings=True)


# ---------------------------------------------------------------------------
# Tenant — the hard isolation boundary. Not itself tenant-scoped.
# ---------------------------------------------------------------------------


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenant"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    status: Mapped[TenantStatus] = mapped_column(
        _enum_column(TenantStatus), nullable=False, default=TenantStatus.ACTIVE
    )


# ---------------------------------------------------------------------------
# CustomerAccount
# ---------------------------------------------------------------------------


class CustomerAccount(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "customer_account"
    __table_args__ = (tenant_unique(), UniqueConstraint("tenant_id", "code"))

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    service_tier: Mapped[ServiceTier] = mapped_column(_enum_column(ServiceTier), nullable=False)
    commercial_status: Mapped[CommercialStatus] = mapped_column(
        _enum_column(CommercialStatus), nullable=False, default=CommercialStatus.PROSPECT
    )
    contract_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    sites: Mapped[list[Site]] = relationship(viewonly=True, back_populates="customer_account")


# ---------------------------------------------------------------------------
# Site
# ---------------------------------------------------------------------------


class Site(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "site"
    __table_args__ = (
        tenant_unique(),
        UniqueConstraint("tenant_id", "code"),
        composite_tenant_fk("customer_account_id", "customer_account"),
    )

    customer_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[OperationalStatus] = mapped_column(
        _enum_column(OperationalStatus), nullable=False, default=OperationalStatus.ACTIVE
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    customer_account: Mapped[CustomerAccount] = relationship(viewonly=True, back_populates="sites")
    plants: Mapped[list[Plant]] = relationship(viewonly=True, back_populates="site")
    gateways: Mapped[list[Gateway]] = relationship(viewonly=True, back_populates="site")


# ---------------------------------------------------------------------------
# Plant
# ---------------------------------------------------------------------------


class Plant(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "plant"
    __table_args__ = (
        tenant_unique(),
        UniqueConstraint("tenant_id", "code"),
        composite_tenant_fk("site_id", "site"),
    )

    site_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    plant_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[OperationalStatus] = mapped_column(
        _enum_column(OperationalStatus), nullable=False, default=OperationalStatus.ACTIVE
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    site: Mapped[Site] = relationship(viewonly=True, back_populates="plants")
    production_lines: Mapped[list[ProductionLine]] = relationship(
        viewonly=True, back_populates="plant"
    )
    gateways: Mapped[list[Gateway]] = relationship(viewonly=True, back_populates="plant")


# ---------------------------------------------------------------------------
# ProductionLine
# ---------------------------------------------------------------------------


class ProductionLine(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "production_line"
    __table_args__ = (
        tenant_unique(),
        UniqueConstraint("tenant_id", "plant_id", "code"),
        composite_tenant_fk("plant_id", "plant"),
    )

    plant_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[OperationalStatus] = mapped_column(
        _enum_column(OperationalStatus), nullable=False, default=OperationalStatus.ACTIVE
    )
    criticality: Mapped[Criticality] = mapped_column(
        _enum_column(Criticality), nullable=False, default=Criticality.MEDIUM
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    plant: Mapped[Plant] = relationship(viewonly=True, back_populates="production_lines")
    machines: Mapped[list[Machine]] = relationship(viewonly=True, back_populates="production_line")


# ---------------------------------------------------------------------------
# Machine
# ---------------------------------------------------------------------------


class Machine(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "machine"
    __table_args__ = (
        tenant_unique(),
        UniqueConstraint("tenant_id", "asset_code"),
        composite_tenant_fk("production_line_id", "production_line"),
    )

    production_line_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_code: Mapped[str] = mapped_column(String(50), nullable=False)
    machine_type: Mapped[MachineType] = mapped_column(_enum_column(MachineType), nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(150), nullable=True)
    model: Mapped[str | None] = mapped_column(String(150), nullable=True)
    serial_number_demo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    installation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    criticality: Mapped[Criticality] = mapped_column(
        _enum_column(Criticality), nullable=False, default=Criticality.MEDIUM
    )
    operating_profile: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    status: Mapped[MachineStatus] = mapped_column(
        _enum_column(MachineStatus), nullable=False, default=MachineStatus.REGISTERED
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    production_line: Mapped[ProductionLine] = relationship(viewonly=True, back_populates="machines")
    bearings: Mapped[list[Bearing]] = relationship(viewonly=True, back_populates="machine")
    lubrication_systems: Mapped[list[LubricationSystem]] = relationship(
        viewonly=True, back_populates="machine"
    )


# ---------------------------------------------------------------------------
# Bearing
# ---------------------------------------------------------------------------


class Bearing(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "bearing"
    __table_args__ = (
        tenant_unique(),
        UniqueConstraint("tenant_id", "machine_id", "position"),
        composite_tenant_fk("machine_id", "machine"),
    )

    machine_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[str] = mapped_column(String(100), nullable=False)
    bearing_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(150), nullable=True)
    model: Mapped[str | None] = mapped_column(String(150), nullable=True)
    criticality: Mapped[Criticality] = mapped_column(
        _enum_column(Criticality), nullable=False, default=Criticality.MEDIUM
    )
    installation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[OperationalStatus] = mapped_column(
        _enum_column(OperationalStatus), nullable=False, default=OperationalStatus.ACTIVE
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    machine: Mapped[Machine] = relationship(viewonly=True, back_populates="bearings")


# ---------------------------------------------------------------------------
# LubricationSystem + physical chain (Reservoir, Pump, Controller, Distributor, Circuit,
# LubricationPoint)
# ---------------------------------------------------------------------------


class LubricationSystem(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "lubrication_system"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("machine_id", "machine"),
        # use_alter=True: these three point at tables that themselves have a (required)
        # composite FK back to lubrication_system, a genuine creation-order cycle. Emitting
        # these as ALTER TABLE ... ADD CONSTRAINT after all tables exist breaks the cycle.
        # See docs/ASSET_HIERARCHY.md.
        composite_tenant_fk("reservoir_id", "reservoir", nullable=True, use_alter=True),
        composite_tenant_fk("pump_id", "pump", nullable=True, use_alter=True),
        composite_tenant_fk("controller_id", "controller", nullable=True, use_alter=True),
    )

    machine_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    system_type: Mapped[LubricationSystemType] = mapped_column(
        _enum_column(LubricationSystemType), nullable=False
    )
    # Nullable "primary equipment" references, populated after the child rows below are
    # created (see docs/ASSET_HIERARCHY.md — creation order note).
    reservoir_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    pump_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    controller_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    status: Mapped[OperationalStatus] = mapped_column(
        _enum_column(OperationalStatus), nullable=False, default=OperationalStatus.ACTIVE
    )
    commissioning_state: Mapped[CommissioningState] = mapped_column(
        _enum_column(CommissioningState), nullable=False, default=CommissioningState.PLANNED
    )
    configuration_version: Mapped[str] = mapped_column(String(50), nullable=False, default="v1")
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    machine: Mapped[Machine] = relationship(viewonly=True, back_populates="lubrication_systems")
    reservoirs: Mapped[list[Reservoir]] = relationship(
        viewonly=True,
        back_populates="lubrication_system",
        foreign_keys="Reservoir.lubrication_system_id",
    )
    pumps: Mapped[list[Pump]] = relationship(
        viewonly=True,
        back_populates="lubrication_system",
        foreign_keys="Pump.lubrication_system_id",
    )
    controllers: Mapped[list[Controller]] = relationship(
        viewonly=True,
        back_populates="lubrication_system",
        foreign_keys="Controller.lubrication_system_id",
    )
    distributors: Mapped[list[Distributor]] = relationship(
        viewonly=True, back_populates="lubrication_system"
    )
    circuits: Mapped[list[Circuit]] = relationship(
        viewonly=True, back_populates="lubrication_system"
    )


class Reservoir(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "reservoir"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("lubrication_system_id", "lubrication_system"),
    )

    lubrication_system_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    capacity_demo: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    capacity_unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    lubricant_type_demo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[OperationalStatus] = mapped_column(
        _enum_column(OperationalStatus), nullable=False, default=OperationalStatus.ACTIVE
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    lubrication_system: Mapped[LubricationSystem] = relationship(
        viewonly=True, back_populates="reservoirs", foreign_keys=[lubrication_system_id]
    )


class Pump(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "pump"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("lubrication_system_id", "lubrication_system"),
    )

    lubrication_system_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    pump_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(150), nullable=True)
    model: Mapped[str | None] = mapped_column(String(150), nullable=True)
    controller_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[OperationalStatus] = mapped_column(
        _enum_column(OperationalStatus), nullable=False, default=OperationalStatus.ACTIVE
    )
    firmware_version_demo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    lubrication_system: Mapped[LubricationSystem] = relationship(
        viewonly=True, back_populates="pumps", foreign_keys=[lubrication_system_id]
    )


class Controller(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "controller"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("lubrication_system_id", "lubrication_system"),
    )

    lubrication_system_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    controller_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(150), nullable=True)
    model: Mapped[str | None] = mapped_column(String(150), nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    configuration_version: Mapped[str] = mapped_column(String(50), nullable=False, default="v1")
    status: Mapped[OperationalStatus] = mapped_column(
        _enum_column(OperationalStatus), nullable=False, default=OperationalStatus.ACTIVE
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    lubrication_system: Mapped[LubricationSystem] = relationship(
        viewonly=True, back_populates="controllers", foreign_keys=[lubrication_system_id]
    )


class Distributor(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "distributor"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("lubrication_system_id", "lubrication_system"),
    )

    lubrication_system_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    position: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[OperationalStatus] = mapped_column(
        _enum_column(OperationalStatus), nullable=False, default=OperationalStatus.ACTIVE
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    lubrication_system: Mapped[LubricationSystem] = relationship(
        viewonly=True, back_populates="distributors"
    )
    circuits: Mapped[list[Circuit]] = relationship(viewonly=True, back_populates="distributor")


class Circuit(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "circuit"
    __table_args__ = (
        tenant_unique(),
        UniqueConstraint("tenant_id", "lubrication_system_id", "code"),
        composite_tenant_fk("lubrication_system_id", "lubrication_system"),
        composite_tenant_fk("distributor_id", "distributor", nullable=True),
    )

    lubrication_system_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    distributor_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[OperationalStatus] = mapped_column(
        _enum_column(OperationalStatus), nullable=False, default=OperationalStatus.ACTIVE
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    lubrication_system: Mapped[LubricationSystem] = relationship(
        viewonly=True, back_populates="circuits"
    )
    distributor: Mapped[Distributor | None] = relationship(viewonly=True, back_populates="circuits")
    lubrication_points: Mapped[list[LubricationPoint]] = relationship(
        viewonly=True, back_populates="circuit"
    )


class LubricationPoint(Base, TenantScopedMixin, TimestampMixin):
    """Connects the lubrication-delivery path (Circuit) to the served component
    (Bearing). See docs/ASSET_HIERARCHY.md for why this is the load-bearing relationship
    of the whole schema."""

    __tablename__ = "lubrication_point"
    __table_args__ = (
        tenant_unique(),
        UniqueConstraint("tenant_id", "circuit_id", "code"),
        composite_tenant_fk("circuit_id", "circuit"),
        composite_tenant_fk("bearing_id", "bearing", nullable=True),
    )

    circuit_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    bearing_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[OperationalStatus] = mapped_column(
        _enum_column(OperationalStatus), nullable=False, default=OperationalStatus.ACTIVE
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    circuit: Mapped[Circuit] = relationship(viewonly=True, back_populates="lubrication_points")
    bearing: Mapped[Bearing | None] = relationship(viewonly=True)


# ---------------------------------------------------------------------------
# Sensor
# ---------------------------------------------------------------------------

_SENSOR_ATTACHMENT_COLUMNS = (
    "machine_id",
    "bearing_id",
    "lubrication_system_id",
    "reservoir_id",
    "pump_id",
    "circuit_id",
)

_sensor_exactly_one_attachment_sql = " + ".join(
    f"(CASE WHEN {col} IS NOT NULL THEN 1 ELSE 0 END)" for col in _SENSOR_ATTACHMENT_COLUMNS
)


class Sensor(Base, TenantScopedMixin, TimestampMixin):
    """A sensor attaches to exactly one physical entity, modeled as one nullable
    composite foreign key per attachable entity type plus a CHECK constraint enforcing
    exactly one is set. See docs/ASSET_HIERARCHY.md (sensor attachment strategy) for why
    this was chosen over a generic polymorphic (entity_type, entity_id) association."""

    __tablename__ = "sensor"
    __table_args__ = (
        tenant_unique(),
        UniqueConstraint("tenant_id", "sensor_code"),
        composite_tenant_fk("machine_id", "machine", nullable=True),
        composite_tenant_fk("bearing_id", "bearing", nullable=True),
        composite_tenant_fk("lubrication_system_id", "lubrication_system", nullable=True),
        composite_tenant_fk("reservoir_id", "reservoir", nullable=True),
        composite_tenant_fk("pump_id", "pump", nullable=True),
        composite_tenant_fk("circuit_id", "circuit", nullable=True),
        CheckConstraint(f"{_sensor_exactly_one_attachment_sql} = 1", name="exactly_one_attachment"),
    )

    sensor_code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sensor_type: Mapped[SensorType] = mapped_column(_enum_column(SensorType), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    installation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    calibration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[SensorStatus] = mapped_column(
        _enum_column(SensorStatus), nullable=False, default=SensorStatus.ACTIVE
    )
    quality_state: Mapped[SensorQualityStateEnum] = mapped_column(
        _enum_column(SensorQualityStateEnum), nullable=False, default=SensorQualityStateEnum.UNKNOWN
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    machine_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    bearing_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    lubrication_system_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    reservoir_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    pump_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    circuit_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)

    machine: Mapped[Machine | None] = relationship(viewonly=True)
    bearing: Mapped[Bearing | None] = relationship(viewonly=True)
    lubrication_system: Mapped[LubricationSystem | None] = relationship(viewonly=True)
    reservoir: Mapped[Reservoir | None] = relationship(viewonly=True)
    pump: Mapped[Pump | None] = relationship(viewonly=True)
    circuit: Mapped[Circuit | None] = relationship(viewonly=True)

    @property
    def attached_entity_type(self) -> str:
        for column in _SENSOR_ATTACHMENT_COLUMNS:
            if getattr(self, column) is not None:
                return column.removesuffix("_id")
        raise ValueError("Sensor has no attachment set — violates ck_sensor_exactly_one_attachment")

    @property
    def attached_entity_id(self) -> uuid.UUID:
        for column in _SENSOR_ATTACHMENT_COLUMNS:
            value = getattr(self, column)
            if value is not None:
                return value  # type: ignore[no-any-return]
        raise ValueError("Sensor has no attachment set — violates ck_sensor_exactly_one_attachment")


# ---------------------------------------------------------------------------
# Gateway
# ---------------------------------------------------------------------------

_GATEWAY_ATTACHMENT_COLUMNS = ("site_id", "plant_id")
_gateway_exactly_one_attachment_sql = " + ".join(
    f"(CASE WHEN {col} IS NOT NULL THEN 1 ELSE 0 END)" for col in _GATEWAY_ATTACHMENT_COLUMNS
)


class Gateway(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "gateway"
    __table_args__ = (
        tenant_unique(),
        UniqueConstraint("tenant_id", "gateway_code"),
        composite_tenant_fk("site_id", "site", nullable=True),
        composite_tenant_fk("plant_id", "plant", nullable=True),
        CheckConstraint(
            f"{_gateway_exactly_one_attachment_sql} = 1", name="exactly_one_attachment"
        ),
    )

    site_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    plant_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    gateway_code: Mapped[str] = mapped_column(String(50), nullable=False)
    manufacturer_demo: Mapped[str | None] = mapped_column(String(150), nullable=True)
    model_demo: Mapped[str | None] = mapped_column(String(150), nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[OperationalStatus] = mapped_column(
        _enum_column(OperationalStatus), nullable=False, default=OperationalStatus.ACTIVE
    )
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    site: Mapped[Site | None] = relationship(viewonly=True, back_populates="gateways")
    plant: Mapped[Plant | None] = relationship(viewonly=True, back_populates="gateways")


# ---------------------------------------------------------------------------
# Telemetry — Phase 6 central pipeline persistence.
#
# A TimescaleDB hypertable partitioned on `source_timestamp` (event time — see
# TECHNICAL_DECISIONS.md ADR-054). The primary key is the composite
# `(event_id, source_timestamp)`, not `event_id` alone: TimescaleDB requires every
# unique/primary-key constraint on a hypertable to include the partitioning column.
# `event_id` deterministically implies `source_timestamp` already (both are fixed at edge
# acquisition time, never regenerated — see edge ADR-045), so this is a safe idempotency
# key, not a weakening of it (ADR-053). `event_id`/`sequence_number`/every timestamp are
# preserved exactly as emitted by the edge (docs/EDGE_ARCHITECTURE.md) — this table never
# mints or overwrites them.
#
# `gateway_id` mirrors the edge's own wire identity (edge.domain.envelope.
# ReadingEnvelope.gateway_id) verbatim as a string, not a foreign key to `gateway.id` — the
# edge (edge.acquisition.builder.EnvelopeBuilder) actually sends `Gateway.id` (a UUID) as
# this field's value, but the wire contract does not strictly type it as one, so it is
# stored as-is and validated at ingestion time (app.pipeline.enrichment, matching by
# `Gateway.id` first, falling back to `Gateway.gateway_code`) rather than DB-FK-enforced.
# `production_line_id` corresponds to the envelope's `line_id` field (renamed to match this
# schema's `production_line` table).
# ---------------------------------------------------------------------------


class Telemetry(Base):
    __tablename__ = "telemetry"
    __table_args__ = (
        PrimaryKeyConstraint("event_id", "source_timestamp", name="pk_telemetry"),
        composite_tenant_fk("sensor_id", "sensor"),
        composite_tenant_fk("machine_id", "machine", nullable=True),
        composite_tenant_fk("bearing_id", "bearing", nullable=True),
        composite_tenant_fk("lubrication_system_id", "lubrication_system", nullable=True),
        composite_tenant_fk("circuit_id", "circuit", nullable=True),
        composite_tenant_fk("lubrication_point_id", "lubrication_point", nullable=True),
        composite_tenant_fk("production_line_id", "production_line", nullable=True),
        composite_tenant_fk("plant_id", "plant", nullable=True),
        composite_tenant_fk("site_id", "site", nullable=True),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    schema_version: Mapped[str] = mapped_column(String(10), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    plant_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    production_line_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    machine_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    bearing_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    lubrication_system_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    circuit_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    lubrication_point_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    sensor_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)

    measurement_type: Mapped[SensorType] = mapped_column(_enum_column(SensorType), nullable=False)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    quality: Mapped[TelemetryQuality] = mapped_column(
        _enum_column(TelemetryQuality), nullable=False
    )
    operating_state: Mapped[str] = mapped_column(String(50), nullable=False)

    source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    edge_received_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    edge_emitted_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    mqtt_received_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    kafka_published_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consumer_received_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    persisted_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    gateway_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(100), nullable=False)
    firmware_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    controller_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="synthetic")
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    kafka_partition: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kafka_offset: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


# ---------------------------------------------------------------------------
# TelemetryQuarantine — malformed/rejected telemetry events (Phase 6 brief §20/§25).
#
# Deliberately carries *no* foreign keys on tenant_id/sensor_id: the whole reason a row
# lands here is that it may reference an unknown, cross-tenant, or otherwise invalid
# entity — an FK constraint would make exactly the rows this table exists to capture
# un-insertable. See TECHNICAL_DECISIONS.md ADR-057.
# ---------------------------------------------------------------------------


class TelemetryQuarantine(Base):
    __tablename__ = "telemetry_quarantine"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    reason: Mapped[QuarantineReason] = mapped_column(_enum_column(QuarantineReason), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)

    event_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    sensor_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    gateway_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    kafka_topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kafka_partition: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kafka_offset: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)

    quarantined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Phase 7 — Data Quality Engine.
#
# Three tables, a deliberate storage-strategy trade-off (TECHNICAL_DECISIONS.md,
# quality-storage-strategy ADR): a per-event `QualityAssessment` row for every trivial GOOD
# telemetry event would explode 1:1 with `telemetry` volume, so:
#   - `QualityIssue` rows exist only when something is actually detected (event- or
#     window-scoped).
#   - `SensorQualityState` is one continuously-upserted row per (tenant_id, sensor_id) —
#     bounded by sensor count, not event count — the always-current summary.
#   - `QualityAssessment` rows are persisted for window-level evaluations (inherently
#     low-frequency, one per sensor per policy window interval, regardless of outcome) and
#     for event-level evaluations that found at least one issue (linked to that issue).
# `machine_id` is denormalized onto all three from the telemetry envelope's own
# (edge-supplied, always-present) `machine_id` field — the quality worker does not need to
# repeat Phase 6's hierarchy-enrichment DB walk.
# ---------------------------------------------------------------------------


class QualityAssessment(Base, TenantScopedMixin):
    __tablename__ = "quality_assessment"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("sensor_id", "sensor"),
        composite_tenant_fk("machine_id", "machine", nullable=True),
    )

    scope: Mapped[AssessmentScope] = mapped_column(_enum_column(AssessmentScope), nullable=False)
    sensor_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    machine_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)

    event_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    quality_state: Mapped[QualityState] = mapped_column(_enum_column(QualityState), nullable=False)
    # Deliberately always NULL in v1 — a numeric score would create false precision beyond
    # what the categorical quality_state + explicit issue list can actually explain (brief
    # §26). Kept as a real nullable column so the contract in §5 is honored structurally,
    # not omitted outright. See TECHNICAL_DECISIONS.md, no-numeric-quality-score ADR.
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    policy_version: Mapped[str] = mapped_column(String(20), nullable=False)
    rule_versions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )


class QualityIssue(Base, TenantScopedMixin):
    __tablename__ = "quality_issue"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("sensor_id", "sensor"),
        composite_tenant_fk("machine_id", "machine", nullable=True),
        composite_tenant_fk("assessment_id", "quality_assessment"),
        # Idempotent-reprocessing keys (brief §31/§33), two different shapes for two
        # different lifecycles (TECHNICAL_DECISIONS.md, issue-lifecycle-scope ADR):
        #   - Event-scoped issues are immutable facts about one past event, always created
        #     directly as RESOLVED — plain uniqueness on event_id is exactly right, and a
        #     reprocessing re-run naturally no-ops via ON CONFLICT DO NOTHING.
        #   - Window-scoped issues represent an *ongoing* condition (staleness,
        #     communication loss, drift/stuck suspicion) that should update in place —
        #     one row per (sensor, rule) while ACTIVE/RECOVERING, not a new row every
        #     evaluation cycle — so uniqueness is a *partial* index scoped to those two
        #     statuses, not a plain constraint on the ever-changing window bounds. Once a
        #     window issue RESOLVED, the same rule can open a fresh row later (recurrence).
        UniqueConstraint(
            "tenant_id",
            "sensor_id",
            "rule_id",
            "rule_version",
            "event_id",
            name="uq_quality_issue_event_scope",
        ),
        Index(
            "uq_quality_issue_active_window_scope",
            "tenant_id",
            "sensor_id",
            "rule_id",
            "rule_version",
            unique=True,
            postgresql_where=text("status IN ('ACTIVE', 'RECOVERING')"),
        ),
    )

    assessment_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    sensor_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    machine_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)

    dimension: Mapped[QualityDimension] = mapped_column(
        _enum_column(QualityDimension), nullable=False
    )
    issue_type: Mapped[QualityIssueType] = mapped_column(
        _enum_column(QualityIssueType), nullable=False, index=True
    )
    severity: Mapped[IssueSeverity] = mapped_column(
        _enum_column(IssueSeverity), nullable=False, index=True
    )
    status: Mapped[IssueStatus] = mapped_column(
        _enum_column(IssueStatus), nullable=False, default=IssueStatus.ACTIVE, index=True
    )

    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    affected_event_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )

    event_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    rule_id: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(20), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(20), nullable=False)


class SensorQualityState(Base):
    """One continuously-upserted row per `(tenant_id, sensor_id)` — the always-current
    summary a `GET /api/v1/data-quality/sensors/{id}` response is built from directly,
    without scanning `quality_issue` history. Not a hypertable: bounded by sensor count."""

    __tablename__ = "sensor_quality_state"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "sensor_id", name="pk_sensor_quality_state"),
        composite_tenant_fk("sensor_id", "sensor"),
        composite_tenant_fk("machine_id", "machine", nullable=True),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sensor_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    machine_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)

    quality_state: Mapped[QualityState] = mapped_column(
        _enum_column(QualityState), nullable=False, default=QualityState.TRUSTED
    )
    eligibility: Mapped[Eligibility] = mapped_column(
        _enum_column(Eligibility), nullable=False, default=Eligibility.ELIGIBLE
    )

    last_good_reading_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_good_reading_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_observed_event_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    last_observed_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_observed_quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_observed_operating_state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_source_timestamp_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    expected_next_sequence: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    staleness_status: Mapped[StalenessStatus] = mapped_column(
        _enum_column(StalenessStatus), nullable=False, default=StalenessStatus.UNKNOWN
    )
    clock_status: Mapped[ClockStatus] = mapped_column(
        _enum_column(ClockStatus), nullable=False, default=ClockStatus.UNKNOWN
    )

    active_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    firmware_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    controller_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    policy_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Phase 8 — Baseline Engine.
#
# One table, not the three the brief suggests as an example (`baseline_profiles`,
# `baseline_statistics`, `baseline_contexts`) — see TECHNICAL_DECISIONS.md,
# baseline-single-table ADR. `statistics`/`context` are 1:1 with exactly one versioned
# profile row and are never queried independently of it, so denormalizing them as JSONB
# columns avoids a join that would only ever return one row, mirroring how
# `quality_assessment.rule_versions` is already JSONB rather than its own table.
#
# `context_key` is a deterministic canonical string built from `context`
# (`app.baselines.domain.context.context_key`) — e.g. "operating_state=RUNNING_HIGH_LOAD"
# or "" for a sensor-level/no-context profile — so a partial unique index can enforce
# "exactly one ACTIVE row per (sensor, strategy, context)" without needing a JSONB
# equality index. `version` increments per (sensor_id, strategy, context_key) lineage;
# superseded/invalidated rows are never deleted, only their `state` changes (brief §16 —
# no silent mutation of history, provenance preserved).
#
# Candidate/stability-gate fields (`candidate_*`) live on the *current* row (whichever one
# is ACTIVE, or the sole BUILDING/INSUFFICIENT_DATA row before first activation) rather
# than a separate candidate table — see docs/BASELINES.md "Contamination control" for why
# a candidate must stay stable across `stability_gate.required_stable_cycles` consecutive
# worker cycles before it replaces the active statistics (TECHNICAL_DECISIONS.md,
# baseline-contamination-control ADR).
# ---------------------------------------------------------------------------


class BaselineProfile(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "baseline_profile"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("sensor_id", "sensor"),
        composite_tenant_fk("machine_id", "machine", nullable=True),
        UniqueConstraint(
            "tenant_id",
            "sensor_id",
            "strategy",
            "context_key",
            "version",
            name="uq_baseline_profile_version",
        ),
        Index(
            "uq_baseline_profile_active",
            "tenant_id",
            "sensor_id",
            "strategy",
            "context_key",
            unique=True,
            postgresql_where=text("state = 'ACTIVE'"),
        ),
    )

    sensor_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    machine_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    measurement_type: Mapped[SensorType] = mapped_column(_enum_column(SensorType), nullable=False)

    strategy: Mapped[BaselineStrategyType] = mapped_column(
        _enum_column(BaselineStrategyType), nullable=False
    )
    metric_kind: Mapped[BaselineMetricKind] = mapped_column(
        _enum_column(BaselineMetricKind), nullable=False, default=BaselineMetricKind.STANDARD
    )
    # Canonical string built from `context` — see module docstring. Empty string for a
    # sensor-level (no-context) rolling/static profile, never NULL, so the partial unique
    # index above treats every strategy uniformly.
    context_key: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[BaselineState] = mapped_column(
        _enum_column(BaselineState), nullable=False, default=BaselineState.INSUFFICIENT_DATA
    )

    statistics: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    min_sample_required: Mapped[int] = mapped_column(Integer, nullable=False)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_seconds: Mapped[float] = mapped_column(Float, nullable=False)

    # Proposed-next-generation statistics, tracked on the current row until they have been
    # stable for enough consecutive worker cycles to be promoted into a new ACTIVE version
    # (contamination control — see module docstring).
    candidate_statistics: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    candidate_sample_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    candidate_window_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    candidate_window_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    candidate_first_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    candidate_stable_cycles: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    config_version: Mapped[str] = mapped_column(String(20), nullable=False)
    quality_policy_version: Mapped[str | None] = mapped_column(String(20), nullable=True)

    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    last_evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    refresh_interval_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    stale_after_seconds: Mapped[float] = mapped_column(Float, nullable=False)

    firmware_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    controller_version: Mapped[str | None] = mapped_column(String(50), nullable=True)


# ---------------------------------------------------------------------------
# Phase 9 — Rules Engine
# ---------------------------------------------------------------------------


class RuleFinding(Base, TenantScopedMixin, TimestampMixin):
    """One row per finding *lineage* — `(tenant_id, machine_id, component_id, rule_id,
    rule_version)` — deliberately denormalized (structured `evidence`/`limitations`/
    `quality_context`/`baseline_version_ids`/`source_event_ids` as JSONB on the same row as
    lifecycle/severity/version metadata) rather than a `rule_finding_evidence` child table,
    for the identical reason `BaselineProfile` chose one table over three
    (`TECHNICAL_DECISIONS.md`, ADR-071): a finding's evidence is always read and written
    together with the row that owns it, never independently. See ADR-078.

    Lifecycle mirrors `QualityIssue`'s ACTIVE/RECOVERING/RESOLVED window-scoped pattern
    (Phase 7) with one CANDIDATE stage prepended (Phase 9 brief §7/§20): at most one
    non-terminal (CANDIDATE/ACTIVE/RECOVERING) row may exist per lineage at a time
    (`uq_rule_finding_active_scope`), enforced the same way `uq_quality_issue_active_
    window_scope` is — a partial unique index used as the `ON CONFLICT` arbiter. RESOLVED
    rows are never deleted or overwritten; a later recurrence opens a fresh row.
    """

    __tablename__ = "rule_finding"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("machine_id", "machine"),
        Index(
            "uq_rule_finding_active_scope",
            "tenant_id",
            "machine_id",
            "component_id",
            "rule_id",
            "rule_version",
            unique=True,
            postgresql_where=text("state IN ('CANDIDATE', 'ACTIVE', 'RECOVERING')"),
        ),
    )

    machine_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    # Generic — the specific bearing/circuit/lubrication-system/machine a finding concerns;
    # `component_type` names which table it refers to (no FK: it is polymorphic by design,
    # matching how `Telemetry`'s own already-resolved hierarchy columns are the source for
    # this, never a fresh lookup — see `app.rules_engine.domain.context` module docstring).
    component_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    component_type: Mapped[str] = mapped_column(String(30), nullable=False)

    finding_type: Mapped[RuleFindingType] = mapped_column(
        _enum_column(RuleFindingType, length=50), nullable=False, index=True
    )
    rule_id: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(20), nullable=False)
    config_version: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[RuleCategory] = mapped_column(_enum_column(RuleCategory), nullable=False)

    severity: Mapped[RuleFindingSeverity] = mapped_column(
        _enum_column(RuleFindingSeverity), nullable=False, index=True
    )
    state: Mapped[RuleFindingState] = mapped_column(
        _enum_column(RuleFindingState),
        nullable=False,
        default=RuleFindingState.CANDIDATE,
        index=True,
    )
    evidence_strength: Mapped[EvidenceStrength] = mapped_column(
        _enum_column(EvidenceStrength), nullable=False
    )
    # Snapshotted at detection (brief §24): influences severity/priority, never whether
    # evidence exists in the first place — see ADR-083.
    criticality_at_detection: Mapped[str | None] = mapped_column(String(20), nullable=True)

    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    limitations: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    quality_context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    baseline_version_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    source_event_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )

    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Debounce bookkeeping (brief §20/§29) — consecutive-cycle counters, not a sliding
    # N-of-M window; see docs/RULES_ENGINE.md "Debounce and hysteresis" / ADR-081.
    candidate_stable_cycles: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
