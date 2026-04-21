import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  deleteCustomSkill,
  getCustomSkill,
  getSkillHistory,
  installSkill,
  listCustomSkills,
  listSkills,
  rollbackSkill,
  updateCustomSkill,
  updateSkill,
} from "./api";
import type { InstallSkillRequest } from "./types";

export function useSkills() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["skills"],
    queryFn: () => listSkills(),
  });
  return { skills: data ?? [], isLoading, error };
}

export function useCustomSkills() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["skills", "custom"],
    queryFn: () => listCustomSkills(),
  });
  return { skills: data ?? [], isLoading, error };
}

export function useSkill(skillName: string | null) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["skills", skillName],
    queryFn: () => (skillName ? getCustomSkill(skillName) : Promise.reject("No skill name")),
    enabled: !!skillName,
  });
  return { skill: data ?? null, isLoading, error };
}

export function useSkillHistory(skillName: string | null) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["skills", skillName, "history"],
    queryFn: () => (skillName ? getSkillHistory(skillName) : Promise.reject("No skill name")),
    enabled: !!skillName,
  });
  return { history: data?.history ?? [], isLoading, error };
}

export function useUpdateSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ skillName, enabled }: { skillName: string; enabled: boolean }) =>
      updateSkill(skillName, enabled),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}

export function useUpdateCustomSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ skillName, content }: { skillName: string; content: string }) =>
      updateCustomSkill(skillName, content),
    onSuccess: (_data, { skillName }) => {
      void queryClient.invalidateQueries({ queryKey: ["skills", skillName] });
      void queryClient.invalidateQueries({ queryKey: ["skills", "custom"] });
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}

export function useDeleteCustomSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (skillName: string) => deleteCustomSkill(skillName),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["skills", "custom"] });
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}

export function useRollbackSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ skillName, historyIndex }: { skillName: string; historyIndex: number }) =>
      rollbackSkill(skillName, historyIndex),
    onSuccess: (_data, { skillName }) => {
      void queryClient.invalidateQueries({ queryKey: ["skills", skillName] });
      void queryClient.invalidateQueries({ queryKey: ["skills", skillName, "history"] });
      void queryClient.invalidateQueries({ queryKey: ["skills", "custom"] });
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}

export function useInstallSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: InstallSkillRequest) => installSkill(request),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["skills", "custom"] });
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}
