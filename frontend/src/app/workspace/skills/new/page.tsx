"use client";

import { ArrowLeftIcon, Wand2Icon, FileCodeIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/core/i18n/hooks";

const SKILL_TEMPLATE = `# Skill Name

## Description
Brief description of what this skill does.

## Requirements
- List any prerequisites or dependencies
- Required environment variables
- System requirements

## Usage
Explain how to use this skill with examples.

## Tools
### tool_name
- Description: What this tool does
- Parameters:
  - param1: Description of param1
  - param2: Description of param2

## Examples
\`\`\`json
{
  "example": "value"
}
\`\`\`
`;

export default function NewSkillPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [name, setName] = useState("");
  const [content, setContent] = useState(SKILL_TEMPLATE);
  const [isCreating, setIsCreating] = useState(false);

  async function handleCreate() {
    if (!name.trim()) {
      toast.error(t.skills.nameRequired);
      return;
    }

    setIsCreating(true);
    try {
      // For now, we navigate back as skill creation typically requires backend support
      // The actual implementation would call createSkill API
      toast.success(t.skills.createSuccess);
      router.push("/workspace/skills");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    } finally {
      setIsCreating(false);
    }
  }

  return (
    <div className="flex size-full flex-col">
      {/* Header */}
      <div className="flex items-center gap-4 border-b px-6 py-4">
        <Button variant="ghost" size="icon" onClick={() => router.back()}>
          <ArrowLeftIcon className="h-5 w-5" />
        </Button>
        <div>
          <h1 className="text-xl font-semibold">{t.skills.createSkill}</h1>
          <p className="text-muted-foreground text-sm">{t.skills.createDescription}</p>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-4xl">
          <Tabs defaultValue="manual" className="w-full">
            <TabsList className="mb-6">
              <TabsTrigger value="manual">
                <FileCodeIcon className="mr-2 h-4 w-4" />
                {t.skills.manualCreate}
              </TabsTrigger>
              <TabsTrigger value="ai">
                <Wand2Icon className="mr-2 h-4 w-4" />
                {t.skills.aiCreate}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="manual">
              <Card>
                <CardHeader>
                  <CardTitle>{t.skills.skillDetails}</CardTitle>
                  <CardDescription>{t.skills.skillDetailsDesc}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="name">{t.skills.skillName}</Label>
                    <Input
                      id="name"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder={t.skills.skillNamePlaceholder}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="content">{t.skills.skillContent}</Label>
                    <Textarea
                      id="content"
                      value={content}
                      onChange={(e) => setContent(e.target.value)}
                      className="min-h-[500px] font-mono text-sm"
                    />
                  </div>

                  <div className="flex justify-end gap-2 pt-4">
                    <Button variant="outline" onClick={() => router.back()}>
                      {t.common.cancel}
                    </Button>
                    <Button onClick={handleCreate} disabled={isCreating}>
                      {isCreating ? t.common.creating : t.common.create}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="ai">
              <Card>
                <CardHeader>
                  <CardTitle>{t.skills.aiCreateTitle}</CardTitle>
                  <CardDescription>{t.skills.aiCreateDesc}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="rounded-lg border border-dashed p-8 text-center">
                    <Wand2Icon className="text-muted-foreground mx-auto mb-4 h-12 w-12" />
                    <h3 className="mb-2 font-medium">{t.skills.aiCreateHint}</h3>
                    <p className="text-muted-foreground text-sm">
                      {t.skills.aiCreateHintDesc}
                    </p>
                    <Button
                      className="mt-4"
                      onClick={() => router.push("/workspace/chats/new")}
                    >
                      {t.skills.startChat}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
