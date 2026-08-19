export interface GatewayResponse {
  id: string;
  site_id: string | null;
  plant_id: string | null;
  name: string;
  gateway_code: string;
  manufacturer_demo: string | null;
  model_demo: string | null;
  firmware_version: string | null;
  status: string;
  last_seen: string | null;
  created_at: string;
  updated_at: string;
}
