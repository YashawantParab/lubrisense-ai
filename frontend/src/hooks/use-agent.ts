"use client";

import { useMutation } from "@tanstack/react-query";

import { sendChat } from "@/lib/api/agent";
import type { ChatRequest } from "@/lib/api/agent-types";

export function useSendChat() {
  return useMutation({
    mutationFn: (body: ChatRequest) => sendChat(body),
  });
}
