export interface HITLClarification {
  tool_call_id: string;
  question: string;
  clarification_type: "missing_info" | "ambiguous_requirement" | "approach_choice" | "risk_confirmation" | "suggestion";
  context: string | null;
  options: string[] | null;
}

export interface HITLStatus {
  thread_id: string;
  has_pending_hitl: boolean;
  status: "idle" | "busy" | "interrupted" | "error" | "not_found";
  clarification: HITLClarification | null;
  checkpoint_id: string | null;
  timestamp: string;
}

export interface HITLResponseRequest {
  response: string;
  tool_call_id?: string | null;
  as_node?: string;
}

export interface HITLResponseResult {
  success: boolean;
  thread_id: string;
  message: string;
  checkpoint_id: string | null;
  timestamp: string;
}

export interface HITLPendingItem {
  thread_id: string;
  checkpoint_id: string | null;
  status: string;
  clarification: HITLClarification;
  created_at: string | null;
}

export interface HITLPendingListResponse {
  pending: HITLPendingItem[];
  total: number;
}

export interface HITLBulkStatusRequest {
  thread_ids: string[];
}

export interface HITLBulkStatusResponse {
  results: Record<string, HITLStatus>;
  pending_count: number;
}
