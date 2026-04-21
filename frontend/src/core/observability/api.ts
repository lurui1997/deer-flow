import { getBackendBaseURL } from "@/core/config";
import type { AgentThread } from "@/core/threads/types";

import type { HealthStatus, ThreadRun, ThreadState, TracingConfig } from "./types";

export async function getHealthStatus(): Promise<HealthStatus> {
  const res = await fetch(`${getBackendBaseURL()}/health`);
  if (!res.ok) throw new Error(`Failed to get health status: ${res.statusText}`);
  return res.json() as Promise<HealthStatus>;
}

export async function listThreads(): Promise<AgentThread[]> {
  const res = await fetch(`${getBackendBaseURL()}/api/threads/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ limit: 100, offset: 0 }),
  });
  if (!res.ok) throw new Error(`Failed to list threads: ${res.statusText}`);
  return res.json() as Promise<AgentThread[]>;
}

export async function getThreadState(threadId: string): Promise<ThreadState> {
  const res = await fetch(`${getBackendBaseURL()}/api/threads/${threadId}/state`);
  if (!res.ok) throw new Error(`Failed to get thread state: ${res.statusText}`);
  return res.json() as Promise<ThreadState>;
}

export async function listThreadRuns(threadId: string): Promise<ThreadRun[]> {
  const res = await fetch(`${getBackendBaseURL()}/api/threads/${threadId}/runs`);
  if (!res.ok) throw new Error(`Failed to list thread runs: ${res.statusText}`);
  return res.json() as Promise<ThreadRun[]>;
}

export async function getTracingConfig(): Promise<TracingConfig> {
  // This endpoint would need to be added to backend
  // For now, return a mock response
  return {
    enabled_providers: [],
  };
}
