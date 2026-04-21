export interface Skill {
  name: string;
  description: string;
  license: string | null;
  category: "public" | "custom";
  enabled: boolean;
}

export interface CustomSkillContent extends Skill {
  content: string;
}

export interface SkillHistoryEntry {
  action: string;
  author: string;
  thread_id: string | null;
  file_path: string;
  prev_content: string | null;
  new_content: string | null;
  ts: string;
  scanner?: {
    decision: string;
    reason: string;
  };
}

export interface SkillHistoryResponse {
  history: SkillHistoryEntry[];
}

export interface InstallSkillRequest {
  thread_id: string;
  path: string;
}

export interface InstallSkillResponse {
  success: boolean;
  skill_name: string;
  message: string;
}
