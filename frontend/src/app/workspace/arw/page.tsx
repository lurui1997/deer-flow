"use client";

import { useState, useEffect } from "react";
import {
  CpuIcon,
  LayersIcon,
  ActivityIcon,
  SettingsIcon,
  PlayIcon,
  PauseIcon,
  RotateCcwIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { useI18n } from "@/core/i18n/hooks";

import { WorkerStatePanel, WorkerStateData } from "@/components/workspace/arw/worker-state-panel";
import { MiddlewareChain, MiddlewareInfo } from "@/components/workspace/arw/middleware-chain";
import { TaskExecutionTimeline, TaskEvent } from "@/components/workspace/arw/task-execution-timeline";

// Demo data for initial state
const demoWorkerState: WorkerStateData = {
  task_context: {
    scheduler_run_id: "master-pod-001-abc123",
    agent_name: "code-review-agent",
    task_description: "Review the pull request #42 and provide feedback on code quality, potential bugs, and security issues.",
    is_plan_mode: true,
    subagent_enabled: false,
  },
  runtime: {
    token_count: 2450,
    token_limit: 4000,
    current_model: "gpt-4o",
    model_tier: "premium",
    checkpoint_count: 3,
    start_time: Date.now() / 1000 - 120,
  },
  skills: {
    resident_skills: [
      { name: "code_review", description: "Review code for quality and bugs" },
      { name: "security_scan", description: "Scan for security vulnerabilities" },
      { name: "test_generator", description: "Generate test cases" },
    ],
    deferred_skills: [
      { name: "performance_analysis", description: "Analyze code performance" },
      { name: "docs_generator", description: "Generate documentation" },
    ],
  },
  thread_data: {
    workspace_path: "/mnt/user-data/workspace/thread-001",
    uploads_path: "/mnt/user-data/uploads/thread-001",
    outputs_path: "/mnt/user-data/outputs/thread-001",
  },
};

const demoMiddlewares: MiddlewareInfo[] = [
  { id: "1", name: "TaskContextMiddleware", description: "Inject ARC task requirements", icon: <LayersIcon className="h-4 w-4" />, status: "completed", duration: 12 },
  { id: "2", name: "ThreadDataMiddleware", description: "Create workspace directories", icon: <LayersIcon className="h-4 w-4" />, status: "completed", duration: 8 },
  { id: "3", name: "SkillLoaderMiddleware", description: "Two-tier skill loading", icon: <LayersIcon className="h-4 w-4" />, status: "completed", duration: 45 },
  { id: "4", name: "UploadsMiddleware", description: "Handle file uploads", icon: <LayersIcon className="h-4 w-4" />, status: "completed", duration: 5 },
  { id: "5", name: "SandboxMiddleware", description: "Sandbox execution", icon: <LayersIcon className="h-4 w-4" />, status: "completed", duration: 15 },
  { id: "6", name: "KnowledgeRetrievalMiddleware", description: "RAG/MCP retrieval", icon: <LayersIcon className="h-4 w-4" />, status: "running" },
  { id: "7", name: "CheckpointMiddleware", description: "Pre-run snapshots", icon: <LayersIcon className="h-4 w-4" />, status: "pending" },
  { id: "8", name: "HITLMiddleware", description: "HITL platform bridging", icon: <LayersIcon className="h-4 w-4" />, status: "pending" },
  { id: "9", name: "EventReportMiddleware", description: "Event reporting", icon: <LayersIcon className="h-4 w-4" />, status: "pending" },
  { id: "10", name: "GuardrailMiddleware", description: "Output guardrails", icon: <LayersIcon className="h-4 w-4" />, status: "pending" },
];

const demoEvents: TaskEvent[] = [
  {
    id: "1",
    type: "task_started",
    status: "success",
    message: "Task started with agent: code-review-agent",
    timestamp: Date.now() - 120000,
    metadata: { agent_name: "code-review-agent", is_plan_mode: true },
  },
  {
    id: "2",
    type: "middleware_init",
    status: "success",
    message: "TaskContextMiddleware initialized",
    timestamp: Date.now() - 115000,
    duration: 12,
  },
  {
    id: "3",
    type: "middleware_init",
    status: "success",
    message: "ThreadDataMiddleware initialized",
    timestamp: Date.now() - 110000,
    duration: 8,
  },
  {
    id: "4",
    type: "middleware_init",
    status: "success",
    message: "SkillLoaderMiddleware loaded 3 resident skills",
    timestamp: Date.now() - 105000,
    duration: 45,
    metadata: { resident_count: 3, deferred_count: 2 },
  },
  {
    id: "5",
    type: "checkpoint",
    status: "success",
    message: "Pre-run checkpoint created",
    timestamp: Date.now() - 100000,
    metadata: { checkpoint_id: "cp-001" },
  },
  {
    id: "6",
    type: "model_call",
    status: "success",
    message: "LLM inference completed",
    timestamp: Date.now() - 80000,
    duration: 1200,
    metadata: { model: "gpt-4o", tokens: 450 },
  },
  {
    id: "7",
    type: "tool_call",
    status: "success",
    message: "Executed tool: code_review",
    timestamp: Date.now() - 60000,
    duration: 2500,
    metadata: { tool_name: "code_review" },
  },
  {
    id: "8",
    type: "heartbeat",
    status: "info",
    message: "Worker heartbeat",
    timestamp: Date.now() - 30000,
    metadata: { token_count: 2450 },
  },
];

export default function ARWPage() {
  const { t } = useI18n();
  const [activeTab, setActiveTab] = useState("overview");
  const [isSimulating, setIsSimulating] = useState(false);
  const [workerState, setWorkerState] = useState<WorkerStateData>(demoWorkerState);
  const [middlewares, setMiddlewares] = useState<MiddlewareInfo[]>(demoMiddlewares);
  const [events, setEvents] = useState<TaskEvent[]>(demoEvents);

  // Simulation effect
  useEffect(() => {
    if (!isSimulating) return;

    const interval = setInterval(() => {
      // Update middleware status randomly
      setMiddlewares((prev) => {
        const runningIndex = prev.findIndex((m) => m.status === "running");
        if (runningIndex >= 0 && Math.random() > 0.5) {
          const next = [...prev];
          next[runningIndex] = { ...next[runningIndex], status: "completed", duration: Math.floor(Math.random() * 50) + 10 };
          if (runningIndex < next.length - 1) {
            next[runningIndex + 1] = { ...next[runningIndex + 1], status: "running" };
          }
          return next;
        }
        return prev;
      });

      // Add heartbeat events
      if (Math.random() > 0.7) {
        setEvents((prev) => [
          {
            id: Date.now().toString(),
            type: "heartbeat",
            status: "info",
            message: "Worker heartbeat",
            timestamp: Date.now(),
            metadata: { token_count: workerState.runtime?.token_count },
          },
          ...prev,
        ]);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [isSimulating, workerState.runtime?.token_count]);

  const handleStartSimulation = () => {
    setIsSimulating(true);
    setEvents((prev) => [
      {
        id: Date.now().toString(),
        type: "task_started",
        status: "success",
        message: "Simulation started",
        timestamp: Date.now(),
      },
      ...prev,
    ]);
  };

  const handleStopSimulation = () => {
    setIsSimulating(false);
    setEvents((prev) => [
      {
        id: Date.now().toString(),
        type: "task_completed",
        status: "success",
        message: "Simulation stopped",
        timestamp: Date.now(),
      },
      ...prev,
    ]);
  };

  const handleReset = () => {
    setIsSimulating(false);
    setMiddlewares(demoMiddlewares);
    setEvents(demoEvents);
    setWorkerState(demoWorkerState);
  };

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div>
          <div className="flex items-center gap-2">
            <CpuIcon className="h-6 w-6 text-primary" />
            <h1 className="text-2xl font-semibold">Agent Runtime Worker</h1>
            <Badge variant="secondary" className="text-xs">ARW</Badge>
          </div>
          <p className="text-muted-foreground mt-1">
            Monitor and manage Agent Runtime Worker instances
          </p>
        </div>
        <div className="flex items-center gap-2">
          {!isSimulating ? (
            <Button onClick={handleStartSimulation}>
              <PlayIcon className="mr-2 h-4 w-4" />
              Start Simulation
            </Button>
          ) : (
            <Button variant="outline" onClick={handleStopSimulation}>
              <PauseIcon className="mr-2 h-4 w-4" />
              Stop
            </Button>
          )}
          <Button variant="ghost" size="icon" onClick={handleReset}>
            <RotateCcwIcon className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full flex flex-col">
          <div className="border-b px-6 py-2">
            <TabsList>
              <TabsTrigger value="overview">
                <ActivityIcon className="mr-2 h-4 w-4" />
                Overview
              </TabsTrigger>
              <TabsTrigger value="state">
                <LayersIcon className="mr-2 h-4 w-4" />
                Worker State
              </TabsTrigger>
              <TabsTrigger value="timeline">
                <CpuIcon className="mr-2 h-4 w-4" />
                Execution Timeline
              </TabsTrigger>
            </TabsList>
          </div>

          <TabsContent value="overview" className="flex-1 overflow-hidden m-0 p-6">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-full">
              {/* Left Column */}
              <div className="lg:col-span-2 space-y-6">
                {/* Stats Cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <Card>
                    <CardHeader className="pb-2">
                      <CardDescription>Status</CardDescription>
                      <div className="flex items-center gap-2">
                        <div className={cn("h-2 w-2 rounded-full", isSimulating ? "bg-green-500 animate-pulse" : "bg-yellow-500")} />
                        <CardTitle className="text-lg">{isSimulating ? "Running" : "Idle"}</CardTitle>
                      </div>
                    </CardHeader>
                  </Card>
                  <Card>
                    <CardHeader className="pb-2">
                      <CardDescription>Middlewares</CardDescription>
                      <CardTitle className="text-lg">
                        {middlewares.filter((m) => m.status === "completed").length} / {middlewares.length}
                      </CardTitle>
                    </CardHeader>
                  </Card>
                  <Card>
                    <CardHeader className="pb-2">
                      <CardDescription>Events</CardDescription>
                      <CardTitle className="text-lg">{events.length}</CardTitle>
                    </CardHeader>
                  </Card>
                  <Card>
                    <CardHeader className="pb-2">
                      <CardDescription>Runtime</CardDescription>
                      <CardTitle className="text-lg">{workerState.runtime?.current_model || "-"}</CardTitle>
                    </CardHeader>
                  </Card>
                </div>

                {/* Middleware Chain */}
                <MiddlewareChain middlewares={middlewares} />
              </div>

              {/* Right Column */}
              <div className="space-y-6">
                <WorkerStatePanel state={workerState} />
              </div>
            </div>
          </TabsContent>

          <TabsContent value="state" className="flex-1 overflow-hidden m-0 p-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 h-full">
              <WorkerStatePanel state={workerState} />
              <Card>
                <CardHeader>
                  <CardTitle>State Schema</CardTitle>
                  <CardDescription>WorkerState type definitions</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="bg-muted rounded-lg p-4 font-mono text-xs space-y-2">
                    <div className="text-blue-600">interface WorkerState {'{'}</div>
                    <div className="pl-4 text-green-600">// Resident Zone (never compacted)</div>
                    <div className="pl-4">task_context: TaskContext;</div>
                    <div className="pl-4 text-green-600 mt-2">// Knowledge Zone (priority retention)</div>
                    <div className="pl-4">retrieved_knowledge: KnowledgeItem[];</div>
                    <div className="pl-4 text-green-600 mt-2">// Working Zone (compacted at 80%)</div>
                    <div className="pl-4">messages: BaseMessage[];</div>
                    <div className="pl-4 text-green-600 mt-2">// ARW Specific</div>
                    <div className="pl-4">skills: SkillRegistryState;</div>
                    <div className="pl-4">hitl: HITLState;</div>
                    <div className="pl-4">runtime: RuntimeStats;</div>
                    <div>{'}'}</div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="timeline" className="flex-1 overflow-hidden m-0 p-6">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-full">
              <div className="lg:col-span-2">
                <TaskExecutionTimeline events={events} isRunning={isSimulating} />
              </div>
              <div>
                <Card>
                  <CardHeader>
                    <CardTitle>Event Types</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2 text-sm">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline">task_started</Badge>
                        <span className="text-muted-foreground">Task initialization</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant="outline">middleware_init</Badge>
                        <span className="text-muted-foreground">Middleware setup</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant="outline">model_call</Badge>
                        <span className="text-muted-foreground">LLM inference</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant="outline">tool_call</Badge>
                        <span className="text-muted-foreground">Tool execution</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant="outline">checkpoint</Badge>
                        <span className="text-muted-foreground">State checkpoint</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant="outline">hitl_requested</Badge>
                        <span className="text-muted-foreground">HITL trigger</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant="outline">task_completed</Badge>
                        <span className="text-muted-foreground">Task finished</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

import { cn } from "@/lib/utils";
