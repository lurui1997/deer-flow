"use client";

import {
  CpuIcon,
  DatabaseIcon,
  FolderIcon,
  HardDriveIcon,
  LayersIcon,
  MessageSquareIcon,
  PuzzleIcon,
  ShieldIcon,
  SparklesIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

export interface WorkerStateData {
  task_context?: {
    scheduler_run_id?: string;
    agent_name?: string;
    task_description?: string;
    is_plan_mode?: boolean;
    subagent_enabled?: boolean;
  };
  runtime?: {
    token_count?: number;
    token_limit?: number;
    current_model?: string;
    model_tier?: string;
    checkpoint_count?: number;
    start_time?: number;
  };
  skills?: {
    resident_skills?: Array<{ name: string; description: string }>;
    deferred_skills?: Array<{ name: string; description: string }>;
  };
  hitl?: {
    is_waiting?: boolean;
    hitl_type?: string;
    question?: string;
  };
  thread_data?: {
    workspace_path?: string;
    uploads_path?: string;
    outputs_path?: string;
  };
}

interface WorkerStatePanelProps {
  state: WorkerStateData;
  className?: string;
}

export function WorkerStatePanel({ state, className }: WorkerStatePanelProps) {
  const runtime = state.runtime;
  const taskContext = state.task_context;
  const skills = state.skills;
  const hitl = state.hitl;
  const threadData = state.thread_data;

  return (
    <Card className={cn("h-full", className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <CpuIcon className="h-5 w-5 text-primary" />
          <CardTitle className="text-lg">Worker State</CardTitle>
        </div>
        <CardDescription>ARW runtime state and configuration</CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        <ScrollArea className="h-[calc(100vh-300px)]">
          <div className="space-y-4 px-6 pb-6">
            {/* Task Context */}
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm font-medium">
                <SparklesIcon className="h-4 w-4 text-blue-500" />
                <span>Task Context</span>
                <Badge variant="secondary" className="text-xs">
                  Resident
                </Badge>
              </div>
              <div className="bg-muted rounded-lg p-3 space-y-2 text-sm">
                {taskContext?.scheduler_run_id && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Scheduler Run ID</span>
                    <span className="font-mono text-xs">
                      {taskContext.scheduler_run_id.slice(0, 16)}...
                    </span>
                  </div>
                )}
                {taskContext?.agent_name && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Agent</span>
                    <span>{taskContext.agent_name}</span>
                  </div>
                )}
                {taskContext?.task_description && (
                  <div className="pt-1">
                    <span className="text-muted-foreground block mb-1">Task</span>
                    <p className="text-xs line-clamp-2">
                      {taskContext.task_description}
                    </p>
                  </div>
                )}
                <div className="flex gap-2 pt-1">
                  {taskContext?.is_plan_mode && (
                    <Badge variant="outline" className="text-xs">
                      Plan Mode
                    </Badge>
                  )}
                  {taskContext?.subagent_enabled && (
                    <Badge variant="outline" className="text-xs">
                      Subagent
                    </Badge>
                  )}
                </div>
              </div>
            </div>

            <Separator />

            {/* Runtime Stats */}
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm font-medium">
                <LayersIcon className="h-4 w-4 text-green-500" />
                <span>Runtime Stats</span>
              </div>
              <div className="bg-muted rounded-lg p-3 space-y-2 text-sm">
                {runtime?.current_model && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Model</span>
                    <div className="flex items-center gap-2">
                      <span>{runtime.current_model}</span>
                      {runtime.model_tier && (
                        <Badge variant="secondary" className="text-xs">
                          {runtime.model_tier}
                        </Badge>
                      )}
                    </div>
                  </div>
                )}
                {runtime?.token_count !== undefined && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Tokens</span>
                    <span>
                      {runtime.token_count.toLocaleString()}
                      {runtime.token_limit && (
                        <span className="text-muted-foreground">
                          {" "}
                          / {runtime.token_limit.toLocaleString()}
                        </span>
                      )}
                    </span>
                  </div>
                )}
                {runtime?.checkpoint_count !== undefined && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Checkpoints</span>
                    <span>{runtime.checkpoint_count}</span>
                  </div>
                )}
                {runtime?.start_time && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Started</span>
                    <span className="text-xs">
                      {new Date(runtime.start_time * 1000).toLocaleTimeString()}
                    </span>
                  </div>
                )}
              </div>
            </div>

            <Separator />

            {/* Skills */}
            {skills && (
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <PuzzleIcon className="h-4 w-4 text-purple-500" />
                  <span>Skills</span>
                  <div className="flex gap-1">
                    {skills.resident_skills && (
                      <Badge variant="secondary" className="text-xs">
                        {skills.resident_skills.length} resident
                      </Badge>
                    )}
                    {skills.deferred_skills && (
                      <Badge variant="outline" className="text-xs">
                        {skills.deferred_skills.length} deferred
                      </Badge>
                    )}
                  </div>
                </div>
                <div className="space-y-1">
                  {skills.resident_skills?.slice(0, 3).map((skill, idx) => (
                    <div
                      key={idx}
                      className="bg-muted rounded px-2 py-1.5 text-xs flex items-center gap-2"
                    >
                      <span className="font-medium truncate">{skill.name}</span>
                      <span className="text-muted-foreground truncate flex-1">
                        {skill.description}
                      </span>
                    </div>
                  ))}
                  {(skills.resident_skills?.length || 0) > 3 && (
                    <div className="text-xs text-muted-foreground text-center py-1">
                      +{(skills.resident_skills?.length || 0) - 3} more
                    </div>
                  )}
                </div>
              </div>
            )}

            <Separator />

            {/* Thread Data */}
            {threadData && (
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <FolderIcon className="h-4 w-4 text-orange-500" />
                  <span>Thread Data</span>
                </div>
                <div className="space-y-1 text-xs">
                  {threadData.workspace_path && (
                    <div className="flex items-center gap-2 bg-muted rounded px-2 py-1.5">
                      <HardDriveIcon className="h-3 w-3 text-muted-foreground" />
                      <span className="text-muted-foreground">workspace</span>
                    </div>
                  )}
                  {threadData.uploads_path && (
                    <div className="flex items-center gap-2 bg-muted rounded px-2 py-1.5">
                      <DatabaseIcon className="h-3 w-3 text-muted-foreground" />
                      <span className="text-muted-foreground">uploads</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* HITL Status */}
            {hitl?.is_waiting && (
              <>
                <Separator />
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <MessageSquareIcon className="h-4 w-4 text-yellow-500" />
                    <span>HITL Waiting</span>
                    <Badge variant="destructive" className="text-xs">
                      {hitl.hitl_type}
                    </Badge>
                  </div>
                  {hitl.question && (
                    <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-sm">
                      <p className="text-yellow-800">{hitl.question}</p>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
