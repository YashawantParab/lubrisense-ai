export interface AuditEventResponse {
  id: string;
  actor_id: string;
  actor_type: "HUMAN" | "SYSTEM" | "AGENT";
  role: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  correlation_id: string;
  request_id: string | null;
  before_summary: string | null;
  after_summary: string | null;
  reason: string | null;
  source: string;
  occurred_at: string;
  created_at: string;
}

export interface PageMeta {
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface PaginatedAuditEvents {
  items: AuditEventResponse[];
  meta: PageMeta;
}
