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

from pgvector.sqlalchemy import Vector
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
    AgentMessageRole,
    AgentToolCallStatus,
    AssessmentScope,
    AuditActorType,
    BaselineMetricKind,
    BaselineSourceKind,
    BaselineState,
    BaselineStrategyType,
    CapabilityLevel,
    ClockStatus,
    CMMSWorkOrderStatus,
    CommercialStatus,
    CommissioningState,
    CommissioningStatus,
    CompatibilityStatus,
    ConditionConfidence,
    ConditionLifecycle,
    ConditionSeverity,
    ConditionType,
    Criticality,
    DecisionLifecycle,
    DecisionPriority,
    DocumentStatus,
    DocumentType,
    Eligibility,
    EnergyAssessmentStatus,
    EvidenceStrength,
    FeedbackClassification,
    ForecastHorizon,
    IncidentEventType,
    IncidentState,
    IssueSeverity,
    IssueStatus,
    LubricationSystemType,
    MachineStatus,
    MachineType,
    MaintenanceActionType,
    MaintenanceState,
    MLConfidenceCategory,
    MLInferenceStatus,
    MLResultKind,
    OperationalStatus,
    PrognosticStatus,
    QualityDimension,
    QualityIssueType,
    QualityState,
    QuarantineReason,
    RecommendedAction,
    RecommendedWindow,
    RuleCategory,
    RuleFindingSeverity,
    RuleFindingState,
    RuleFindingType,
    SensorStatus,
    SensorType,
    ServiceTier,
    StalenessStatus,
    StateTrend,
    StateType,
    StateUncertaintyCategory,
    TechnicianFindingResult,
    TelemetryQuality,
    TenantStatus,
)
from app.domain.enums import (
    DeviceType as DeviceTypeEnum,
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


# ---------------------------------------------------------------------------
# Phase 10 — Feature Engineering
# ---------------------------------------------------------------------------


class FeatureVector(Base, TenantScopedMixin, TimestampMixin):
    """Immutable logical model-input snapshot with full computation provenance.

    `id` is deterministic for the logical key, and the matching unique constraint is a
    second database-level idempotency guard. Existing vectors are never updated in place.
    """

    __tablename__ = "feature_vector"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("machine_id", "machine"),
        UniqueConstraint(
            "tenant_id",
            "machine_id",
            "entity_key",
            "feature_set",
            "feature_set_version",
            "as_of_timestamp",
            name="uq_feature_vector_logical",
        ),
    )

    machine_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    component_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    entity_key: Mapped[str] = mapped_column(String(100), nullable=False)
    feature_set: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    feature_set_version: Mapped[str] = mapped_column(String(20), nullable=False)
    as_of_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    feature_values: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    missing_features: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    quality_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    source_window: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    baseline_versions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    rule_versions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    feature_definition_versions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    feature_policy_version: Mapped[str] = mapped_column(String(20), nullable=False)


class MLInferenceResult(Base, TenantScopedMixin, TimestampMixin):
    """Persisted `ml-service` inference output (Phase 11 brief §42) — ML EVIDENCE, not a
    diagnosis, incident, or decision (see docs/ML_ARCHITECTURE.md "Core principle"). Every
    row is fully reproducible: `model_id`/`model_version` resolve back to one
    `ml-service` registry artifact, and `feature_vector_id` resolves back to one immutable
    Phase 10 `FeatureVector`.

    One table serves both `ANOMALY` and `CLASSIFICATION` result kinds (discriminated by
    `result_kind`) rather than two near-identical tables — the shared columns (provenance,
    quality, explanation) dominate, and kind-specific columns are simply nullable for the
    other kind.
    """

    __tablename__ = "ml_inference_result"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("machine_id", "machine"),
        Index(
            "ix_ml_inference_result_tenant_machine_model_time",
            "tenant_id",
            "machine_id",
            "model_id",
            text("as_of_timestamp DESC"),
        ),
    )

    machine_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    feature_vector_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    result_kind: Mapped[MLResultKind] = mapped_column(_enum_column(MLResultKind), nullable=False)
    status: Mapped[MLInferenceStatus] = mapped_column(
        _enum_column(MLInferenceStatus), nullable=False
    )
    as_of_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    anomaly_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    anomalous: Mapped[bool | None] = mapped_column(nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)

    predicted_class: Mapped[str | None] = mapped_column(String(80), nullable=True)
    class_probabilities: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    confidence_category: Mapped[MLConfidenceCategory | None] = mapped_column(
        _enum_column(MLConfidenceCategory), nullable=True
    )

    features_used: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    missing_features: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    quality_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    explanation: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )


class EnergyAssessment(Base, TenantScopedMixin, TimestampMixin):
    """Lubrication Efficiency Intelligence, Pass 1 (docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md,
    ADR-176) — energy-deviation EVIDENCE only, mirroring `MLInferenceResult`'s own
    "evidence, never a diagnosis" framing. `expected_power_kw`/`expected_lower_kw`/
    `expected_upper_kw` are read directly from the existing `app.baselines`
    `CONTEXTUAL_ASSET_BASELINE` machinery (`baseline_profile_id`/`baseline_source`
    resolve back to exactly which profile/fallback rung answered) — this table computes
    no statistics of its own.

    Deliberately does NOT carry a `lubrication_attribution` field yet: attribution,
    carbon estimation, and maintenance-verification are explicitly out of scope for this
    pass (see the design doc's implementation sequence, step 3+) and are added to this
    table (or a related one) only once that evidence chain is actually built and
    reviewed — never speculatively reserved here.
    """

    __tablename__ = "energy_assessment"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("machine_id", "machine"),
        composite_tenant_fk("power_sensor_id", "sensor"),
        Index(
            "ix_energy_assessment_tenant_machine_time",
            "tenant_id",
            "machine_id",
            text("as_of_timestamp DESC"),
        ),
    )

    machine_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    power_sensor_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    as_of_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    actual_power_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_power_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_lower_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_upper_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    residual_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    residual_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    status: Mapped[EnergyAssessmentStatus] = mapped_column(
        _enum_column(EnergyAssessmentStatus), nullable=False
    )
    #: Reuses `app.data_quality`'s own per-sensor vocabulary directly (TRUSTED/
    #: USABLE_WITH_CAUTION/UNUSABLE) rather than inventing a parallel one — this
    #: assessment concerns exactly one sensor's data quality, not a multi-source
    #: aggregate rollup (contrast `ConditionAssessment.quality_context`, which spans many
    #: sensors and does need its own coarser TRUSTED/CAUTION/NO_TRUSTED_DATA rollup).
    data_quality_state: Mapped[QualityState] = mapped_column(
        _enum_column(QualityState), nullable=False
    )

    #: Which `app.baselines` fallback rung actually answered (EXACT_CONTEXT/
    #: OPERATING_STATE/SENSOR_LEVEL/ENGINEERING_REFERENCE/NONE) — same field shape as
    #: `app/api/schemas/baselines.py`'s `CurrentBaselineResponse.source`.
    baseline_source: Mapped[BaselineSourceKind] = mapped_column(
        _enum_column(BaselineSourceKind), nullable=False
    )
    baseline_profile_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    operating_state: Mapped[str | None] = mapped_column(String(40), nullable=True)

    engine_version: Mapped[str] = mapped_column(String(20), nullable=False)


class StateEstimate(Base, TenantScopedMixin, TimestampMixin):
    """Persisted Kalman-filter state estimate (Phase 12 brief §16-§17) — condition
    EVIDENCE, not a diagnosis. Every row is fully reproducible: `feature_vector_id`
    resolves back to one immutable Phase 10 `FeatureVector`, and
    `estimator_id`/`estimator_version`/`config_version` resolve back to the exact filter
    configuration that produced it.

    Unlike `MLInferenceResult` (Phase 11, stateless point-in-time scoring), a state
    estimate is inherently sequential — its prior/posterior depend on the previous
    estimate for the same `(machine_id, state_type, estimator_version)`. Rows are
    append-only and never updated in place; idempotency is enforced on
    `(tenant_id, machine_id, state_type, as_of_timestamp, estimator_version)` so replaying
    the same historical window twice does not duplicate estimates (Phase 12 brief §17).
    """

    __tablename__ = "state_estimate"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("machine_id", "machine"),
        UniqueConstraint(
            "tenant_id",
            "machine_id",
            "state_type",
            "as_of_timestamp",
            "estimator_version",
            name="uq_state_estimate_logical",
        ),
        Index(
            "ix_state_estimate_tenant_machine_type_time",
            "tenant_id",
            "machine_id",
            "state_type",
            text("as_of_timestamp DESC"),
        ),
    )

    machine_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    component_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    state_type: Mapped[StateType] = mapped_column(_enum_column(StateType), nullable=False)
    as_of_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    state_value: Mapped[float] = mapped_column(Float, nullable=False)
    state_rate: Mapped[float] = mapped_column(Float, nullable=False)
    trend: Mapped[StateTrend] = mapped_column(_enum_column(StateTrend), nullable=False)
    uncertainty: Mapped[StateUncertaintyCategory] = mapped_column(
        _enum_column(StateUncertaintyCategory), nullable=False
    )
    covariance_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    estimator_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    estimator_version: Mapped[str] = mapped_column(String(20), nullable=False)
    config_version: Mapped[str] = mapped_column(String(20), nullable=False)
    feature_set: Mapped[str] = mapped_column(String(80), nullable=False)
    feature_set_version: Mapped[str] = mapped_column(String(20), nullable=False)
    feature_vector_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)

    dt_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    prediction_only: Mapped[bool] = mapped_column(nullable=False, default=False)
    observations_used: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    observations_missing: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    quality_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )


# ---------------------------------------------------------------------------
# Phase 13 — Condition Intelligence
# ---------------------------------------------------------------------------


class ConditionAssessment(Base, TenantScopedMixin, TimestampMixin):
    """Persisted `ConditionEngine` output (Phase 13 brief §13.5) — a SYNTHESIS judgment
    over `RuleFinding`/`MLInferenceResult`/`StateEstimate`/quality evidence, never a new
    primary evidence source itself. Append-only: every `ConditionEngine.assess()` call
    inserts a fresh row (mirrors `MLInferenceResult`/`StateEstimate`'s own "recompute and
    persist" pattern) — `lifecycle_state` captures how this assessment relates to the
    immediately preceding one for the same machine, so history is a readable timeline, not
    a single mutated row.
    """

    __tablename__ = "condition_assessment"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("machine_id", "machine"),
        Index(
            "ix_condition_assessment_tenant_machine_time",
            "tenant_id",
            "machine_id",
            text("as_of_timestamp DESC"),
        ),
    )

    machine_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    component_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)

    condition_type: Mapped[ConditionType] = mapped_column(
        _enum_column(ConditionType, length=50), nullable=False, index=True
    )
    lifecycle_state: Mapped[ConditionLifecycle] = mapped_column(
        _enum_column(ConditionLifecycle), nullable=False
    )
    severity: Mapped[ConditionSeverity] = mapped_column(
        _enum_column(ConditionSeverity), nullable=False
    )
    confidence: Mapped[ConditionConfidence] = mapped_column(
        _enum_column(ConditionConfidence), nullable=False
    )

    as_of_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    evidence_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    rule_finding_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    ml_result_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    state_estimate_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    quality_context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    baseline_versions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    instrumentation_coverage: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    limitations: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    recommended_next_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)

    policy_version: Mapped[str] = mapped_column(String(20), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(20), nullable=False)


# ---------------------------------------------------------------------------
# Phase 15 — Prognostics
# ---------------------------------------------------------------------------


class PrognosticAssessment(Base, TenantScopedMixin, TimestampMixin):
    """Persisted `PrognosticEngine` output (Phase 15 brief §15.4) — one row per
    `(state_type, horizon)` forecast, derived from the Phase 12 `StateEstimate` this
    forecast extrapolates. Append-only, same rationale as `ConditionAssessment`."""

    __tablename__ = "prognostic_assessment"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("machine_id", "machine"),
        Index(
            "ix_prognostic_assessment_tenant_machine_state_time",
            "tenant_id",
            "machine_id",
            "state_type",
            "horizon",
            text("as_of_timestamp DESC"),
        ),
    )

    machine_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    component_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    state_estimate_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)

    state_type: Mapped[StateType] = mapped_column(_enum_column(StateType), nullable=False)
    horizon: Mapped[ForecastHorizon] = mapped_column(_enum_column(ForecastHorizon), nullable=False)
    status: Mapped[PrognosticStatus] = mapped_column(_enum_column(PrognosticStatus), nullable=False)

    as_of_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    current_state: Mapped[float] = mapped_column(Float, nullable=False)
    trend: Mapped[StateTrend] = mapped_column(_enum_column(StateTrend), nullable=False)
    predicted_state_at_horizon: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_threshold_crossing_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    uncertainty: Mapped[StateUncertaintyCategory] = mapped_column(
        _enum_column(StateUncertaintyCategory), nullable=False
    )
    data_sufficient: Mapped[bool] = mapped_column(nullable=False)

    limitations: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    engine_version: Mapped[str] = mapped_column(String(20), nullable=False)
    config_version: Mapped[str] = mapped_column(String(20), nullable=False)


# ---------------------------------------------------------------------------
# Phase 14 — Decision Intelligence
# ---------------------------------------------------------------------------


class DecisionAssessment(Base, TenantScopedMixin, TimestampMixin):
    """Persisted `DecisionEngine` output (Phase 14 brief §14.3) — the only layer whose
    output is meant to trigger a human maintenance action, and therefore the only layer
    with an explicit `human_review_required` gate and a lifecycle that never silently
    overwrites a prior recommendation (`lifecycle_state`, §14.12)."""

    __tablename__ = "decision_assessment"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("machine_id", "machine"),
        Index(
            "ix_decision_assessment_tenant_machine_time",
            "tenant_id",
            "machine_id",
            text("as_of_timestamp DESC"),
        ),
    )

    machine_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    component_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    condition_assessment_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    prognostic_assessment_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)

    priority: Mapped[DecisionPriority] = mapped_column(
        _enum_column(DecisionPriority), nullable=False
    )
    recommended_action: Mapped[RecommendedAction] = mapped_column(
        _enum_column(RecommendedAction, length=50), nullable=False
    )
    recommended_window: Mapped[RecommendedWindow] = mapped_column(
        _enum_column(RecommendedWindow, length=40), nullable=False
    )
    risk_if_deferred: Mapped[str] = mapped_column(Text, nullable=False)
    human_review_required: Mapped[bool] = mapped_column(nullable=False, default=True)

    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    confidence: Mapped[ConditionConfidence] = mapped_column(
        _enum_column(ConditionConfidence), nullable=False
    )
    limitations: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )

    lifecycle_state: Mapped[DecisionLifecycle] = mapped_column(
        _enum_column(DecisionLifecycle), nullable=False, default=DecisionLifecycle.ACTIVE
    )
    as_of_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    policy_version: Mapped[str] = mapped_column(String(20), nullable=False)


# ---------------------------------------------------------------------------
# Phase 16 — Alert Correlation + Incident Management
# ---------------------------------------------------------------------------


class Incident(Base, TenantScopedMixin, TimestampMixin):
    """One coherent operational problem for one machine/component/condition-family, not
    one row per evaluation cycle (Phase 16 brief §16.1/§16.4). `correlation_key` is a
    deterministic string (`app.incidents.services.correlation.build_correlation_key`) —
    never opaque ML clustering. At most one non-terminal (state not in RESOLVED/CLOSED)
    incident may exist per `(tenant, machine, correlation_key)` at a time
    (`uq_incident_active_correlation_key`), mirroring `RuleFinding`'s own
    `uq_rule_finding_active_scope` partial-unique-index idempotency pattern (ADR-078).
    RESOLVED/CLOSED rows are never deleted or overwritten — a later recurrence (family no
    longer matches an open incident) opens a fresh row with a fresh correlation key
    instance."""

    __tablename__ = "incident"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("machine_id", "machine"),
        Index(
            "uq_incident_active_correlation_key",
            "tenant_id",
            "machine_id",
            "correlation_key",
            unique=True,
            postgresql_where=text("state NOT IN ('RESOLVED', 'CLOSED')"),
        ),
        Index(
            "ix_incident_tenant_machine_time", "tenant_id", "machine_id", text("created_at DESC")
        ),
    )

    machine_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    component_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    correlation_key: Mapped[str] = mapped_column(String(150), nullable=False, index=True)

    incident_type: Mapped[ConditionType] = mapped_column(
        _enum_column(ConditionType, length=50), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[ConditionSeverity] = mapped_column(
        _enum_column(ConditionSeverity), nullable=False
    )
    priority: Mapped[DecisionPriority] = mapped_column(
        _enum_column(DecisionPriority), nullable=False
    )
    state: Mapped[IncidentState] = mapped_column(
        _enum_column(IncidentState), nullable=False, default=IncidentState.OPEN, index=True
    )

    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    condition_assessment_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    decision_assessment_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    prognostic_assessment_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    rule_finding_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    ml_result_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    state_estimate_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    evidence_refs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    assigned_to: Mapped[str | None] = mapped_column(String(150), nullable=True)

    policy_version: Mapped[str] = mapped_column(String(20), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(20), nullable=False)


class IncidentEvent(Base, TenantScopedMixin, TimestampMixin):
    """Append-only incident timeline (Phase 16 brief §16.8). Never mutated or deleted —
    `IncidentEvent` rows are the only place incident history is readable turn-by-turn;
    `Incident` itself only ever reflects current state."""

    __tablename__ = "incident_event"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("incident_id", "incident"),
        Index("ix_incident_event_tenant_incident_time", "tenant_id", "incident_id", "created_at"),
    )

    incident_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    event_type: Mapped[IncidentEventType] = mapped_column(
        _enum_column(IncidentEventType), nullable=False
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Phase 17 — Maintenance Workflow
# ---------------------------------------------------------------------------


class MaintenanceCase(Base, TenantScopedMixin, TimestampMixin):
    """Human-controlled maintenance workflow linked to one `Incident` (Phase 17 brief
    §17.4). No physical maintenance action is ever executed automatically — this table
    only ever records what a human recommended/planned/performed/found (§17.3). At most
    one non-terminal (state not in COMPLETED/CANCELLED) case may exist per incident
    (`uq_maintenance_case_active_incident`), the same partial-unique-index idempotency
    pattern used throughout this platform."""

    __tablename__ = "maintenance_case"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("incident_id", "incident"),
        Index(
            "uq_maintenance_case_active_incident",
            "tenant_id",
            "incident_id",
            unique=True,
            postgresql_where=text("state NOT IN ('COMPLETED', 'CANCELLED')"),
        ),
    )

    incident_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    machine_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    component_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    condition_assessment_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    decision_assessment_id: Mapped[uuid.UUID] = mapped_column(nullable=False)

    recommended_action: Mapped[RecommendedAction] = mapped_column(
        _enum_column(RecommendedAction, length=50), nullable=False
    )
    recommended_window: Mapped[RecommendedWindow] = mapped_column(
        _enum_column(RecommendedWindow, length=40), nullable=False
    )
    priority: Mapped[DecisionPriority] = mapped_column(
        _enum_column(DecisionPriority), nullable=False
    )
    human_review_required: Mapped[bool] = mapped_column(nullable=False, default=True)
    state: Mapped[MaintenanceState] = mapped_column(
        _enum_column(MaintenanceState), nullable=False, index=True
    )

    # Deterministic, template-based checklist snapshot (Phase 17 brief §17.5 — no RAG/LLM
    # yet). `[{"text": str, "completed": bool}, ...]`. Embedded here rather than a separate
    # `inspection_checklist` table since it is always read/written together with the case
    # that owns it, matching `RuleFinding`'s own single-table-over-child-table rationale
    # (ADR-078) — see ADR-129.
    checklist: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    checklist_template_id: Mapped[str] = mapped_column(String(60), nullable=False)

    feedback_classification: Mapped[FeedbackClassification | None] = mapped_column(
        _enum_column(FeedbackClassification), nullable=True
    )

    planned_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    policy_version: Mapped[str] = mapped_column(String(20), nullable=False)


class TechnicianFinding(Base, TenantScopedMixin, TimestampMixin):
    """Append-only technician findings for one `MaintenanceCase` (Phase 17 brief §17.6).
    Multiple findings may be recorded over the life of a case (an initial finding, a
    follow-up); the case's `feedback_classification` reflects the case's overall outcome,
    not any single finding."""

    __tablename__ = "technician_finding"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("maintenance_case_id", "maintenance_case"),
        Index("ix_technician_finding_tenant_case_time", "tenant_id", "maintenance_case_id"),
    )

    maintenance_case_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    result: Mapped[TechnicianFindingResult] = mapped_column(
        _enum_column(TechnicianFindingResult, length=40), nullable=False
    )
    component: Mapped[str | None] = mapped_column(String(150), nullable=True)
    observed_issue: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    # Demo user placeholder — Phase 2's tenant-context ADR applies equally here: no real
    # auth/identity exists yet, so this is a free-text identifier, never a FK to a users
    # table that does not exist in this reference implementation.
    technician_identifier: Mapped[str] = mapped_column(String(150), nullable=False)
    attachments_metadata: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MaintenanceAction(Base, TenantScopedMixin, TimestampMixin):
    """Append-only record of a maintenance action a human performed (Phase 17 brief
    §17.7). Recording an action here is a record of what was done, never a system-issued
    physical command — see CLAUDE.md "Workflow Intelligence" boundary."""

    __tablename__ = "maintenance_action"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("maintenance_case_id", "maintenance_case"),
        Index("ix_maintenance_action_tenant_case_time", "tenant_id", "maintenance_case_id"),
    )

    maintenance_case_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    action_type: Mapped[MaintenanceActionType] = mapped_column(
        _enum_column(MaintenanceActionType, length=40), nullable=False
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_by: Mapped[str] = mapped_column(String(150), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FeedbackRecord(Base, TenantScopedMixin, TimestampMixin):
    """One feedback record per completed `MaintenanceCase` (Phase 17 brief §17.9-§17.12).
    Preserves pointers to the original intelligence evidence even for FALSE_POSITIVE
    outcomes (§17.10 — the intelligence result is never erased). Recording this NEVER
    automatically retrains an ML model (ADR-131) — it is an audit/learning record for a
    future, explicitly human-triggered retraining/evaluation phase, matching the
    already-accepted no-auto-retraining rule from Phase 11/CLAUDE.md."""

    __tablename__ = "feedback_record"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("maintenance_case_id", "maintenance_case"),
    )

    maintenance_case_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    incident_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    condition_assessment_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    decision_assessment_id: Mapped[uuid.UUID] = mapped_column(nullable=False)

    classification: Mapped[FeedbackClassification] = mapped_column(
        _enum_column(FeedbackClassification), nullable=False, index=True
    )
    confirmed_component: Mapped[str | None] = mapped_column(String(150), nullable=True)
    confirmed_finding: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Real, fresh re-evaluation of the machine's condition after the recorded action —
    # never the original pre-action condition — used only for transparency, never to
    # silently auto-complete the case (Phase 17 brief §17.8).
    post_action_condition_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_by: Mapped[str] = mapped_column(String(150), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Phase 20 — CMMS Adapter
# ---------------------------------------------------------------------------


class DemoCMMSWorkOrder(Base, TenantScopedMixin, TimestampMixin):
    """Locally-persisted demo work order (Phase 20 brief §20.2). Exactly one draft per
    `MaintenanceCase` (`uq_demo_cmms_work_order_case`, Phase 20 brief §20.5 idempotency) —
    never multiple accidental drafts for the same case. A real external CMMS submission is
    always a distinct future step requiring explicit human approval (§20.4 draft-first);
    this table only ever represents the local draft/demo side."""

    __tablename__ = "demo_cmms_work_order"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("maintenance_case_id", "maintenance_case"),
        UniqueConstraint("tenant_id", "maintenance_case_id", name="uq_demo_cmms_work_order_case"),
    )

    maintenance_case_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    external_reference: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    asset_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    priority: Mapped[DecisionPriority] = mapped_column(
        _enum_column(DecisionPriority), nullable=False
    )
    status: Mapped[CMMSWorkOrderStatus] = mapped_column(
        _enum_column(CMMSWorkOrderStatus), nullable=False, default=CMMSWorkOrderStatus.DRAFT
    )
    recommended_window: Mapped[RecommendedWindow] = mapped_column(
        _enum_column(RecommendedWindow, length=40), nullable=False
    )
    checklist: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )


# ---------------------------------------------------------------------------
# Phase 18 — Approved-Knowledge RAG Platform
# ---------------------------------------------------------------------------

#: Must match `app.knowledge.embeddings.provider.EMBEDDING_DIMENSIONS` — kept as a
#: literal here (not imported) since `app.domain` is a dependency-free base layer every
#: other package builds on; a dedicated test
#: (`tests/knowledge/test_embeddings.py::test_embedding_dimension_matches_column`) pins
#: the two constants together.
_EMBEDDING_DIMENSIONS = 256


class KnowledgeDocument(Base, TimestampMixin):
    """Approved-knowledge source document (Phase 18 brief §18.1/§18.5). Deliberately NOT
    `TenantScopedMixin` — `tenant_id` is nullable so a document can be either global
    (visible to every tenant, the common case for generic industrial procedures) or
    tenant-specific (nullable FK, not the composite-tenant-FK pattern, since this is a
    root entity with no tenant-scoped parent to hang one off of — see ADR-139).

    Versioning (Phase 18 brief §18.12): multiple rows may share `document_key` (a stable
    slug identifying "the same document" across versions) with different `version`
    values. At most one row per `(tenant_id, document_key)` may be `APPROVED` at a time
    (`uq_knowledge_document_active_approved`) — approving a new version transitions the
    previously-APPROVED row for the same key to `RETIRED`, the same supersede-not-delete
    pattern `DecisionAssessment` already established (ADR-121), applied to documents.

    `(document_key, version)` idempotency/uniqueness is scoped by `tenant_id`, not
    global — a real bug found live: two different tenants ingesting a document under the
    same `document_key`/`version` (e.g. two tenants both submitting a demo procedure
    named identically) collided, and the second tenant's "idempotent ingest" silently
    returned the FIRST tenant's row instead of creating its own (ADR-140).
    """

    __tablename__ = "knowledge_document"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "document_key", "version", name="uq_knowledge_document_key_version"
        ),
        Index(
            "uq_knowledge_document_active_approved",
            "tenant_id",
            "document_key",
            unique=True,
            postgresql_where=text("status = 'APPROVED'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=True, index=True
    )

    document_key: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[DocumentType] = mapped_column(
        _enum_column(DocumentType, length=40), nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        _enum_column(DocumentStatus), nullable=False, default=DocumentStatus.DRAFT, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str] = mapped_column(String(150), nullable=False)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Demo user placeholder — no real auth/identity exists yet (Phase 2 tenant-context
    # ADR applies equally here), matching `TechnicianFinding.technician_identifier`.
    approved_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)


class KnowledgeChunk(Base, TimestampMixin):
    """One retrievable section of a `KnowledgeDocument` (Phase 18 brief §18.6).
    Deterministic chunking by markdown heading — one chunk per section, preserving
    `heading`/`section` for citations, never arbitrary tiny fragments. Never denormalizes
    the parent document's `status`/`tenant_id` — the retriever always joins to
    `KnowledgeDocument` for those, so a document's lifecycle transition (e.g. APPROVED ->
    RETIRED) instantly and correctly affects every one of its chunks with no risk of a
    stale denormalized copy."""

    __tablename__ = "knowledge_chunk"
    __table_args__ = (
        UniqueConstraint("document_id", "ordinal", name="uq_knowledge_chunk_document_ordinal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_document.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str] = mapped_column(String(150), nullable=False)
    heading: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(_EMBEDDING_DIMENSIONS), nullable=False)


# ---------------------------------------------------------------------------
# Phase 19 — Guarded GenAI Agent
# ---------------------------------------------------------------------------


class AgentSession(Base, TenantScopedMixin, TimestampMixin):
    """One guarded-assistant conversation (Phase 19 brief §19.1). `machine_id`/
    `incident_id`/`case_id` are optional context, plain nullable columns (no FK) —
    mirrors `RuleFinding.component_id`'s polymorphic-optional-context pattern, since a
    session may reference any subset of these or none at all."""

    __tablename__ = "agent_session"
    __table_args__ = (tenant_unique(),)

    machine_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    incident_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    maintenance_case_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)


class AgentMessage(Base, TenantScopedMixin, TimestampMixin):
    """Append-only conversation transcript."""

    __tablename__ = "agent_message"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("session_id", "agent_session"),
        Index("ix_agent_message_tenant_session_time", "tenant_id", "session_id", "created_at"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    role: Mapped[AgentMessageRole] = mapped_column(_enum_column(AgentMessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Structured payload mirroring `AgentResponse` (citations/tool_calls/draft_artifacts/
    # limitations/human_review_required) for ASSISTANT messages; empty for USER messages.
    response_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )


class AgentToolCall(Base, TenantScopedMixin, TimestampMixin):
    """Append-only tool-call audit record (Phase 19 brief §19.10). Never persists
    secrets — `arguments` is already-sanitized (ids/short strings only, never telemetry
    payloads or credentials)."""

    __tablename__ = "agent_tool_call"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("session_id", "agent_session"),
        Index("ix_agent_tool_call_tenant_session_time", "tenant_id", "session_id", "created_at"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    arguments: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    status: Mapped[AgentToolCallStatus] = mapped_column(
        _enum_column(AgentToolCallStatus), nullable=False
    )
    result_summary: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)


# ---------------------------------------------------------------------------
# Phase 25 — Auditability
# ---------------------------------------------------------------------------


class AuditEvent(Base, TenantScopedMixin, TimestampMixin):
    """Append-only "who did what, when, to which entity, and why" record (Phase 25
    brief §25.1). Written only through `app.audit.service.AuditService.record()` — there
    is deliberately no update/delete API anywhere in this package (§25.4). `actor_type`
    distinguishes a real person (`HUMAN`) from a scheduler/worker (`SYSTEM`) and from the
    guarded agent preparing a draft (`AGENT`) — a `SYSTEM` event is never recorded as if
    a person performed it (§25.3). Never stores secrets — `before_summary`/
    `after_summary`/`reason` are short, human-readable strings, never raw payloads or
    credentials (ADR-152)."""

    __tablename__ = "audit_event"
    __table_args__ = (
        tenant_unique(),
        Index("ix_audit_event_tenant_entity", "tenant_id", "entity_type", "entity_id"),
        Index("ix_audit_event_tenant_actor_time", "tenant_id", "actor_id", text("created_at DESC")),
        Index("ix_audit_event_tenant_time", "tenant_id", text("created_at DESC")),
        Index("ix_audit_event_correlation", "correlation_id"),
    )

    actor_id: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    actor_type: Mapped[AuditActorType] = mapped_column(_enum_column(AuditActorType), nullable=False)
    role: Mapped[str | None] = mapped_column(String(50), nullable=True)

    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    before_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[str] = mapped_column(String(100), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Phase 30 — Customer Onboarding / Commissioning
# ---------------------------------------------------------------------------


class CommissioningSession(Base, TenantScopedMixin, TimestampMixin):
    """A guided demo commissioning workflow for one machine (Phase 30 brief §30.1/§30.2)
    — never real physical device discovery. Created together with its `Machine` (status
    `COMMISSIONING`) so every subsequent step (sensor mapping, gateway assignment,
    validation) has a real machine to attach to. `capability_level` and
    `validation_issues` are recomputed by `validate()`, never hand-set."""

    __tablename__ = "commissioning_session"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("machine_id", "machine"),
        composite_tenant_fk("gateway_id", "gateway", nullable=True),
    )

    machine_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    gateway_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    status: Mapped[CommissioningStatus] = mapped_column(
        _enum_column(CommissioningStatus), nullable=False, default=CommissioningStatus.DRAFT
    )
    capability_level: Mapped[CapabilityLevel] = mapped_column(
        _enum_column(CapabilityLevel), nullable=False, default=CapabilityLevel.NONE
    )
    validation_issues: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    steps_completed: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# Phase 31 — Firmware / Configuration Management
# ---------------------------------------------------------------------------


class ConfigurationSnapshot(Base, TenantScopedMixin, TimestampMixin):
    """One point-in-time configuration/firmware snapshot for one device (Phase 31 brief
    §31.3). Never stores secrets — `config` is limited to non-sensitive operational
    metadata (sampling interval, units, mapping). Superseding a snapshot never deletes
    the prior one (`is_current` flips instead) — see `ConfigurationChange` for the
    append-only transition record."""

    __tablename__ = "configuration_snapshot"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("machine_id", "machine"),
        Index(
            "uq_configuration_snapshot_current_device",
            "tenant_id",
            "device_type",
            "device_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    machine_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    device_type: Mapped[DeviceTypeEnum] = mapped_column(
        _enum_column(DeviceTypeEnum), nullable=False, index=True
    )
    device_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    firmware_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    compatibility_status: Mapped[CompatibilityStatus] = mapped_column(
        _enum_column(CompatibilityStatus), nullable=False, default=CompatibilityStatus.UNKNOWN
    )
    is_current: Mapped[bool] = mapped_column(nullable=False, default=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConfigurationChange(Base, TenantScopedMixin, TimestampMixin):
    """Append-only configuration/firmware change history (Phase 31 brief §31.4) — never
    updated or deleted. `baseline_review_required` surfaces that a Phase 8 baseline may
    need human review after this change; it never automatically transitions or destroys
    existing `BaselineProfile` history (§31.6 — "do not automatically destroy existing
    baseline history")."""

    __tablename__ = "configuration_change"
    __table_args__ = (
        tenant_unique(),
        composite_tenant_fk("machine_id", "machine"),
        composite_tenant_fk("new_snapshot_id", "configuration_snapshot"),
        composite_tenant_fk("previous_snapshot_id", "configuration_snapshot", nullable=True),
    )

    machine_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    device_type: Mapped[DeviceTypeEnum] = mapped_column(
        _enum_column(DeviceTypeEnum), nullable=False
    )
    device_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    previous_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    new_snapshot_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    changed_by: Mapped[str] = mapped_column(String(150), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    baseline_review_required: Mapped[bool] = mapped_column(nullable=False, default=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
