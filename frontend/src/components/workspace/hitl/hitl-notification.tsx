"use client";

import {
  BellIcon,
  MessageSquareIcon,
  XIcon,
  CornerDownLeftIcon,
  ClockIcon,
  AlertCircleIcon,
  AlertTriangleIcon,
  GitBranchIcon,
  HelpCircleIcon,
  LightbulbIcon,
} from "lucide-react";
import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useI18n } from "@/core/i18n/hooks";
import { usePendingHITL, useSubmitHITLResponse } from "@/core/hitl";
import { cn } from "@/lib/utils";
import type { HITLPendingItem } from "@/core/hitl/types";

const clarificationIcons: Record<string, React.ReactNode> = {
  missing_info: <HelpCircleIcon className="h-4 w-4" />,
  ambiguous_requirement: <AlertCircleIcon className="h-4 w-4" />,
  approach_choice: <GitBranchIcon className="h-4 w-4" />,
  risk_confirmation: <AlertTriangleIcon className="h-4 w-4" />,
  suggestion: <LightbulbIcon className="h-4 w-4" />,
};

const clarificationColors: Record<string, string> = {
  missing_info: "bg-blue-100 text-blue-700 border-blue-200",
  ambiguous_requirement: "bg-yellow-100 text-yellow-700 border-yellow-200",
  approach_choice: "bg-purple-100 text-purple-700 border-purple-200",
  risk_confirmation: "bg-red-100 text-red-700 border-red-200",
  suggestion: "bg-green-100 text-green-700 border-green-200",
};

interface HITLNotificationProps {
  className?: string;
}

export function HITLNotification({ className }: HITLNotificationProps) {
  const { t } = useI18n();
  const router = useRouter();
  const { pending, total, isLoading, refetch } = usePendingHITL(10, 0);
  const submitResponse = useSubmitHITLResponse();
  const [open, setOpen] = useState(false);
  const [respondingId, setRespondingId] = useState<string | null>(null);

  // 当有新请求时播放提示音（可选）
  useEffect(() => {
    if (total > 0 && !isLoading) {
      // 可以在这里添加提示音
    }
  }, [total, isLoading]);

  const handleQuickResponse = useCallback(
    async (item: HITLPendingItem, response: string) => {
      setRespondingId(item.thread_id);
      try {
        await submitResponse.mutateAsync({
          threadId: item.thread_id,
          request: {
            response,
            tool_call_id: item.clarification.tool_call_id,
          },
        });
        await refetch();
      } catch (err) {
        console.error("Failed to submit response:", err);
      } finally {
        setRespondingId(null);
      }
    },
    [submitResponse, refetch]
  );

  const handleNavigateToHITL = () => {
    setOpen(false);
    router.push("/workspace/hitl");
  };

  // 只显示有选项的请求在通知中快速回复
  const quickResponseItems = pending.filter(
    (item) => item.clarification.options && item.clarification.options.length > 0
  );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className={cn("relative", className)}
        >
          <BellIcon className="h-5 w-5" />
          {total > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75" />
              <span className="relative inline-flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
                {Math.min(total, 9)}
                {total > 9 && "+"}
              </span>
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-96 p-0" align="end">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <div className="flex items-center gap-2">
            <MessageSquareIcon className="h-4 w-4 text-primary" />
            <span className="font-semibold">人机协作请求</span>
            {total > 0 && (
              <Badge variant="secondary" className="text-xs">
                {total}
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs"
              onClick={handleNavigateToHITL}
            >
              查看全部
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => setOpen(false)}
            >
              <XIcon className="h-3 w-3" />
            </Button>
          </div>
        </div>

        <ScrollArea className="max-h-[400px]">
          {isLoading ? (
            <div className="flex h-32 items-center justify-center">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            </div>
          ) : total === 0 ? (
            <div className="flex h-32 flex-col items-center justify-center gap-2 text-center p-4">
              <div className="bg-muted rounded-full p-2">
                <BellIcon className="h-5 w-5 text-muted-foreground" />
              </div>
              <p className="text-sm text-muted-foreground">没有待处理请求</p>
            </div>
          ) : (
            <div className="divide-y">
              {pending.slice(0, 5).map((item) => (
                <div
                  key={item.thread_id}
                  className="p-4 hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-start gap-3">
                    <div
                      className={cn(
                        "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border",
                        clarificationColors[item.clarification.clarification_type] ??
                          "bg-muted text-muted-foreground"
                      )}
                    >
                      {clarificationIcons[item.clarification.clarification_type] ?? (
                        <MessageSquareIcon className="h-4 w-4" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium">
                          {t.hitl.clarificationTypes[item.clarification.clarification_type] ??
                            item.clarification.clarification_type}
                        </span>
                        {item.created_at && (
                          <span className="text-muted-foreground text-xs flex items-center gap-1">
                            <ClockIcon className="h-3 w-3" />
                            {formatRelativeTime(new Date(item.created_at))}
                          </span>
                        )}
                      </div>
                      <p className="text-sm mt-1 line-clamp-2">
                        {item.clarification.question}
                      </p>

                      {/* 快速选项 */}
                      {item.clarification.options &&
                        item.clarification.options.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-1">
                            {item.clarification.options.slice(0, 3).map((option, idx) => (
                              <Button
                                key={idx}
                                variant="outline"
                                size="sm"
                                className="h-6 px-2 text-xs"
                                disabled={respondingId === item.thread_id}
                                onClick={() => handleQuickResponse(item, option)}
                              >
                                {respondingId === item.thread_id ? (
                                  <span className="h-3 w-3 animate-spin rounded-full border border-current border-t-transparent" />
                                ) : (
                                  option.slice(0, 10) + (option.length > 10 ? "..." : "")
                                )}
                              </Button>
                            ))}
                          </div>
                        )}
                    </div>
                  </div>
                </div>
              ))}

              {total > 5 && (
                <div className="p-3 text-center">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-xs w-full"
                    onClick={handleNavigateToHITL}
                  >
                    还有 {total - 5} 个请求...
                  </Button>
                </div>
              )}
            </div>
          )}
        </ScrollArea>

        {/* 底部提示 */}
        {total > 0 && (
          <div className="border-t bg-muted/50 px-4 py-2 text-xs text-muted-foreground flex items-center justify-between">
            <span>按 Enter 快速回复</span>
            <span className="flex items-center gap-1">
              <CornerDownLeftIcon className="h-3 w-3" />
              快捷键
            </span>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}

function formatRelativeTime(date: Date): string {
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes}分钟前`;
  if (hours < 24) return `${hours}小时前`;
  if (days < 7) return `${days}天前`;
  return date.toLocaleDateString();
}
