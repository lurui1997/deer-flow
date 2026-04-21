import { getBackendBaseURL } from "@/core/config";

import type {
  HITLBulkStatusRequest,
  HITLBulkStatusResponse,
  HITLPendingListResponse,
  HITLResponseRequest,
  HITLResponseResult,
  HITLStatus,
} from "./types";

export async function getHITLStatus(threadId: string): Promise<HITLStatus> {
  const res = await fetch(`${getBackendBaseURL()}/api/hitl/threads/${threadId}/status`);
  if (!res.ok) throw new Error(`Failed to get HITL status: ${res.statusText}`);
  return res.json() as Promise<HITLStatus>;
}

export async function submitHITLResponse(
  threadId: string,
  request: HITLResponseRequest
): Promise<HITLResponseResult> {
  const res = await fetch(`${getBackendBaseURL()}/api/hitl/threads/${threadId}/respond`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!res.ok) throw new Error(`Failed to submit HITL response: ${res.statusText}`);
  return res.json() as Promise<HITLResponseResult>;
}

export async function getBulkHITLStatus(
  threadIds: string[]
): Promise<HITLBulkStatusResponse> {
  const res = await fetch(`${getBackendBaseURL()}/api/hitl/threads/bulk-status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_ids: threadIds } as HITLBulkStatusRequest),
  });
  if (!res.ok) throw new Error(`Failed to get bulk HITL status: ${res.statusText}`);
  return res.json() as Promise<HITLBulkStatusResponse>;
}

export async function listPendingHITL(
  limit: number = 100,
  offset: number = 0
): Promise<HITLPendingListResponse> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  const res = await fetch(`${getBackendBaseURL()}/api/hitl/pending?${params}`);
  if (!res.ok) throw new Error(`Failed to list pending HITL: ${res.statusText}`);
  return res.json() as Promise<HITLPendingListResponse>;
}
