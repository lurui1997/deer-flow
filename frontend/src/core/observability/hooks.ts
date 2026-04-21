import { useQuery } from "@tanstack/react-query";

import { getHealthStatus, listThreads, listThreadRuns, getThreadState } from "./api";

export function useHealthStatus() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["observability", "health"],
    queryFn: () => getHealthStatus(),
    refetchInterval: 30000, // Refresh every 30 seconds
  });
  return { health: data ?? { status: "unknown", service: "deer-flow-gateway" }, isLoading, error };
}

export function useThreads() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["observability", "threads"],
    queryFn: () => listThreads(),
    refetchInterval: 10000,
  });
  return { threads: data ?? [], isLoading, error };
}

export function useThreadRuns(threadId: string | null) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["observability", "thread-runs", threadId],
    queryFn: () => (threadId ? listThreadRuns(threadId) : Promise.reject("No thread ID")),
    enabled: !!threadId,
    refetchInterval: 5000,
  });
  return { runs: data ?? [], isLoading, error };
}

export function useThreadState(threadId: string | null) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["observability", "thread-state", threadId],
    queryFn: () => (threadId ? getThreadState(threadId) : Promise.reject("No thread ID")),
    enabled: !!threadId,
    refetchInterval: 5000,
  });
  return { state: data ?? null, isLoading, error };
}

export function useSystemStats() {
  const { threads, isLoading: threadsLoading } = useThreads();
  
  const stats = {
    totalThreads: threads.length,
    activeRuns: threads.filter(t => t.status === "busy").length,
    interruptedThreads: threads.filter(t => t.status === "interrupted").length,
    errorThreads: threads.filter(t => t.status === "error").length,
  };
  
  return { stats, isLoading: threadsLoading };
}
