export interface HealthStatus {
  status: "healthy" | "unhealthy" | "degraded";
  service: string;
  timestamp?: string;
}

export interface ThreadRun {
  run_id: string;
  thread_id: string;
  assistant_id: string | null;
  status: "pending" | "running" | "success" | "error" | "timeout" | "interrupted";
  metadata: Record<string, unknown>;
  multitask_strategy: string;
  created_at: string;
  updated_at: string;
}

export interface ThreadState {
  values: Record<string, unknown>;
  next: string[];
  metadata: Record<string, unknown>;
  checkpoint: {
    id: string;
    ts: string;
  };
  checkpoint_id: string | null;
  parent_checkpoint_id: string | null;
  created_at: string | null;
  tasks: Array<{ id: string; name: string }>;
}

export interface SystemStats {
  totalThreads: number;
  activeRuns: number;
  pendingHITL: number;
  recentErrors: number;
}

export interface TracingConfig {
  langsmith?: {
    enabled: boolean;
    project: string;
    endpoint: string;
    is_configured: boolean;
  };
  langfuse?: {
    enabled: boolean;
    host: string;
    is_configured: boolean;
  };
  enabled_providers: string[];
}
