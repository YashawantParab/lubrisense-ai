import { tenantScopedFetch } from "@/lib/api/client";
import type { ChatRequest, ChatResponse } from "@/lib/api/agent-types";

export function sendChat(body: ChatRequest): Promise<ChatResponse> {
  return tenantScopedFetch<ChatResponse>("/api/v1/agent/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
