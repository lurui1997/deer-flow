"use client";

import {
  AlertCircleIcon,
  CheckCircleIcon,
  ClockIcon,
  HelpCircleIcon,
  LightbulbIcon,
  MessageSquareIcon,
  AlertTriangleIcon,
  GitBranchIcon,
  SendIcon,
  CornerDownLeftIcon,
  XIcon,
  KeyboardIcon,
} from "lucide-react";
import { useState, useRef, useEffect, useCallback } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { useI18n } from "@/core/i18n/hooks";
import { useSubmitHITLResponse } from "@/core/hitl";
import type { HITLPendingItem } from "@/core/hitl/types";
import { cn } from "@/lib/utils";

interface HITLCardProps {
  item: HITLPendingItem;
  onResponded?: () => void;
  compact?: boolean;
}

const clarificationIcons: Record<string, React.ReactNode> = {
  missing_info: <HelpCircleIcon className="h-5 w-5" />,
  ambiguous_requirement: <AlertCircleIcon className="h-5 w-5" />,
  approach_choice: <GitBranchIcon className="h-5 w-5" />,
  risk_confirmation: <AlertTriangleIcon className="h-5 w-5" />,
  suggestion: <LightbulbIcon className="h-5 w-5" />,
};

const clarificationColors: Record<string, string> = {
  missing_info: "bg-blue-100 text-blue-700 border-blue-200",
  ambiguous_requirement: "bg-yellow-100 text-yellow-700 border-yellow-200",
  approach_choice: "bg-purple-100 text-purple-700 border-purple-200",
  risk_confirmation: "bg-red-100 text-red-700 border-red-200",
  suggestion: "bg-green-100 text-green-700 border-green-200",
};

const clarificationBgColors: Record<string, string> = {
  missing_info: "hover:border-blue-300 hover:bg-blue-50/50",
  ambiguous_requirement: "hover:border-yellow-300 hover:bg-yellow-50/50",
  approach_choice: "hover:border-purple-300 hover:bg-purple-50/50",
  risk_confirmation: "hover:border-red-300 hover:bg-red-50/50",
  suggestion: "hover:border-green-300 hover:bg-green-50/50",
};

export function HITLCard({ item, onResponded, compact = false }: HITLCardProps) {
  const { t } = useI18n();
  const submitResponse = useSubmitHITLResponse();
  const [respondOpen, setRespondOpen] = useState(false);
  const [response, setResponse] = useState("");
  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const clarification = item.clarification;
  const hasOptions = clarification.options && clarification.options.length > 0;

  // 自动聚焦输入框
  useEffect(() => {
    if (isExpanded && !hasOptions && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isExpanded, hasOptions]);

  // 键盘快捷键支持
  useEffect(() => {
    if (!isExpanded) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      // ESC 关闭
      if (e.key === "Escape") {
        setIsExpanded(false);
        setRespondOpen(false);
        return;
      }

      // 数字键 1-9 选择选项
      if (hasOptions && /^[1-9]$/.test(e.key)) {
        const index = parseInt(e.key) - 1;
        const options = clarification.options || [];
        if (index < options.length) {
          e.preventDefault();
          handleQuickSubmit(options[index]);
        } else if (index === options.length) {
          // 最后一个数字键选择自定义输入
          e.preventDefault();
          setSelectedOption("custom");
          setTimeout(() => inputRef.current?.focus(), 0);
        }
      }

      // Enter 提交
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (selectedOption && selectedOption !== "custom") {
          handleQuickSubmit(selectedOption);
        } else if (response.trim()) {
          handleQuickSubmit(response);
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isExpanded, hasOptions, clarification.options, selectedOption, response]);

  async function handleSubmit() {
    const finalResponse = selectedOption ?? response;
    if (!finalResponse.trim()) return;
    await handleQuickSubmit(finalResponse);
  }

  async function handleQuickSubmit(answer: string) {
    if (!answer.trim()) return;

    try {
      await submitResponse.mutateAsync({
        threadId: item.thread_id,
        request: {
          response: answer,
          tool_call_id: clarification.tool_call_id,
        },
      });
      toast.success(t.hitl.responseSubmitted);
      setRespondOpen(false);
      setIsExpanded(false);
      setResponse("");
      setSelectedOption(null);
      onResponded?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  }

  // 内联快速回复区域
  const renderInlineResponse = () => {
    if (!isExpanded) return null;

    return (
      <div className="mt-4 space-y-3 border-t pt-3 animate-in fade-in slide-in-from-top-2 duration-200">
        {/* 选项快速选择 */}
        {hasOptions && (
          <div className="space-y-2">
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <KeyboardIcon className="h-3 w-3" />
              <span>按数字键 1-{Math.min((clarification.options?.length || 0) + 1, 9)} 快速选择</span>
            </div>
            <div className="grid gap-2">
              {clarification.options?.map((option, idx) => (
                <Button
                  key={idx}
                  variant="outline"
                  size="sm"
                  className="justify-start h-auto py-2 px-3 text-left whitespace-normal"
                  onClick={() => handleQuickSubmit(option)}
                  disabled={submitResponse.isPending}
                >
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-muted text-xs font-mono mr-2">
                    {idx + 1}
                  </span>
                  <span className="text-sm">{option}</span>
                </Button>
              ))}
              <Button
                variant="outline"
                size="sm"
                className="justify-start h-auto py-2 px-3 text-left"
                onClick={() => {
                  setSelectedOption("custom");
                  setTimeout(() => inputRef.current?.focus(), 0);
                }}
                disabled={submitResponse.isPending}
              >
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-muted text-xs font-mono mr-2">
                  {(clarification.options?.length || 0) + 1}
                </span>
                <span className="text-sm text-muted-foreground">{t.hitl.customResponse}</span>
              </Button>
            </div>
          </div>
        )}

        {/* 自定义输入 */}
        {(!hasOptions || selectedOption === "custom") && (
          <div className="flex gap-2">
            <Input
              ref={inputRef}
              placeholder={t.hitl.responsePlaceholder}
              value={response}
              onChange={(e) => setResponse(e.target.value)}
              className="flex-1"
              disabled={submitResponse.isPending}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && response.trim()) {
                  e.preventDefault();
                  handleQuickSubmit(response);
                }
              }}
            />
            <Button
              size="icon"
              onClick={() => handleQuickSubmit(response)}
              disabled={!response.trim() || submitResponse.isPending}
            >
              {submitResponse.isPending ? (
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
              ) : (
                <SendIcon className="h-4 w-4" />
              )}
            </Button>
          </div>
        )}

        {/* 快捷提示 */}
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <CornerDownLeftIcon className="h-3 w-3" />
            <span>Enter 提交</span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-xs"
            onClick={() => {
              setIsExpanded(false);
              setSelectedOption(null);
              setResponse("");
            }}
          >
            <XIcon className="mr-1 h-3 w-3" />
            ESC 取消
          </Button>
        </div>
      </div>
    );
  };

  if (compact) {
    return (
      <div
        className={cn(
          "rounded-lg border p-3 transition-all cursor-pointer",
          clarificationBgColors[clarification.clarification_type] || "hover:bg-muted/50",
          isExpanded && "border-primary ring-1 ring-primary"
        )}
        onClick={() => !isExpanded && setIsExpanded(true)}
      >
        <div className="flex items-start gap-3">
          <div
            className={cn(
              "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
              clarificationColors[clarification.clarification_type] ?? "bg-muted text-muted-foreground"
            )}
          >
            {clarificationIcons[clarification.clarification_type] ?? (
              <MessageSquareIcon className="h-4 w-4" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium truncate">
                {t.hitl.clarificationTypes[clarification.clarification_type] ??
                  clarification.clarification_type}
              </span>
              {item.created_at && (
                <span className="text-muted-foreground text-xs">
                  {new Date(item.created_at).toLocaleTimeString()}
                </span>
              )}
            </div>
            <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
              {clarification.question}
            </p>
          </div>
        </div>
        {renderInlineResponse()}
      </div>
    );
  }

  return (
    <>
      <Card
        className={cn(
          "transition-all",
          isExpanded ? "shadow-md border-primary ring-1 ring-primary" : "hover:shadow-md",
          clarificationBgColors[clarification.clarification_type]
        )}
      >
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2">
              <div
                className={cn(
                  "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border",
                  clarificationColors[clarification.clarification_type] ??
                    "bg-muted text-muted-foreground"
                )}
              >
                {clarificationIcons[clarification.clarification_type] ?? (
                  <MessageSquareIcon className="h-5 w-5" />
                )}
              </div>
              <div className="min-w-0">
                <h3 className="truncate text-sm font-medium">
                  {t.hitl.clarificationTypes[clarification.clarification_type] ??
                    clarification.clarification_type}
                </h3>
                <div className="flex items-center gap-2">
                  <Badge variant="secondary" className="text-xs">
                    {item.status}
                  </Badge>
                  {item.created_at && (
                    <span className="text-muted-foreground text-xs">
                      <ClockIcon className="mr-1 inline h-3 w-3" />
                      {new Date(item.created_at).toLocaleString()}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
        </CardHeader>

        <CardContent className="pb-3">
          {clarification.context && (
            <p className="text-muted-foreground mb-2 text-xs bg-muted rounded px-2 py-1">
              {clarification.context}
            </p>
          )}
          <p className="text-sm">{clarification.question}</p>

          {/* 预览选项 */}
          {hasOptions && !isExpanded && (
            <div className="mt-3 flex flex-wrap gap-1">
              {clarification.options?.slice(0, 3).map((option, idx) => (
                <Badge key={idx} variant="outline" className="text-xs font-normal">
                  {idx + 1}. {option.length > 20 ? option.slice(0, 20) + "..." : option}
                </Badge>
              ))}
              {(clarification.options?.length || 0) > 3 && (
                <Badge variant="outline" className="text-xs">
                  +{(clarification.options?.length || 0) - 3}
                </Badge>
              )}
            </div>
          )}

          <div className="text-muted-foreground mt-3 text-xs font-mono">
            {item.thread_id.slice(0, 16)}...
          </div>

          {renderInlineResponse()}
        </CardContent>

        {!isExpanded && (
          <CardFooter className="pt-0">
            <Button
              size="sm"
              className="w-full"
              onClick={() => setIsExpanded(true)}
            >
              <MessageSquareIcon className="mr-1.5 h-4 w-4" />
              {t.hitl.respond}
              <span className="ml-2 text-xs opacity-70 hidden sm:inline">
                (Enter)
              </span>
            </Button>
          </CardFooter>
        )}
      </Card>

      {/* Full Dialog for complex responses */}
      <Dialog open={respondOpen} onOpenChange={setRespondOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{t.hitl.respondToClarification}</DialogTitle>
            <DialogDescription>
              {clarification.context && (
                <span className="block text-xs">{clarification.context}</span>
              )}
              <span className="mt-1 block">{clarification.question}</span>
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {hasOptions ? (
              <RadioGroup
                value={selectedOption ?? ""}
                onValueChange={setSelectedOption}
              >
                <div className="space-y-2">
                  {clarification.options?.map((option, idx) => (
                    <div
                      key={idx}
                      className="flex items-center space-x-2 rounded-lg border p-3"
                    >
                      <RadioGroupItem value={option} id={`option-${idx}`} />
                      <label
                        htmlFor={`option-${idx}`}
                        className="flex-1 text-sm"
                      >
                        {option}
                      </label>
                    </div>
                  ))}
                  <div className="flex items-center space-x-2 rounded-lg border p-3">
                    <RadioGroupItem value="custom" id="option-custom" />
                    <label htmlFor="option-custom" className="text-sm">
                      {t.hitl.customResponse}
                    </label>
                  </div>
                </div>
              </RadioGroup>
            ) : null}

            {(!hasOptions || selectedOption === "custom") && (
              <Input
                placeholder={t.hitl.responsePlaceholder}
                value={response}
                onChange={(e) => setResponse(e.target.value)}
                className="w-full"
              />
            )}
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setRespondOpen(false)}
              disabled={submitResponse.isPending}
            >
              {t.common.cancel}
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={
                submitResponse.isPending ||
                (!selectedOption && !response.trim())
              }
            >
              {submitResponse.isPending ? (
                t.common.submitting
              ) : (
                <>
                  <CheckCircleIcon className="mr-1.5 h-4 w-4" />
                  {t.common.submit}
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
