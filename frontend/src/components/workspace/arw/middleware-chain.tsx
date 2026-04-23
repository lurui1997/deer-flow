"use client";

import {
  ArrowRightIcon,
  CheckCircleIcon,
  CircleIcon,
  CpuIcon,
  DatabaseIcon,
  FilterIcon,
  FolderIcon,
  LayersIcon,
  MessageSquareIcon,
  PuzzleIcon,
  RefreshCwIcon,
  RocketIcon,
  ShieldIcon,
  SparklesIcon,
  ZapIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export type MiddlewareStatus = "pending" | "running" | "completed" | "error";

export interface MiddlewareInfo {
  id: string;
  name: string;
  description: string;
  icon: React.ReactNode;
  status: MiddlewareStatus;
  duration?: number;
  error?: string;
}

interface MiddlewareChainProps {
  middlewares: MiddlewareInfo[];
  className?: string;
}

const defaultMiddlewares: MiddlewareInfo[] = [
  {
    id: "task-context",
    name: "TaskContextMiddleware",
    description: "Inject ARC task requirements",
    icon: <SparklesIcon className="h-4 w-4" />,
    status: "pending",
  },
  {
    id: "thread-data",
    name: "ThreadDataMiddleware",
    description: "Create workspace directories",
    icon: <FolderIcon className="h-4 w-4" />,
    status: "pending",
  },
  {
    id: "skill-loader",
    name: "SkillLoaderMiddleware",
    description: "Two-tier skill loading",
    icon: <PuzzleIcon className="h-4 w-4" />,
    status: "pending",
  },
  {
    id: "uploads",
    name: "UploadsMiddleware",
    description: "Handle file uploads",
    icon: <DatabaseIcon className="h-4 w-4" />,
    status: "pending",
  },
  {
    id: "sandbox",
    name: "SandboxMiddleware",
    description: "Sandbox execution",
    icon: <ShieldIcon className="h-4 w-4" />,
    status: "pending",
  },
  {
    id: "knowledge",
    name: "KnowledgeRetrievalMiddleware",
    description: "RAG/MCP retrieval",
    icon: <LayersIcon className="h-4 w-4" />,
    status: "pending",
  },
  {
    id: "checkpoint",
    name: "CheckpointMiddleware",
    description: "Pre-run snapshots",
    icon: <RefreshCwIcon className="h-4 w-4" />,
    status: "pending",
  },
  {
    id: "hitl",
    name: "HITLMiddleware",
    description: "HITL platform bridging",
    icon: <MessageSquareIcon className="h-4 w-4" />,
    status: "pending",
  },
  {
    id: "event-report",
    name: "EventReportMiddleware",
    description: "Event reporting",
    icon: <RocketIcon className="h-4 w-4" />,
    status: "pending",
  },
  {
    id: "guardrail",
    name: "GuardrailMiddleware",
    description: "Output guardrails",
    icon: <FilterIcon className="h-4 w-4" />,
    status: "pending",
  },
];

export function MiddlewareChain({ middlewares, className }: MiddlewareChainProps) {
  const items = middlewares.length > 0 ? middlewares : defaultMiddlewares;

  return (
    <Card className={cn("h-full", className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <LayersIcon className="h-5 w-5 text-primary" />
            <CardTitle className="text-lg">Middleware Chain</CardTitle>
          </div>
          <Badge variant="secondary" className="text-xs">
            {items.length} layers
          </Badge>
        </div>
        <CardDescription>ARW 10-layer middleware execution pipeline</CardDescription>
      </CardHeader>
      <CardContent className="overflow-y-auto max-h-[400px]">
        <div className="space-y-1">
          {items.map((middleware, index) => (
            <MiddlewareItem
              key={middleware.id}
              middleware={middleware}
              index={index}
              isLast={index === items.length - 1}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

interface MiddlewareItemProps {
  middleware: MiddlewareInfo;
  index: number;
  isLast: boolean;
}

function MiddlewareItem({ middleware, index, isLast }: MiddlewareItemProps) {
  const statusColors: Record<MiddlewareStatus, string> = {
    pending: "bg-muted text-muted-foreground",
    running: "bg-blue-100 text-blue-700 border-blue-300",
    completed: "bg-green-100 text-green-700 border-green-300",
    error: "bg-red-100 text-red-700 border-red-300",
  };

  const statusIcons: Record<MiddlewareStatus, React.ReactNode> = {
    pending: <CircleIcon className="h-4 w-4 text-muted-foreground" />,
    running: <RefreshCwIcon className="h-4 w-4 animate-spin text-blue-600" />,
    completed: <CheckCircleIcon className="h-4 w-4 text-green-600" />,
    error: <ZapIcon className="h-4 w-4 text-red-600" />,
  };

  return (
    <div className="relative">
      <div
        className={cn(
          "flex items-center gap-3 rounded-lg border p-3 transition-all",
          statusColors[middleware.status],
          middleware.status === "running" && "ring-2 ring-blue-200"
        )}
      >
        {/* Index */}
        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white/50 text-xs font-medium">
          {index + 1}
        </div>

        {/* Icon */}
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-white/50">
          {middleware.icon}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm truncate">{middleware.name}</span>
            <Badge variant="outline" className="text-xs capitalize shrink-0">
              {middleware.status}
            </Badge>
          </div>
          <p className="text-xs opacity-80 truncate">{middleware.description}</p>
        </div>

        {/* Status & Duration */}
        <div className="flex items-center gap-2">
          {middleware.duration !== undefined && middleware.status === "completed" && (
            <span className="text-xs opacity-60">{middleware.duration}ms</span>
          )}
          {statusIcons[middleware.status]}
        </div>
      </div>

      {/* Connector */}
      {!isLast && (
        <div className="flex justify-center py-1">
          <ArrowRightIcon className="h-4 w-4 rotate-90 text-muted-foreground opacity-50" />
        </div>
      )}
    </div>
  );
}

export function CompactMiddlewareChain({ middlewares, className }: MiddlewareChainProps) {
  const items = middlewares.length > 0 ? middlewares : defaultMiddlewares;
  const completedCount = items.filter((m) => m.status === "completed").length;
  const runningItem = items.find((m) => m.status === "running");

  return (
    <Card className={cn(className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Middleware Chain</CardTitle>
          <Badge variant="secondary" className="text-xs">
            {completedCount}/{items.length}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        {runningItem ? (
          <div className="flex items-center gap-3 rounded-lg border bg-blue-50 p-3">
            <RefreshCwIcon className="h-4 w-4 animate-spin text-blue-600" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{runningItem.name}</p>
              <p className="text-xs text-muted-foreground truncate">
                {runningItem.description}
              </p>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-green-500 transition-all"
                style={{ width: `${(completedCount / items.length) * 100}%` }}
              />
            </div>
            <span className="text-xs text-muted-foreground">
              {completedCount}/{items.length}
            </span>
          </div>
        )}

        {/* Compact Status Grid */}
        <div className="grid grid-cols-10 gap-1 mt-3">
          {items.map((middleware, idx) => (
            <div
              key={middleware.id}
              className={cn(
                "h-1.5 rounded-full transition-all",
                middleware.status === "completed" && "bg-green-500",
                middleware.status === "running" && "bg-blue-500 animate-pulse",
                middleware.status === "error" && "bg-red-500",
                middleware.status === "pending" && "bg-muted"
              )}
              title={`${idx + 1}. ${middleware.name}`}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
