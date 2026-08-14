// Thin typed client for the FastAPI backend. All paths are relative to `/api`
// so they work identically under the Vite dev proxy (dev) and when FastAPI
// serves the built frontend (prod, same-origin).

import type {
  Difficulty,
  DistillRequest,
  DistillStarted,
  HealthStatus,
  JudgeProvider,
  OllamaModel,
  ReasoningEffort,
  SamplesPage,
  SessionMeta,
  SessionStatus,
  ThinkingFormat,
  ToolPreset,
  ToolSimulateResult,
} from "./types";

const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const r = await fetch(BASE + path);
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  return r.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  return r.json() as Promise<T>;
}

async function del<T>(path: string): Promise<T> {
  const r = await fetch(BASE + path, { method: "DELETE" });
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  return r.json() as Promise<T>;
}

export interface JudgeTestBody {
  model: string;
  api_key?: string | null;
  reasoning_effort?: ReasoningEffort | null;
}

export interface ToolSimulateBody {
  tool_name: string;
  description: string;
  parameters: Record<string, any>;
  arguments: Record<string, any>;
  judge_model: string;
  judge_api_key?: string | null;
  judge_reasoning_effort?: ReasoningEffort | null;
}

export const api = {
  // Ollama
  ollamaHealth: () => get<HealthStatus>("/ollama/health"),
  ollamaModels: () => get<OllamaModel[]>("/ollama/models"),

  // Judges
  judgeProviders: () => get<JudgeProvider[]>("/judges/providers"),
  judgeTest: (body: JudgeTestBody) => post<HealthStatus>("/judges/test", body),

  // Tools
  toolPresets: () => get<ToolPreset[]>("/tools/presets"),
  toolSimulate: (body: ToolSimulateBody) =>
    post<ToolSimulateResult>("/tools/simulate", body),

  // Distillation CRUD
  startDistill: (body: DistillRequest) =>
    post<DistillStarted>("/distill", body),
  listSessions: () => get<SessionMeta[]>("/distill/sessions"),
  getSession: (id: string) => get<SessionStatus>(`/distill/${id}`),
  stopSession: (id: string) =>
    post<SessionStatus>(`/distill/${id}/stop`, {}),
  resumeSession: (id: string) =>
    post<DistillStarted>(`/distill/${id}/resume`, {}),
  deleteSession: (id: string) => del<{ ok: boolean }>(`/distill/${id}`),
  getSamples: (id: string, offset = 0, limit = 50) =>
    get<SamplesPage>(
      `/distill/${id}/samples?offset=${offset}&limit=${limit}`,
    ),

  // Export — returns a URL the browser navigates to (triggers a download).
  exportUrl: (
    id: string,
    fmt: "sharegpt" | "raw" | "alpaca",
    opts: {
      include_thinking: boolean;
      thinking_format: ThinkingFormat;
      include_tools_spec: boolean;
    },
  ): string =>
    `${BASE}/distill/${id}/export?fmt=${fmt}` +
    `&include_thinking=${opts.include_thinking ? "true" : "false"}` +
    `&thinking_format=${opts.thinking_format}` +
    `&include_tools_spec=${opts.include_tools_spec ? "true" : "false"}`,
};

export type DifficultyValue = Difficulty;