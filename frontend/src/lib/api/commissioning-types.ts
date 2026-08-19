export type CommissioningStatus =
  | "DRAFT"
  | "CONFIGURING"
  | "VALIDATING"
  | "READY"
  | "COMPLETED"
  | "FAILED";

export type CapabilityLevel =
  | "NONE"
  | "BASIC_MONITORING"
  | "DELIVERY_INTELLIGENCE"
  | "BEARING_INTELLIGENCE"
  | "FULL_INTELLIGENCE";

export interface ValidationIssue {
  code: string;
  message: string;
  blocking: boolean;
}

export interface CommissioningSessionResponse {
  id: string;
  tenant_id: string;
  machine_id: string;
  gateway_id: string | null;
  status: CommissioningStatus;
  capability_level: CapabilityLevel;
  validation_issues: ValidationIssue[];
  steps_completed: string[];
  notes: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface StartCommissioningRequest {
  production_line_id: string;
  name: string;
  asset_code: string;
  machine_type: string;
}

export interface AddSensorRequest {
  sensor_type: string;
  sensor_code: string;
  name: string;
  unit?: string;
}

export interface AssignGatewayRequest {
  gateway_id: string;
}
