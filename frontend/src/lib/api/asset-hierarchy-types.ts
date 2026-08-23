/**
 * Types mirroring the backend's Phase 2 asset-hierarchy response contracts
 * (backend/app/api/schemas/*.py). Kept hand-written and minimal — a generated client can
 * replace this once the API surface grows further.
 */

export interface PageMeta {
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface PaginatedResponse<T> {
  items: T[];
  meta: PageMeta;
}

// --- Hierarchy tree (GET /api/v1/hierarchy) ---

export interface HierarchyMachine {
  id: string;
  name: string;
  asset_code: string;
  machine_type: string;
  criticality: string;
  status: string;
  /** Product-presentation equipment class for the curated showcase fleet (e.g. "Ball
   * Mill") — null for every other machine, in which case prefer `humanize(machine_type)`. */
  equipment_class: string | null;
  /** Synthetic process-area label for the curated showcase fleet (e.g. "Grinding") —
   * null for every other machine. */
  area: string | null;
}

export interface HierarchyProductionLine {
  id: string;
  name: string;
  code: string;
  criticality: string;
  status: string;
  machines: HierarchyMachine[];
}

export interface HierarchyPlant {
  id: string;
  name: string;
  code: string;
  status: string;
  production_lines: HierarchyProductionLine[];
}

export interface HierarchySite {
  id: string;
  name: string;
  code: string;
  status: string;
  plants: HierarchyPlant[];
}

export interface HierarchyCustomerAccount {
  id: string;
  name: string;
  code: string;
  service_tier: string;
  commercial_status: string;
  sites: HierarchySite[];
}

export interface HierarchyResponse {
  customers: HierarchyCustomerAccount[];
  generated_at: string;
}

// --- Machine detail + hierarchy (GET /api/v1/machines/{id}, .../hierarchy) ---

export interface MachineResponse {
  id: string;
  production_line_id: string;
  name: string;
  asset_code: string;
  machine_type: string;
  manufacturer: string | null;
  model: string | null;
  serial_number_demo: string | null;
  installation_date: string | null;
  criticality: string;
  status: string;
  operating_profile: Record<string, unknown>;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface BearingResponse {
  id: string;
  machine_id: string;
  name: string;
  position: string;
  bearing_type: string | null;
  manufacturer: string | null;
  model: string | null;
  criticality: string;
  installation_date: string | null;
  status: string;
}

export interface SensorResponse {
  id: string;
  sensor_code: string;
  name: string;
  sensor_type: string;
  unit: string | null;
  installation_date: string | null;
  calibration_date: string | null;
  firmware_version: string | null;
  status: string;
  quality_state: string;
  attached_entity_type: string;
  attached_entity_id: string;
}

export interface LubricationPointResponse {
  id: string;
  circuit_id: string;
  bearing_id: string | null;
  name: string;
  code: string;
  status: string;
}

export interface CircuitResponse {
  id: string;
  lubrication_system_id: string;
  distributor_id: string | null;
  name: string;
  code: string;
  status: string;
  lubrication_points: LubricationPointResponse[];
}

export interface ReservoirResponse {
  id: string;
  name: string;
  capacity_demo: number | null;
  capacity_unit: string | null;
  lubricant_type_demo: string | null;
  status: string;
}

export interface PumpResponse {
  id: string;
  name: string;
  pump_type: string | null;
  manufacturer: string | null;
  model: string | null;
  status: string;
}

export interface ControllerResponse {
  id: string;
  name: string;
  controller_type: string | null;
  manufacturer: string | null;
  model: string | null;
  status: string;
}

export interface DistributorResponse {
  id: string;
  name: string;
  type: string | null;
  status: string;
}

export interface LubricationSystemResponse {
  id: string;
  machine_id: string;
  name: string;
  system_type: string;
  status: string;
  commissioning_state: string;
  reservoirs: ReservoirResponse[];
  pumps: PumpResponse[];
  controllers: ControllerResponse[];
  distributors: DistributorResponse[];
  circuits: CircuitResponse[];
}

export interface MachineHierarchyResponse {
  machine: MachineResponse;
  bearings: BearingResponse[];
  lubrication_systems: LubricationSystemResponse[];
  sensors: SensorResponse[];
}
