// TypeScript mirrors of the backend Pydantic schemas (src/distillery/schemas.py)
// and the WebSocket ProgressEvent. These are the wire types the frontend speaks.

export type Difficulty = "any" | "easy" | "medium" | "hard";
export type ExecPolicy = "simulate" | "builtin" | "off";
export type ReasoningEffort = "none" | "low" | "medium" | "high";
export type ThinkingFormat = "separate_field" | "inline_tags" | "strip";
export type SessionStatusLiteral = "running" | "stopped" | "completed" | "errored";

export interface OllamaModel {
  name: string;
  size?: number | null;
  param_size?: string | null;
  quant?: string | null;
  capabilities?: string[];
  thinking?: boolean;
}

export interface HealthStatus {
  ok: boolean;
  detail?: string | null;
}

export interface JudgeProvider {
  provider: string;
  label: string;
  models: string[];
}

export interface ToolDef {
  name: string;
  description: string;
  parameters: Record<string, any>;
  exec_policy: ExecPolicy;
}

export interface ToolPreset {
  name: string;
  description: string;
  parameters: Record<string, any>;
  exec_policy: ExecPolicy;
}

export interface Grade {
  score: number; // 1-10 (0 = parse failed)
  passed: boolean;
  reasoning: string;
  turn_scores?: number[];
  tool_score?: number | null;
}

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, any>;
}

export interface AssistantTraceMessage {
  role: "assistant";
  content: string;
  thinking: string;
  tool_calls: ToolCall[];
}

export interface ToolTraceMessage {
  role: "tool";
  tool_call_id: string;
  name: string;
  content: string;
}

export type TraceMessage = AssistantTraceMessage | ToolTraceMessage;

export interface Turn {
  question: string;
  answer: string;
  thinking: string;
  tool_trace: TraceMessage[];
}

export interface Sample {
  question: string;
  answer: string;
  thinking: string;
  score: number;
  passed: boolean;
  judge_reasoning: string;
  teacher_model: string;
  judge_model: string;
  topics: string[];
  difficulty: string | null;
  timestamp: string;
  turns?: Turn[];
  conversation_id?: string | null;
  n_turns?: number;
  tools?: any[] | null;
  system_prompt?: string | null;
  turn_scores?: number[] | null;
  tool_score?: number | null;
}

export interface TokenTotals {
  prompt: number;
  completion: number;
  total: number;
}

export interface SessionStatus {
  id: string;
  teacher_model: string;
  judge_model: string;
  topics: string[];
  status: SessionStatusLiteral;
  target_count: number;
  kept: number;
  rejected: number;
  grade_failed: number;
  error_count: number;
  topic_counts: Record<string, number>;
  tokens: TokenTotals;
  multi_turn: boolean;
  min_turns: number;
  max_turns: number;
  aborted: number;
  tools_active: boolean;
  last_question?: string | null;
  last_answer?: string | null;
  last_thinking?: string | null;
  last_grade?: Grade | null;
  last_error?: string | null;
}

export interface SessionMeta {
  id: string;
  teacher_model: string;
  judge_model: string;
  topics: string[];
  status: string;
  target_count: number;
  kept: number;
  rejected: number;
  grade_failed: number;
  error_count: number;
  multi_turn: boolean;
  min_turns: number;
  max_turns: number;
  tools_active: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface DistillStarted {
  session_id: string;
}

export interface SamplesPage {
  total: number;
  offset: number;
  limit: number;
  items: Sample[];
}

export interface ToolSimulateResult {
  result: string;
  ok: boolean;
  error?: string | null;
}

// The full request body for POST /api/distill. Mirrors schemas.DistillRequest.
// max_tokens / teacher_timeout / judge_timeout are omitted so the server applies
// its defaults (matches the original frontend's behavior).
export interface DistillRequest {
  teacher_model: string;
  judge_model: string;
  judge_api_key: string | null;
  judge_reasoning_effort: ReasoningEffort | null;
  topics: string[];
  seeds: string[];
  difficulty: Difficulty;
  target_count: number;
  min_score: number;
  include_thinking: boolean;
  teacher_system_prompt: string | null;
  grading_criteria: string | null;
  concurrency: number;
  multi_turn: boolean;
  min_turns: number;
  max_turns: number;
  history_include_thinking: boolean;
  min_turn_score: number | null;
  tools: ToolDef[];
  max_tool_rounds: number;
  tool_call_timeout: number;
  keep_partial_on_abort: boolean;
}

// WebSocket ProgressEvent (one discriminated union shape; fields are optional
// per event type, exactly as the backend emits them).
export type ProgressEventType =
  | "question"
  | "answer"
  | "grade"
  | "kept"
  | "rejected"
  | "grade_failed"
  | "error"
  | "complete"
  | "stopped"
  | "status"
  | "conversation_started"
  | "turn_answer"
  | "turn_followup"
  | "conversation_graded"
  | "conversation_aborted"
  | "tool_call"
  | "tool_result"
  | "tool_unsupported";

export interface ProgressEvent {
  type: ProgressEventType;
  question?: string | null;
  answer?: string | null;
  thinking?: string | null;
  grade?: Grade | null;
  kept?: number | null;
  rejected?: number | null;
  grade_failed?: number | null;
  error_count?: number | null;
  aborted?: number | null;
  target?: number | null;
  topic?: string | null;
  message?: string | null;
  status?: SessionStatus | null;
  conversation_id?: string | null;
  turn?: number | null;
  turn_count?: number | null;
  step?: number | null;
  tool_call_id?: string | null;
  tool_name?: string | null;
  tool_args?: Record<string, any> | null;
  tool_result?: string | null;
  exec_policy?: string | null;
  tool_error?: string | null;
  tools_active?: boolean | null;
}