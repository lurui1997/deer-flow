import { getBackendBaseURL } from "@/core/config";

import type {
  CustomSkillContent,
  InstallSkillRequest,
  InstallSkillResponse,
  Skill,
  SkillHistoryResponse,
} from "./types";

export async function listSkills(): Promise<Skill[]> {
  const res = await fetch(`${getBackendBaseURL()}/api/skills`);
  if (!res.ok) throw new Error(`Failed to load skills: ${res.statusText}`);
  const data = (await res.json()) as { skills: Skill[] };
  return data.skills;
}

export async function listCustomSkills(): Promise<Skill[]> {
  const res = await fetch(`${getBackendBaseURL()}/api/skills/custom`);
  if (!res.ok) throw new Error(`Failed to load custom skills: ${res.statusText}`);
  const data = (await res.json()) as { skills: Skill[] };
  return data.skills;
}

export async function getSkill(skillName: string): Promise<Skill> {
  const res = await fetch(`${getBackendBaseURL()}/api/skills/${skillName}`);
  if (!res.ok) throw new Error(`Failed to get skill: ${res.statusText}`);
  return res.json() as Promise<Skill>;
}

export async function getCustomSkill(skillName: string): Promise<CustomSkillContent> {
  const res = await fetch(`${getBackendBaseURL()}/api/skills/custom/${skillName}`);
  if (!res.ok) throw new Error(`Failed to get custom skill: ${res.statusText}`);
  return res.json() as Promise<CustomSkillContent>;
}

export async function updateSkill(skillName: string, enabled: boolean): Promise<Skill> {
  const res = await fetch(`${getBackendBaseURL()}/api/skills/${skillName}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  if (!res.ok) throw new Error(`Failed to update skill: ${res.statusText}`);
  return res.json() as Promise<Skill>;
}

export async function updateCustomSkill(skillName: string, content: string): Promise<CustomSkillContent> {
  const res = await fetch(`${getBackendBaseURL()}/api/skills/custom/${skillName}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) throw new Error(`Failed to update custom skill: ${res.statusText}`);
  return res.json() as Promise<CustomSkillContent>;
}

export async function deleteCustomSkill(skillName: string): Promise<void> {
  const res = await fetch(`${getBackendBaseURL()}/api/skills/custom/${skillName}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`Failed to delete custom skill: ${res.statusText}`);
}

export async function getSkillHistory(skillName: string): Promise<SkillHistoryResponse> {
  const res = await fetch(`${getBackendBaseURL()}/api/skills/custom/${skillName}/history`);
  if (!res.ok) throw new Error(`Failed to get skill history: ${res.statusText}`);
  return res.json() as Promise<SkillHistoryResponse>;
}

export async function rollbackSkill(skillName: string, historyIndex: number = -1): Promise<CustomSkillContent> {
  const res = await fetch(`${getBackendBaseURL()}/api/skills/custom/${skillName}/rollback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ history_index: historyIndex }),
  });
  if (!res.ok) throw new Error(`Failed to rollback skill: ${res.statusText}`);
  return res.json() as Promise<CustomSkillContent>;
}

export async function installSkill(request: InstallSkillRequest): Promise<InstallSkillResponse> {
  const res = await fetch(`${getBackendBaseURL()}/api/skills/install`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  const data = (await res.json()) as InstallSkillResponse;
  if (!res.ok) {
    throw new Error(data.message || `Failed to install skill: ${res.statusText}`);
  }
  return data;
}
