// The setup-form state. Svelte 5 `$state` in a class instance preserves
// reactivity across module boundaries, so components can `bind:value`
// directly onto these fields. Mirrors the controls in the original index.html.

import type { ToolDef } from "../types";

export class FormState {
  // Teacher
  teacherModel = $state("");

  // Judge
  judgeModel = $state("anthropic/claude-opus-5");
  judgeApiKey = $state("");
  judgeReasoningEffort = $state<"none" | "low" | "medium" | "high">("medium");

  // Distillation
  topics = $state("");
  seeds = $state("");
  difficulty = $state<"any" | "easy" | "medium" | "hard">("any");
  targetCount = $state(10);
  minScore = $state(7);
  includeThinking = $state(true);
  teacherSystemPrompt = $state("");
  gradingCriteria = $state("");
  concurrency = $state(1);

  // Multi-turn
  multiTurn = $state(false);
  minTurns = $state(2);
  maxTurns = $state(4);
  historyIncludeThinking = $state(true);
  minTurnScore = $state<number | null>(null);

  // Tools
  toolsEnabled = $state(false);
  tools = $state<ToolDef[]>([]);
  maxToolRounds = $state(6);
  toolCallTimeout = $state(60);
  keepPartialOnAbort = $state(false);

  // Export (lives on the form; the run view reads it)
  expThinking = $state(true);
  expToolsSpec = $state(true);
  expFmt = $state<"sharegpt" | "raw" | "alpaca">("sharegpt");
  expFormat = $state<"separate_field" | "inline_tags" | "strip">(
    "separate_field",
  );

  // Start-flow status message (e.g. "starting…", "✗ …").
  startMsg = $state("");
  starting = $state(false);

  // Derived conveniences (getters reading $state are reactive).
  get topicsList(): string[] {
    return this.topics.split(",").map((s) => s.trim()).filter(Boolean);
  }
  get seedsList(): string[] {
    return this.seeds.split("\n").map((s) => s.trim()).filter(Boolean);
  }
  get judgeEffortOrNone(): "none" | "low" | "medium" | "high" | null {
    return this.judgeReasoningEffort || null;
  }

  /** Build the POST /api/distill body, matching the original app.js exactly. */
  toRequest(): import("../types").DistillRequest {
    return {
      teacher_model: this.teacherModel,
      judge_model: this.judgeModel,
      judge_api_key: this.judgeApiKey || null,
      judge_reasoning_effort: this.judgeEffortOrNone,
      topics: this.topicsList,
      seeds: this.seedsList,
      difficulty: this.difficulty,
      target_count: this.targetCount || 10,
      min_score: this.minScore || 7,
      include_thinking: this.includeThinking,
      teacher_system_prompt: this.teacherSystemPrompt.trim() || null,
      grading_criteria: this.gradingCriteria.trim() || null,
      concurrency: this.concurrency || 1,
      multi_turn: this.multiTurn,
      min_turns: this.minTurns || 1,
      max_turns: this.maxTurns || 1,
      history_include_thinking: this.historyIncludeThinking,
      min_turn_score: this.minTurnScore || null,
      tools: this.toolsEnabled ? this.tools : [],
      max_tool_rounds: this.maxToolRounds || 6,
      tool_call_timeout: this.toolCallTimeout || 60,
      keep_partial_on_abort: this.keepPartialOnAbort,
    };
  }

  /** Validate the form before start. Returns an error message or null. */
  validate(): string | null {
    if (!this.topicsList.length) return "add at least one topic";
    if (!this.teacherModel) return "pick a teacher model";
    if (this.multiTurn && this.minTurns > this.maxTurns)
      return "min turns > max turns";
    return null;
  }
}

export const form = new FormState();