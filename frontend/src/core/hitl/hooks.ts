import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getBulkHITLStatus,
  getHITLStatus,
  listPendingHITL,
  submitHITLResponse,
} from "./api";
import type { HITLResponseRequest } from "./types";

export function useHITLStatus(threadId: string | null) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["hitl", "status", threadId],
    queryFn: () => (threadId ? getHITLStatus(threadId) : Promise.reject("No thread ID")),
    enabled: !!threadId,
    refetchInterval: 5000, // Auto-refresh every 5 seconds
  });
  return { status: data ?? null, isLoading, error, refetch };
}

export function useBulkHITLStatus(threadIds: string[]) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["hitl", "bulk-status", threadIds],
    queryFn: () => getBulkHITLStatus(threadIds),
    enabled: threadIds.length > 0,
    refetchInterval: 5000,
  });
  return { statuses: data?.results ?? {}, pendingCount: data?.pending_count ?? 0, isLoading, error };
}

export function usePendingHITL(limit: number = 100, offset: number = 0) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["hitl", "pending", limit, offset],
    queryFn: () => listPendingHITL(limit, offset),
    refetchInterval: 5000,
  });
  return { pending: data?.pending ?? [], total: data?.total ?? 0, isLoading, error };
}

export function useSubmitHITLResponse() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ threadId, request }: { threadId: string; request: HITLResponseRequest }) =>
      submitHITLResponse(threadId, request),
    onSuccess: (_data, { threadId }) => {
      void queryClient.invalidateQueries({ queryKey: ["hitl", "status", threadId] });
      void queryClient.invalidateQueries({ queryKey: ["hitl", "pending"] });
      void queryClient.invalidateQueries({ queryKey: ["hitl", "bulk-status"] });
    },
  });
}
