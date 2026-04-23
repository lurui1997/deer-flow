"use client";

import {
  RefreshCwIcon,
  UserCheckIcon,
  FilterIcon,
  LayoutGridIcon,
  ListIcon,
  BellIcon,
  CheckCircleIcon,
  ClockIcon,
  AlertTriangleIcon,
  ArrowUpDownIcon,
} from "lucide-react";
import { useMemo, useState, useEffect } from "react";

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
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Card, CardContent } from "@/components/ui/card";
import { useI18n } from "@/core/i18n/hooks";
import { usePendingHITL } from "@/core/hitl";
import { HITLCard } from "./hitl-card";
import type { HITLPendingItem } from "@/core/hitl/types";
import { cn } from "@/lib/utils";

type SortField = "created_at" | "type" | "thread_id";
type SortOrder = "asc" | "desc";
type ViewMode = "grid" | "list" | "compact";

export function HITLList() {
  const { t } = useI18n();
  const { pending, total, isLoading, error, refetch } = usePendingHITL(100, 0);
  const [search, setSearch] = useState("");
  const [filterType, setFilterType] = useState<string>("all");
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  const [sortField, setSortField] = useState<SortField>("created_at");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());

  // 自动刷新指示器
  useEffect(() => {
    const interval = setInterval(() => {
      setLastUpdated(new Date());
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  const filteredAndSortedPending = useMemo(() => {
    let result = pending.filter((item) => {
      const matchesSearch =
        item.thread_id.toLowerCase().includes(search.toLowerCase()) ||
        item.clarification.question.toLowerCase().includes(search.toLowerCase()) ||
        (item.clarification.context?.toLowerCase().includes(search.toLowerCase()) ?? false);
      const matchesType =
        filterType === "all" ||
        item.clarification.clarification_type === filterType;
      return matchesSearch && matchesType;
    });

    // 排序
    result = [...result].sort((a, b) => {
      let comparison = 0;
      switch (sortField) {
        case "created_at":
          comparison = new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime();
          break;
        case "type":
          comparison = a.clarification.clarification_type.localeCompare(b.clarification.clarification_type);
          break;
        case "thread_id":
          comparison = a.thread_id.localeCompare(b.thread_id);
          break;
      }
      return sortOrder === "asc" ? comparison : -comparison;
    });

    return result;
  }, [pending, search, filterType, sortField, sortOrder]);

  const clarificationTypes = useMemo(() => {
    const types = new Set(pending.map((p) => p.clarification.clarification_type));
    return ["all", ...Array.from(types)];
  }, [pending]);

  // 统计信息
  const stats = useMemo(() => {
    const byType: Record<string, number> = {};
    pending.forEach((item) => {
      const type = item.clarification.clarification_type;
      byType[type] = (byType[type] || 0) + 1;
    });
    return { byType };
  }, [pending]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortOrder("desc");
    }
  };

  return (
    <div className="flex size-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold">{t.hitl.title}</h1>
            {total > 0 && (
              <Badge variant="destructive" className="animate-pulse">
                <BellIcon className="mr-1 h-3 w-3" />
                {total} 待处理
              </Badge>
            )}
          </div>
          <p className="text-muted-foreground mt-0.5 text-sm">
            {t.hitl.description}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">
            上次更新: {lastUpdated.toLocaleTimeString()}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isLoading}
          >
            <RefreshCwIcon className={cn("mr-1.5 h-4 w-4", isLoading && "animate-spin")} />
            刷新
          </Button>
        </div>
      </div>

      {/* Stats Bar */}
      {total > 0 && (
        <div className="flex items-center gap-2 border-b px-6 py-2 bg-muted/30">
          {Object.entries(stats.byType).map(([type, count]) => (
            <Badge key={type} variant="secondary" className="text-xs">
              {t.hitl.clarificationTypes[type] ?? type}: {count}
            </Badge>
          ))}
        </div>
      )}

      {/* Filters Toolbar */}
      <div className="flex flex-wrap items-center gap-4 border-b px-6 py-3">
        <div className="flex items-center gap-3 flex-1 min-w-0">
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
                  {type !== "all" && stats.byType[type] && ` (${stats.byType[type]})`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-3">
          {/* Sort Button */}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => handleSort("created_at")}
            className={cn(sortField === "created_at" && "bg-muted")}
          >
            <ClockIcon className="mr-1.5 h-4 w-4" />
            时间
            {sortField === "created_at" && (
              <ArrowUpDownIcon className={cn("ml-1 h-3 w-3", sortOrder === "asc" && "rotate-180")} />
            )}
          </Button>

          {/* View Mode Toggle */}
          <ToggleGroup
            type="single"
            value={viewMode}
            onValueChange={(v) => v && setViewMode(v as ViewMode)}
          >
            <ToggleGroupItem value="grid" aria-label="Grid view">
              <LayoutGridIcon className="h-4 w-4" />
            </ToggleGroupItem>
            <ToggleGroupItem value="list" aria-label="List view">
              <ListIcon className="h-4 w-4" />
            </ToggleGroupItem>
            <ToggleGroupItem value="compact" aria-label="Compact view">
              <span className="text-xs font-mono">C</span>
            </ToggleGroupItem>
          </ToggleGroup>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {isLoading && pending.length === 0 ? (
          <div className="flex h-40 items-center justify-center">
            <RefreshCwIcon className="text-muted-foreground h-8 w-8 animate-spin" />
          </div>
        ) : error ? (
          <Card className="border-destructive">
            <CardContent className="flex h-40 flex-col items-center justify-center gap-3 text-center">
              <AlertTriangleIcon className="text-destructive h-12 w-12" />
              <div>
                <p className="font-medium text-destructive">{t.hitl.loadError}</p>
                <p className="text-muted-foreground mt-1 text-sm">
                  请检查网络连接或稍后重试
                </p>
              </div>
              <Button variant="outline" onClick={() => refetch()}>
                <RefreshCwIcon className="mr-1.5 h-4 w-4" />
                重试
              </Button>
            </CardContent>
          </Card>
        ) : filteredAndSortedPending.length === 0 ? (
          <div className="flex h-64 flex-col items-center justify-center gap-3 text-center">
            <div className="bg-muted rounded-full p-4">
              <CheckCircleIcon className="text-muted-foreground h-12 w-12" />
            </div>
            <div>
              <p className="font-medium">{t.hitl.noPending}</p>
              <p className="text-muted-foreground mt-1 text-sm">
                {search || filterType !== "all"
                  ? "没有符合筛选条件的人机协作请求"
                  : t.hitl.noPendingDesc}
              </p>
            </div>
            {(search || filterType !== "all") && (
              <Button
                variant="outline"
                onClick={() => {
                  setSearch("");
                  setFilterType("all");
                }}
              >
                清除筛选
              </Button>
            )}
          </div>
        ) : (
          <div
            className={cn(
              "grid gap-4",
              viewMode === "grid" && "grid-cols-1 md:grid-cols-2 lg:grid-cols-3",
              viewMode === "list" && "grid-cols-1",
              viewMode === "compact" && "grid-cols-1"
            )}
          >
            {filteredAndSortedPending.map((item) => (
              <HITLCard
                key={item.thread_id}
                item={item}
                compact={viewMode === "compact"}
                onResponded={() => refetch()}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
