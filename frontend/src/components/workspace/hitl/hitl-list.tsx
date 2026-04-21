"use client";

import { RefreshCwIcon, UserCheckIcon, FilterIcon } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useI18n } from "@/core/i18n/hooks";
import { usePendingHITL, useThreads } from "@/core/hitl";
import { HITLCard } from "./hitl-card";
import type { HITLPendingItem } from "@/core/hitl/types";
import type { AgentThread } from "@/core/threads/types";

export function HITLList() {
  const { t } = useI18n();
  const { pending, total, isLoading, error } = usePendingHITL(100, 0);
  const [search, setSearch] = useState("");
  const [filterType, setFilterType] = useState<string>("all");

  const filteredPending = useMemo(() => {
    return pending.filter((item) => {
      const matchesSearch =
        item.thread_id.toLowerCase().includes(search.toLowerCase()) ||
        item.clarification.question.toLowerCase().includes(search.toLowerCase());
      const matchesType =
        filterType === "all" ||
        item.clarification.clarification_type === filterType;
      return matchesSearch && matchesType;
    });
  }, [pending, search, filterType]);

  const clarificationTypes = useMemo(() => {
    const types = new Set(pending.map((p) => p.clarification.clarification_type));
    return ["all", ...Array.from(types)];
  }, [pending]);

  return (
    <div className="flex size-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold">{t.hitl.title}</h1>
          <p className="text-muted-foreground mt-0.5 text-sm">
            {t.hitl.description}
          </p>
        </div>
        <div className="flex items-center gap-4">
          <Badge variant="secondary" className="text-sm">
            <UserCheckIcon className="mr-1.5 h-4 w-4" />
            {t.hitl.pendingCount}: {total}
          </Badge>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4 border-b px-6 py-3">
        <Input
          type="search"
          placeholder={t.hitl.searchPending}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <Select value={filterType} onValueChange={setFilterType}>
          <SelectTrigger className="w-40">
            <FilterIcon className="mr-2 h-4 w-4" />
            <SelectValue placeholder={t.hitl.filterByType} />
          </SelectTrigger>
          <SelectContent>
            {clarificationTypes.map((type) => (
              <SelectItem key={type} value={type}>
                {type === "all"
                  ? t.hitl.allTypes
                  : t.hitl.clarificationTypes[type] ?? type}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {isLoading ? (
          <div className="flex h-40 items-center justify-center">
            <RefreshCwIcon className="text-muted-foreground h-8 w-8 animate-spin" />
          </div>
        ) : error ? (
          <div className="text-destructive flex h-40 items-center justify-center">
            {t.hitl.loadError}
          </div>
        ) : filteredPending.length === 0 ? (
          <div className="flex h-64 flex-col items-center justify-center gap-3 text-center">
            <UserCheckIcon className="text-muted-foreground h-12 w-12" />
            <div>
              <p className="font-medium">{t.hitl.noPending}</p>
              <p className="text-muted-foreground mt-1 text-sm">
                {t.hitl.noPendingDesc}
              </p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {filteredPending.map((item) => (
              <HITLCard key={item.thread_id} item={item} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
