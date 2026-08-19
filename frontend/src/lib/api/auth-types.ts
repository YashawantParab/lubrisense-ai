export type DemoRole =
  | "VIEWER"
  | "TECHNICIAN"
  | "RELIABILITY_ENGINEER"
  | "PLANT_MANAGER"
  | "DATA_SCIENTIST"
  | "ADMIN";

export interface DemoLoginResponse {
  access_token: string;
  token_type: string;
  role: DemoRole;
  user_id: string;
  display_name: string;
  expires_in_seconds: number;
}
