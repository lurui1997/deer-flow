"use client";

import {
  ActivityIcon,
  AlertCircleIcon,
  CheckCircleIcon,
  ClockIcon,
  LayersIcon,
  RefreshCwIcon,
  ServerIcon,
  ZapIcon,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useI18n } from "@/core/i18n/hooks";
import {
  useHealthStatus,
  useSystemStats,
  useThreads,
} from "@/core/observability";
import { formatTimeAgo } from "@/core/utils/datetime";
import { ThreadDetailDialog } from "./thread-detail-dialog";
import type { AgentThread } from "@/core/threads/types";

const statusIcons: Record<string, React.ReactNode> = {
  idle: <CheckCircleIcon className="h-4 w-4 text-green-500" />,
  busy: <ZapIcon className="h-4 w-4 text-blue-500" />,
  interrupted: <AlertCircleIcon className="h-4 w-4 text-yellow-500" />,
  error: <AlertCircleIcon className="h-4 w-4 text-red-500" />,
};

const statusColors: Record<string, string> = {
  idle: "bg-green-100 text-green-700",
  busy: "bg-blue-100 text-blue-700",
  interrupted: "bg-yellow-100 text-yellow-700",
  error: "bg-red-100 text-red-700",
};

export function ObservabilityDashboard() {
  const { t } = useI18n();
  const { health, isLoading: healthLoading } = useHealthStatus();
  const { stats, isLoading: statsLoading } = useSystemStats();
  const { threads, isLoading: threadsLoading } = useThreads();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedThread, setSelectedThread] = useState<AgentThread | null>(null);

  const filteredThreads = threads.filter((thread) => {
    const matchesSearch =
      thread.thread_id.toLowerCase().includes(search.toLowerCase()) ||
      (thread.values?.title ?? "")
        .toLowerCase()
        .includes(search.toLowerCase());
    const matchesStatus =
      statusFilter === "all" || thread.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="flex size-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold">{t.observability.title}</h1>
          <p className="text-muted-foreground mt-0.5 text-sm">
            {t.observability.description}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge
            variant={health.status === "healthy" ? "default" : "destructive"}
            className="text-sm"
          >
            <ServerIcon className="mr-1.5 h-4 w-4" />
            {health.status === "healthy"
              ? t.observability.healthy
              : t.observability.unhealthy}
          </Badge>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 gap-4 border-b p-6 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>{t.observability.totalThreads}</CardDescription>
            <CardTitle className="text-2xl">{stats.totalThreads}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-muted-foreground flex items-center text-xs">
              <LayersIcon className="mr-1 h-3 w-3" />
              {t.observability.activeConversations}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>{t.observability.activeRuns}</CardDescription>
            <CardTitle className="text-2xl">{stats.activeRuns}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-muted-foreground flex items-center text-xs">
              <ActivityIcon className="mr-1 h-3 w-3" />
              {t.observability.currentlyRunning}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>{t.observability.interrupted}</CardDescription>
            <CardTitle className="text-2xl">
              {stats.interruptedThreads}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-muted-foreground flex items-center text-xs">
              <AlertCircleIcon className="mr-1 h-3 w-3" />
              {t.observability.waitingForHITL}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>{t.observability.errors}</CardDescription>
            <CardTitle className="text-2xl">{stats.errorThreads}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-muted-foreground flex items-center text-xs">
              <AlertCircleIcon className="mr-1 h-3 w-3" />
              {t.observability.recentErrors}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Threads Table */}
      <div className="flex-1 overflow-hidden">
        <Tabs defaultValue="threads" className="h-full flex flex-col">
          <div className="flex items-center justify-between border-b px-6 py-3">
            <TabsList>
              <TabsTrigger value="threads">
                {t.observability.threadsTab}
              </TabsTrigger>
              <TabsTrigger value="health">
                {t.observability.healthTab}
              </TabsTrigger>
            </TabsList>
            <div className="flex items-center gap-2">
              <Input
                type="search"
                placeholder={t.observability.searchThreads}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-64"
              />
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-32">
                  <SelectValue placeholder={t.observability.filterByStatus} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t.observability.allStatuses}</SelectItem>
                  <SelectItem value="idle">{t.observability.statusIdle}</SelectItem>
                  <SelectItem value="busy">{t.observability.statusBusy}</SelectItem>
                  <SelectItem value="interrupted">
                    {t.observability.statusInterrupted}
                  </SelectItem>
                  <SelectItem value="error">{t.observability.statusError}</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <TabsContent value="threads" className="flex-1 overflow-hidden m-0 p-0">
            <div className="h-full overflow-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t.observability.threadId}</TableHead>
                    <TableHead>{t.observability.status}</TableHead>
                    <TableHead>{t.observability.title}</TableHead>
                    <TableHead>{t.observability.updatedAt}</TableHead>
                    <TableHead className="text-right">
                      {t.observability.actions}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {threadsLoading ? (
                    <TableRow>
                      <TableCell colSpan={5} className="h-32 text-center">
                        <RefreshCwIcon className="mx-auto h-6 w-6 animate-spin" />
                      </TableCell>
                    </TableRow>
                  ) : filteredThreads.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="h-32 text-center">
                        {t.observability.noThreads}
                      </TableCell>
                    </TableRow>
                  ) : (
                    filteredThreads.map((thread) => (
                      <TableRow key={thread.thread_id}>
                        <TableCell className="font-mono text-xs">
                          {thread.thread_id.slice(0, 8)}...
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            {statusIcons[thread.status]}
                            <Badge
                              variant="secondary"
                              className={statusColors[thread.status]}
                            >
                              {thread.status}
                            </Badge>
                          </div>
                        </TableCell>
                        <TableCell className="max-w-xs truncate">
                          {thread.values?.title ?? "-"}
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center text-xs">
                            <ClockIcon className="mr-1 h-3 w-3" />
                            {thread.updated_at
                              ? formatTimeAgo(thread.updated_at)
                              : "-"}
                          </div>
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setSelectedThread(thread)}
                          >
                            {t.observability.viewDetails}
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          </TabsContent>

          <TabsContent value="health" className="m-0 flex-1 overflow-auto p-6">
            <div className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>{t.observability.healthStatus}</CardTitle>
                  <CardDescription>
                    {t.observability.healthDescription}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span>{t.observability.serviceStatus}</span>
                      <Badge
                        variant={
                          health.status === "healthy" ? "default" : "destructive"
                        }
                      >
                        {health.status}
                      </Badge>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>{t.observability.serviceName}</span>
                      <span className="text-muted-foreground">
                        {health.service}
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>{t.observability.endpoints}</CardTitle>
                  <CardDescription>
                    {t.observability.endpointsDescription}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 text-sm">
                    <div className="flex items-center justify-between border-b py-2">
                      <code>/health</code>
                      <Badge variant="outline">GET</Badge>
                    </div>
                    <div className="flex items-center justify-between border-b py-2">
                      <code>/api/threads</code>
                      <Badge variant="outline">POST</Badge>
                    </div>
                    <div className="flex items-center justify-between border-b py-2">
                      <code>/api/hitl/pending</code>
                      <Badge variant="outline">GET</Badge>
                    </div>
                    <div className="flex items-center justify-between py-2">
                      <code>/api/skills</code>
                      <Badge variant="outline">GET</Badge>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>
      </div>

      {/* Thread Detail Dialog */}
      <ThreadDetailDialog
        thread={selectedThread}
        open={!!selectedThread}
        onOpenChange={(open) => !open && setSelectedThread(null)}
      />
    </div>
  );
}
