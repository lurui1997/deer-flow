"use client";

import { CodeIcon, FileCodeIcon, Trash2Icon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { useDeleteCustomSkill, useUpdateSkill } from "@/core/skills";
import type { Skill } from "@/core/skills/types";
import { useI18n } from "@/core/i18n/hooks";

interface SkillCardProps {
  skill: Skill;
  onEdit?: (skill: Skill) => void;
}

export function SkillCard({ skill, onEdit }: SkillCardProps) {
  const { t } = useI18n();
  const updateSkill = useUpdateSkill();
  const deleteSkill = useDeleteCustomSkill();
  const [deleteOpen, setDeleteOpen] = useState(false);

  async function handleToggle(enabled: boolean) {
    try {
      await updateSkill.mutateAsync({ skillName: skill.name, enabled });
      toast.success(enabled ? t.common.enabled : t.common.disabled);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleDelete() {
    try {
      await deleteSkill.mutateAsync(skill.name);
      toast.success(t.common.deleteSuccess);
      setDeleteOpen(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  }

  const isCustom = skill.category === "custom";

  return (
    <>
      <Card className="flex flex-col transition-shadow hover:shadow-md">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2">
              <div className="bg-primary/10 text-primary flex h-9 w-9 shrink-0 items-center justify-center rounded-lg">
                {isCustom ? <FileCodeIcon className="h-5 w-5" /> : <CodeIcon className="h-5 w-5" />}
              </div>
              <div className="min-w-0">
                <CardTitle className="truncate text-base">{skill.name}</CardTitle>
                <Badge variant="secondary" className="mt-0.5 text-xs">
                  {skill.category}
                </Badge>
              </div>
            </div>
            <Switch
              checked={skill.enabled}
              onCheckedChange={handleToggle}
              disabled={updateSkill.isPending}
              aria-label={skill.enabled ? t.common.enabled : t.common.disabled}
            />
          </div>
          {skill.description && (
            <CardDescription className="mt-2 line-clamp-2 text-sm">
              {skill.description}
            </CardDescription>
          )}
        </CardHeader>

        <CardFooter className="mt-auto flex items-center justify-between gap-2 pt-3">
          {isCustom && onEdit && (
            <Button size="sm" variant="outline" className="flex-1" onClick={() => onEdit(skill)}>
              {t.common.edit}
            </Button>
          )}
          {isCustom && (
            <Button
              size="icon"
              variant="ghost"
              className="text-destructive hover:text-destructive h-8 w-8 shrink-0"
              onClick={() => setDeleteOpen(true)}
              title={t.common.delete}
            >
              <Trash2Icon className="h-3.5 w-3.5" />
            </Button>
          )}
        </CardFooter>
      </Card>

      {/* Delete Confirm Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t.common.delete}</DialogTitle>
            <DialogDescription>{t.skills.deleteConfirm}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)} disabled={deleteSkill.isPending}>
              {t.common.cancel}
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleteSkill.isPending}>
              {deleteSkill.isPending ? t.common.loading : t.common.delete}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
