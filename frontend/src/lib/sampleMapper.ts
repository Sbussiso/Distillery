// Map a kept Sample (from GET /api/distill/{id}/samples) into the RoundRow
// shape the conversations table + TraceView render. The live WebSocket path
// builds the same shape incrementally; this lets a past/resumed/completed
// session show its already-collected conversations without an empty table.
//
// raw.jsonl holds KEPT samples only, so every loaded row is a "kept" result.

import type {
  AssistantTraceMessage,
  Sample,
  ToolTraceMessage,
} from "./types";
import type {
  RoundRow,
  TraceStepView,
  TraceTurnView,
} from "./state/run.svelte";

function isAssistant(
  m: AssistantTraceMessage | ToolTraceMessage,
): m is AssistantTraceMessage {
  return m.role === "assistant";
}

/** Render an agentic tool_trace (interleaved assistant(tool_calls) + tool
 *  results) as the flat step list TraceView expects. The terminal
 *  no-tool-calls assistant message is the turn's final answer (shown as t.a),
 *  so it is NOT emitted as a step — only tool-calling steps and results. */
function stepsFromTrace(
  trace: (AssistantTraceMessage | ToolTraceMessage)[] | undefined,
): TraceStepView[] {
  const steps: TraceStepView[] = [];
  if (!trace || !trace.length) return steps;
  for (const m of trace) {
    if (isAssistant(m)) {
      if (!m.tool_calls || m.tool_calls.length === 0) continue; // final answer
      const desc = m.tool_calls
        .map((c) => `${c.name}(${JSON.stringify(c.arguments)})`)
        .join(", ");
      steps.push({
        kind: "call",
        step: steps.length + 1,
        content: m.content ? `${m.content}\n${desc}` : desc,
        thinking: m.thinking || null,
      });
    } else {
      steps.push({
        kind: "result",
        step: steps.length + 1,
        name: m.name,
        result: m.content,
        policy: null, // exec_policy is not stored per-result on disk
        error: null,
      });
    }
  }
  return steps;
}

function turnsFromSample(s: Sample): TraceTurnView[] {
  if (s.turns && s.turns.length) {
    return s.turns.map((t, i) => ({
      idx: i + 1,
      q: t.question,
      a: t.answer,
      th: t.thinking || null,
      steps: stepsFromTrace(t.tool_trace),
    }));
  }
  // Single-turn sample (no `turns` field on disk): synthesize one turn.
  return [
    {
      idx: 1,
      q: s.question,
      a: s.answer,
      th: s.thinking || null,
      steps: [],
    },
  ];
}

export function sampleToRound(s: Sample, idx: number): RoundRow {
  const turns = turnsFromSample(s);
  const toolsUsed =
    (s.tools != null && (s.tools?.length ?? 0) > 0) ||
    turns.some((t) => t.steps.length > 0);
  const grade = {
    score: s.score,
    passed: s.passed,
    reasoning: s.judge_reasoning,
    turn_scores: s.turn_scores ?? [],
    tool_score: s.tool_score ?? null,
  };
  return {
    id: s.conversation_id || `sample-${idx}`,
    idx,
    question: s.question,
    turns: s.n_turns || turns.length,
    grade,
    result: "kept",
    toolsUsed,
    reasoning: s.judge_reasoning,
    trace: { turns, grade },
  };
}

/** Build RoundRow[] (newest-first, idx = 1..N oldest->newest) from a page of
 *  kept samples. The samples endpoint returns oldest-first; we reverse for
 *  display so the most recent conversation is on top, matching the live stream. */
export function samplesToRounds(samples: Sample[]): RoundRow[] {
  const rows = samples.map((s, i) => sampleToRound(s, i + 1));
  rows.reverse(); // newest first; newest keeps the highest idx
  return rows;
}