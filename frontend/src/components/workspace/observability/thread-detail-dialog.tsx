"use client";

import {
  ClockIcon,
  CodeIcon,
  ActivityIcon,
  CheckCircleIcon,
  XCircleIcon,
  AlertCircleIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useI18n } from "@/core/i18n/hooks";
import { useThreadRuns, useThreadState } from "@/core/observability";
import type { AgentThread } from "@/core/threads/types";

interface ThreadDetailDialogProps {
  thread: AgentThread | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const statusIcons: Record<string, React.ReactNode> = {
  pending: <ClockIcon className="h-4 w-4 text-yellow-500" />,
  running: <ActivityIcon className="h-4 w-4 text-blue-500" />,
  success: <CheckCircleIcon className="h-4 w-4 text-green-500" />,
  error: <XCircleIcon className="h-4 w-4 text-red-500" />,
  interrupted: <AlertCircleIcon className="h-4 w-4 text-orange-500" />,
  timeout: <ClockIcon className="h-4 w-4 text-gray-500" />,
};

export function ThreadDetailDialog({
  thread,
  open,
  onOpenChange,
}: ThreadDetailDialogProps) {
  const { t } = useI18n();
  const { state } = useThreadState(thread?.thread_id ?? null);
  const { runs } = useThreadRuns(thread?.thread_id ?? null);

  if (!thread) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {t.observability.threadDetails}
            <Badge variant="secondary">{thread.thread_id.slice(0, 8)}...</Badge>
          </DialogTitle>
          <DialogDescription>
            {thread.values?.title ?? t.observability.noTitle}
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="info" className="w-full">
          <TabsList className="mb-4">
            <TabsTrigger value="info">{t.observability.basicInfo}</TabsTrigger>
            <TabsTrigger value="runs">{t.observability.runs}</TabsTrigger>
            <TabsTrigger value="state">{t.observability.state}</TabsTrigger>
          </TabsList>

          <TabsContent value="info" className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="rounded-lg border p-3">
                <div className="text-muted-foreground text-xs">{t.observability.status}</div>
                <div className="mt-1 flex items-center gap-2">
                  <Badge>{thread.status}</Badge>
                </div>
              </div>
              <div className="rounded-lg border p-3">
                <div className="text-muted-foreground text-xs">{t.observability.createdAt}</div>
                <div className="mt-1 text-sm">
                  {thread.created_at
                    ? new Date(thread.created_at).toLocaleString()
                    : "-"}
                </div>
              </div>
              <div className="rounded-lg border p-3">
                <div className="text-muted-foreground text-xs">{t.observability.updatedAt}</div>
                <div className="mt-1 text-sm">
                  {thread.updated_at
                    ? new Date(thread.updated_at).toLocaleString()
                    : "-"}
                </div>
              </div>
              <div className="rounded-lg border p-3">
                <div className="text-muted-foreground text-xs">{t.observability.checkpoint}</div>
                <div className="mt-1 font-mono text-xs">
                  {state?.checkpoint_id?.slice(0, 16) ?? "-"}
                </div>
              </div>
            </div>

            {thread.metadata && Object.keys(thread.metadata).length > 0 && (
              <div className="rounded-lg border p-3">
                <div className="text-muted-foreground mb-2 text-xs">{t.observability.metadata}</div>
                <pre className="max-h-40 overflow-auto rounded bg-muted p-2 text-xs">
                  {JSON.stringify(thread.metadata, null, 2)}
                </pre>
              </div>
            )}
          </TabsContent>

          <TabsContent value="runs">
            <ScrollArea className="h-64 rounded-lg border">
              {runs.length === 0 ? (
                <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
                  {t.observability.noRuns}
                </div>
              ) : (
                <div className="divide-y">
                  {runs.map((run) => (
                    <div key={run.run_id} className="flex items-center justify-between p-3">
                      <div className="flex items-center gap-2">
                        {statusIcons[run.status]}
                        <div>
                          <div className="font-mono text-xs">{run.run_id.slice(0, 8)}...</div>
                          <div className="text-muted-foreground text-xs">
                            {run.assistant_id ?? t.observability.defaultAssistant}
                          </div>
                        </div>
                      </div>
                      <div className="text-right text-xs">
                        <div>{new Date(run.created_at).toLocaleDateString()}</div>
                        <div className="text-muted-foreground">{run.status}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>
          </TabsContent>

          <TabsContent value="state">
            <ScrollArea className="h-64 rounded-lg border p-3">
              {state ? (
                <div className="space-y-4 text-sm">
                  <div>
                    <div className="text-muted-foreground mb-1 text-xs">{t.observability.nextTasks}</div>
                    {state.next.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {state.next.map((task) => (
                          <Badge key={task} variant="outline">
                            {task}
                          </Badge>
                        ))}
                      </div>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </div>

                  <div>
                    <div className="text-muted-foreground mb-1 text-xs">{t.observability.values}</div>
                    <pre className="max-h-40 overflow-auto rounded bg-muted p-2 text-xs">
                      {JSON.stringify(state.values, null, 2)}
                    </pre>
                  </div>

                  {state.tasks && state.tasks.length > 0 && (
                    <div>
                      <div className="text-muted-foreground mb-1 text-xs">{t.observability.tasks}</div>
                      <div className="space-y-1">
                        {state.tasks.map((task) => (
                          <div key={task.id} className="rounded bg-muted p-2 text-xs">
                            <div className="font-medium">{task.name}</div>
                            <div className="text-muted-foreground">ID: {task.id}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
                  {t.observability.noState}
                </div>
              )}
            </ScrollArea>
          </TabsContent>
        </Tabs>

        <div className="flex justify-end">
          <Button onClick={() => onOpenChange(false)}>{t.common.close}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
