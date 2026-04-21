"use client";

import {
  ActivityIcon,
  AlertCircleIcon,
  CheckCircleIcon,
  ClockIcon,
  CpuIcon,
  DatabaseIcon,
  LayersIcon,
  MessageSquareIcon,
  PlayIcon,
  PuzzleIcon,
  RefreshCwIcon,
  RocketIcon,
  ShieldIcon,
  SparklesIcon,
  StopCircleIcon,
  ZapIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

export type TaskEventType =
  | "task_started"
  | "middleware_init"
  | "model_call"
  | "tool_call"
  | "checkpoint"
  | "hitl_requested"
  | "hitl_resolved"
  | "task_completed"
  | "task_failed"
  | "heartbeat";

export type TaskEventStatus = "info" | "success" | "warning" | "error";

export interface TaskEvent {
  id: string;
  type: TaskEventType;
  status: TaskEventStatus;
  message: string;
  timestamp: number;
  duration?: number;
  metadata?: Record<string, unknown>;
}

interface TaskExecutionTimelineProps {
  events: TaskEvent[];
  className?: string;
  isRunning?: boolean;
}

const eventIcons: Record<TaskEventType, React.ReactNode> = {
  task_started: <PlayIcon className="h-4 w-4" />,
  middleware_init: <LayersIcon className="h-4 w-4" />,
  model_call: <CpuIcon className="h-4 w-4" />,
  tool_call: <PuzzleIcon className="h-4 w-4" />,
  checkpoint: <DatabaseIcon className="h-4 w-4" />,
  hitl_requested: <MessageSquareIcon className="h-4 w-4" />,
  hitl_resolved: <CheckCircleIcon className="h-4 w-4" />,
  task_completed: <CheckCircleIcon className="h-4 w-4" />,
  task_failed: <AlertCircleIcon className="h-4 w-4" />,
  heartbeat: <ActivityIcon className="h-4 w-4" />,
};

const statusColors: Record<TaskEventStatus, string> = {
  info: "bg-blue-100 text-blue-700 border-blue-200",
  success: "bg-green-100 text-green-700 border-green-200",
  warning: "bg-yellow-100 text-yellow-700 border-yellow-200",
  error: "bg-red-100 text-red-700 border-red-200",
};

const statusDotColors: Record<TaskEventStatus, string> = {
  info: "bg-blue-500",
  success: "bg-green-500",
  warning: "bg-yellow-500",
  error: "bg-red-500",
};

export function TaskExecutionTimeline({
  events,
  className,
  isRunning = false,
}: TaskExecutionTimelineProps) {
  const sortedEvents = [...events].sort((a, b) => b.timestamp - a.timestamp);

  return (
    <Card className={cn("h-full", className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ActivityIcon className="h-5 w-5 text-primary" />
            <CardTitle className="text-lg">Execution Timeline</CardTitle>
          </div>
          <div className="flex items-center gap-2">
            {isRunning && (
              <Badge variant="secondary" className="text-xs">
                <RefreshCwIcon className="mr-1 h-3 w-3 animate-spin" />
                Running
              </Badge>
            )}
            <Badge variant="outline" className="text-xs">
              {events.length} events
            </Badge>
          </div>
        </div>
        <CardDescription>Task execution events and checkpoints</CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        <ScrollArea className="h-[calc(100vh-300px)]">
          <div className="space-y-0 px-6 pb-6">
            {sortedEvents.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <ClockIcon className="mx-auto h-8 w-8 mb-2 opacity-50" />
                <p className="text-sm">No events yet</p>
              </div>
            ) : (
              sortedEvents.map((event, index) => (
                <TimelineItem
                  key={event.id}
                  event={event}
                  isLast={index === sortedEvents.length - 1}
                />
              ))
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

interface TimelineItemProps {
  event: TaskEvent;
  isLast: boolean;
}

function TimelineItem({ event, isLast }: TimelineItemProps) {
  return (
    <div className="relative flex gap-4 pb-6">
      {/* Timeline line */}
      {!isLast && (
        <div className="absolute left-[19px] top-8 bottom-0 w-px bg-border" />
      )}

      {/* Icon */}
      <div
        className={cn(
          "relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-2",
          statusColors[event.status]
        )}
      >
        {eventIcons[event.type]}
      </div>

      {/* Content */}
      <div className="flex-1 pt-1">
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-medium text-sm">{formatEventType(event.type)}</span>
              <Badge
                variant="outline"
                className={cn("text-xs capitalize", statusDotColors[event.status])}
              >
                {event.status}
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground mt-0.5">{event.message}</p>

            {/* Metadata */}
            {event.metadata && Object.keys(event.metadata).length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {Object.entries(event.metadata).map(([key, value]) => (
                  <div
                    key={key}
                    className="bg-muted rounded px-2 py-1 text-xs flex items-center gap-1"
                  >
                    <span className="text-muted-foreground">{key}:</span>
                    <span className="font-mono">
                      {typeof value === "object" ? JSON.stringify(value) : String(value)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Timestamp */}
          <div className="text-right shrink-0">
            <span className="text-xs text-muted-foreground">
              {new Date(event.timestamp).toLocaleTimeString()}
            </span>
            {event.duration !== undefined && (
              <div className="text-xs text-muted-foreground">{event.duration}ms</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function formatEventType(type: TaskEventType): string {
  return type
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

// Compact version for dashboard
export function CompactTaskExecutionTimeline({
  events,
  className,
  isRunning = false,
}: TaskExecutionTimelineProps) {
  const sortedEvents = [...events].sort((a, b) => b.timestamp - a.timestamp);
  const recentEvents = sortedEvents.slice(0, 5);

  return (
    <Card className={cn(className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Recent Events</CardTitle>
          {isRunning && (
            <RefreshCwIcon className="h-4 w-4 animate-spin text-blue-500" />
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {recentEvents.length === 0 ? (
            <div className="text-center py-4 text-muted-foreground text-sm">
              No events yet
            </div>
          ) : (
            recentEvents.map((event) => (
              <div
                key={event.id}
                className="flex items-center gap-3 rounded-lg border p-2"
              >
                <div
                  className={cn(
                    "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
                    statusColors[event.status]
                  )}
                >
                  {eventIcons[event.type]}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{formatEventType(event.type)}</p>
                  <p className="text-xs text-muted-foreground truncate">{event.message}</p>
                </div>
                <span className="text-xs text-muted-foreground shrink-0">
                  {new Date(event.timestamp).toLocaleTimeString()}
                </span>
              </div>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
}
