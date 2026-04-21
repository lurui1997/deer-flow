"use client";

import { HistoryIcon, SaveIcon, UndoIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  useRollbackSkill,
  useSkill,
  useSkillHistory,
  useUpdateCustomSkill,
} from "@/core/skills";
import type { Skill } from "@/core/skills/types";
import { useI18n } from "@/core/i18n/hooks";

interface SkillEditDialogProps {
  skill: Skill | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SkillEditDialog({ skill, open, onOpenChange }: SkillEditDialogProps) {
  const { t } = useI18n();
  const { skill: skillWithContent, isLoading } = useSkill(skill?.name ?? null);
  const { history } = useSkillHistory(skill?.name ?? null);
  const updateSkill = useUpdateCustomSkill();
  const rollbackSkill = useRollbackSkill();
  const [content, setContent] = useState("");
  const [activeTab, setActiveTab] = useState("editor");

  useEffect(() => {
    if (skillWithContent?.content) {
      setContent(skillWithContent.content);
    }
  }, [skillWithContent?.content]);

  async function handleSave() {
    if (!skill) return;
    try {
      await updateSkill.mutateAsync({ skillName: skill.name, content });
      toast.success(t.common.saveSuccess);
      onOpenChange(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleRollback(historyIndex: number) {
    if (!skill) return;
    try {
      await rollbackSkill.mutateAsync({ skillName: skill.name, historyIndex });
      toast.success(t.skills.rollbackSuccess);
      // Refresh content
      const rolledBackSkill = await rollbackSkill.mutateAsync({
        skillName: skill.name,
        historyIndex,
      });
      if (rolledBackSkill.content) {
        setContent(rolledBackSkill.content);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  }

  if (!skill) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] max-w-4xl flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {t.skills.editSkill}: {skill.name}
          </DialogTitle>
          <DialogDescription>{skill.description}</DialogDescription>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1">
          <TabsList className="mb-2">
            <TabsTrigger value="editor">{t.skills.editor}</TabsTrigger>
            <TabsTrigger value="history">{t.skills.history}</TabsTrigger>
          </TabsList>

          <TabsContent value="editor" className="mt-0">
            <ScrollArea className="h-[50vh] rounded-md border">
              <Textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder={t.skills.skillContentPlaceholder}
                className="min-h-[50vh] resize-none border-0 font-mono text-sm"
                disabled={isLoading}
              />
            </ScrollArea>
          </TabsContent>

          <TabsContent value="history" className="mt-0">
            <ScrollArea className="h-[50vh] rounded-md border p-4">
              {history.length === 0 ? (
                <div className="text-muted-foreground py-8 text-center">
                  {t.skills.noHistory}
                </div>
              ) : (
                <div className="space-y-3">
                  {history.map((entry, index) => (
                    <div
                      key={entry.ts}
                      className="flex items-start justify-between gap-2 rounded-lg border p-3"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium">{entry.action}</span>
                          <span className="text-muted-foreground text-xs">
                            {new Date(entry.ts).toLocaleString()}
                          </span>
                        </div>
                        <div className="text-muted-foreground mt-1 text-xs">
                          {t.skills.author}: {entry.author}
                        </div>
                        {entry.scanner && (
                          <div className="mt-1 text-xs">
                            <span
                              className={
                                entry.scanner.decision === "allow"
                                  ? "text-green-600"
                                  : "text-red-600"
                              }
                            >
                              {entry.scanner.decision}
                            </span>
                          </div>
                        )}
                      </div>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            size="icon"
                            variant="ghost"
                            onClick={() => handleRollback(index)}
                            disabled={rollbackSkill.isPending}
                          >
                            <UndoIcon className="h-4 w-4" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>{t.skills.rollback}</TooltipContent>
                      </Tooltip>
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>
          </TabsContent>
        </Tabs>

        <DialogFooter className="gap-2">
          <div className="mr-auto flex gap-2">
            {history.length > 0 && activeTab === "editor" && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm">
                    <HistoryIcon className="mr-1.5 h-4 w-4" />
                    {t.skills.rollbackTo}
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start">
                  {history.slice(0, 5).map((entry, index) => (
                    <DropdownMenuItem
                      key={entry.ts}
                      onClick={() => handleRollback(index)}
                    >
                      {entry.action} - {new Date(entry.ts).toLocaleDateString()}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t.common.cancel}
          </Button>
          <Button onClick={handleSave} disabled={updateSkill.isPending || isLoading}>
            <SaveIcon className="mr-1.5 h-4 w-4" />
            {updateSkill.isPending ? t.common.saving : t.common.save}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
