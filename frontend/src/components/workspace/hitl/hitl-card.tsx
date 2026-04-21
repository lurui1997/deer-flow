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
} from "lucide-react";
import { useState } from "react";
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

interface HITLCardProps {
  item: HITLPendingItem;
}

const clarificationIcons: Record<string, React.ReactNode> = {
  missing_info: <HelpCircleIcon className="h-5 w-5" />,
  ambiguous_requirement: <AlertCircleIcon className="h-5 w-5" />,
  approach_choice: <GitBranchIcon className="h-5 w-5" />,
  risk_confirmation: <AlertTriangleIcon className="h-5 w-5" />,
  suggestion: <LightbulbIcon className="h-5 w-5" />,
};

const clarificationColors: Record<string, string> = {
  missing_info: "bg-blue-100 text-blue-700",
  ambiguous_requirement: "bg-yellow-100 text-yellow-700",
  approach_choice: "bg-purple-100 text-purple-700",
  risk_confirmation: "bg-red-100 text-red-700",
  suggestion: "bg-green-100 text-green-700",
};

export function HITLCard({ item }: HITLCardProps) {
  const { t } = useI18n();
  const submitResponse = useSubmitHITLResponse();
  const [respondOpen, setRespondOpen] = useState(false);
  const [response, setResponse] = useState("");
  const [selectedOption, setSelectedOption] = useState<string | null>(null);

  const clarification = item.clarification;
  const hasOptions = clarification.options && clarification.options.length > 0;

  async function handleSubmit() {
    const finalResponse = selectedOption ?? response;
    if (!finalResponse.trim()) return;

    try {
      await submitResponse.mutateAsync({
        threadId: item.thread_id,
        request: {
          response: finalResponse,
          tool_call_id: clarification.tool_call_id,
        },
      });
      toast.success(t.hitl.responseSubmitted);
      setRespondOpen(false);
      setResponse("");
      setSelectedOption(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <>
      <Card className="transition-shadow hover:shadow-md">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2">
              <div
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${
                  clarificationColors[clarification.clarification_type] ??
                  "bg-muted text-muted-foreground"
                }`}
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
            <p className="text-muted-foreground mb-2 text-xs">
              {clarification.context}
            </p>
          )}
          <p className="text-sm">{clarification.question}</p>

          {hasOptions && (
            <div className="mt-3 space-y-1">
              {clarification.options?.map((option, idx) => (
                <div
                  key={idx}
                  className="flex items-center gap-2 rounded bg-muted px-2 py-1 text-xs"
                >
                  <span className="text-muted-foreground font-mono">
                    {idx + 1}.
                  </span>
                  <span className="truncate">{option}</span>
                </div>
              ))}
            </div>
          )}

          <div className="text-muted-foreground mt-3 text-xs">
            {t.hitl.threadId}: {item.thread_id}
          </div>
        </CardContent>

        <CardFooter className="pt-3">
          <Button
            size="sm"
            className="w-full"
            onClick={() => setRespondOpen(true)}
          >
            <MessageSquareIcon className="mr-1.5 h-4 w-4" />
            {t.hitl.respond}
          </Button>
        </CardFooter>
      </Card>

      {/* Response Dialog */}
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
