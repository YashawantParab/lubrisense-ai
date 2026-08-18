/**
 * Types mirroring the backend's Phase 6 telemetry query contract
 * (backend/app/api/schemas/telemetry.py).
 */

export interface TelemetryReadingResponse {
  event_id: string;
  sensor_id: string;
  machine_id: string | null;
  bearing_id: string | null;
  lubrication_system_id: string | null;
  circuit_id: string | null;

  measurement_type: string;
  value: number | null;
  unit: string;
  quality: string;
  operating_state: string;

  source_timestamp: string;
  persisted_timestamp: string;

  gateway_id: string;
  metadata: Record<string, unknown>;
}
