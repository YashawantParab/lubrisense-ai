export type DeviceType = "GATEWAY" | "CONTROLLER" | "SENSOR";
export type CompatibilityStatus =
  | "SUPPORTED"
  | "SUPPORTED_WITH_LIMITATIONS"
  | "UNKNOWN"
  | "INCOMPATIBLE";

export interface ConfigurationSnapshotResponse {
  id: string;
  machine_id: string;
  device_type: DeviceType;
  device_id: string;
  firmware_version: string | null;
  config: Record<string, unknown>;
  compatibility_status: CompatibilityStatus;
  is_current: boolean;
  captured_at: string;
}

export interface ConfigurationChangeResponse {
  id: string;
  machine_id: string;
  device_type: DeviceType;
  device_id: string;
  previous_snapshot_id: string | null;
  new_snapshot_id: string;
  changed_by: string;
  reason: string | null;
  source: string;
  baseline_review_required: boolean;
  occurred_at: string;
}
