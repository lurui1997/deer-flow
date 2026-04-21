"use client";

import { PlusIcon, SparklesIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useI18n } from "@/core/i18n/hooks";
import { useSkills } from "@/core/skills";
import type { Skill } from "@/core/skills/types";

import { SkillCard } from "./skill-card";
import { SkillEditDialog } from "./skill-edit-dialog";

export function SkillGallery() {
  const { t } = useI18n();
  const router = useRouter();
  const { skills, isLoading } = useSkills();
  const [search, setSearch] = useState("");
  const [editingSkill, setEditingSkill] = useState<Skill | null>(null);

  const filteredSkills = useMemo(() => {
    const term = search.toLowerCase();
    return skills.filter(
      (skill) =>
        skill.name.toLowerCase().includes(term) ||
        skill.description.toLowerCase().includes(term)
    );
  }, [skills, search]);

  const publicSkills = useMemo(
    () => filteredSkills.filter((s) => s.category === "public"),
    [filteredSkills]
  );

  const customSkills = useMemo(
    () => filteredSkills.filter((s) => s.category === "custom"),
    [filteredSkills]
  );

  return (
    <div className="flex size-full flex-col">
      {/* Page header */}
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold">{t.skills.title}</h1>
          <p className="text-muted-foreground mt-0.5 text-sm">
            {t.skills.description}
          </p>
        </div>
        <Button onClick={() => router.push("/workspace/skills/new")}>
          <PlusIcon className="mr-1.5 h-4 w-4" />
          {t.skills.createSkill}
        </Button>
      </div>

      {/* Search bar */}
      <div className="border-b px-6 py-3">
        <Input
          type="search"
          placeholder={t.skills.searchSkills}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-md"
        />
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {isLoading ? (
          <div className="text-muted-foreground flex h-40 items-center justify-center text-sm">
            {t.common.loading}
          </div>
        ) : skills.length === 0 ? (
          <div className="flex h-64 flex-col items-center justify-center gap-3 text-center">
            <div className="bg-muted flex h-14 w-14 items-center justify-center rounded-full">
              <SparklesIcon className="text-muted-foreground h-7 w-7" />
            </div>
            <div>
              <p className="font-medium">{t.skills.emptyTitle}</p>
              <p className="text-muted-foreground mt-1 text-sm">
                {t.skills.emptyDescription}
              </p>
            </div>
            <Button
              variant="outline"
              className="mt-2"
              onClick={() => router.push("/workspace/skills/new")}
            >
              <PlusIcon className="mr-1.5 h-4 w-4" />
              {t.skills.createSkill}
            </Button>
          </div>
        ) : (
          <Tabs defaultValue="all" className="w-full">
            <TabsList className="mb-4">
              <TabsTrigger value="all">
                {t.skills.allSkills} ({filteredSkills.length})
              </TabsTrigger>
              <TabsTrigger value="public">
                {t.skills.publicSkills} ({publicSkills.length})
              </TabsTrigger>
              <TabsTrigger value="custom">
                {t.skills.customSkills} ({customSkills.length})
              </TabsTrigger>
            </TabsList>

            <TabsContent value="all">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {filteredSkills.map((skill) => (
                  <SkillCard
                    key={skill.name}
                    skill={skill}
                    onEdit={skill.category === "custom" ? setEditingSkill : undefined}
                  />
                ))}
              </div>
            </TabsContent>

            <TabsContent value="public">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {publicSkills.map((skill) => (
                  <SkillCard key={skill.name} skill={skill} />
                ))}
              </div>
            </TabsContent>

            <TabsContent value="custom">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {customSkills.map((skill) => (
                  <SkillCard
                    key={skill.name}
                    skill={skill}
                    onEdit={setEditingSkill}
                  />
                ))}
              </div>
            </TabsContent>
          </Tabs>
        )}
      </div>

      {/* Edit Dialog */}
      <SkillEditDialog
        skill={editingSkill}
        open={!!editingSkill}
        onOpenChange={(open) => !open && setEditingSkill(null)}
      />
    </div>
  );
}
