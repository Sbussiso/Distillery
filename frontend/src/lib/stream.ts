// WebSocket connection manager + event reducer. Ports the original app.js
// `handleEvent` / `convUpdate` / `convStep` / `finalizeConv` / `addRound` /
// `applyStatus` logic, mutating the reactive `run` store (and reading `form`
// for min_score and the session id).
//
// liveConvs and pendingAnswers are plain module scratch state — they buffer
// in-progress conversations that aren't worth rendering until they finalize,
// exactly as the original app kept them in non-reactive JS objects and only
// touched the DOM on finalize.

import { api } from "./api";
import { form } from "./state/form.svelte";
import { run, type RoundResult, type RoundRow, type TraceStepView, type TraceTurnView } from "./state/run.svelte";
import { sessions } from "./state/sessions.svelte";
import type { Grade, ProgressEvent, SessionStatus } from "./types";

interface ConvLive {
  idx: number;
  turns: (TraceTurnView | null)[];
  toolsActive: boolean;
}

let ws: WebSocket | null = null;
let roundIdx = 0;
let liveConvs: Record<string, ConvLive> = {};
// Single-turn answers waiting for their grade, keyed by question: with
// concurrency > 1, answer/grade events from different workers interleave.
let pendingAnswers = new Map<string, ProgressEvent>();
let streamSessionId: string | null = null;

export function openStream(sessionId: string): void {
  closeStream();
  // Per-session scratch reset: the "#" column is a 1-based per-session row
  // number (matches the original app.js showRun() resetting roundIdx = 0),
  // and any abandoned in-progress conversations are dropped.
  roundIdx = 0;
  streamSessionId = sessionId;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/api/distill/${sessionId}/stream`);
  ws.onmessage = (ev) => {
    try {
      handleEvent(JSON.parse(ev.data));
    } catch {
      // ignore malformed frames
    }
  };
  ws.onclose = () => {
    if (streamSessionId === sessionId) {
      run.active = false;
      void sessions.reload();
    }
  };
}

export function closeStream(): void {
  if (ws) {
    ws.onclose = null;
    ws.close();
    ws = null;
  }
  // Drop any in-progress conversations that will never receive a
  // conversation_graded (e.g. user hit "New" mid-stream) so they can't leak
  // or bleed into the next session.
  liveConvs = {};
  pendingAnswers = new Map();
}

function minScore(): number {
  return form.minScore || 7;
}

function resultFromGrade(grade: Grade | undefined | null): RoundResult {
  if (grade && grade.reasoning === "parse_failed" && grade.score === 0)
    return "grade failed";
  return "rejected";
}

function classifyFinal(grade: Grade | undefined | null, kept?: number | null, rejected?: number | null): RoundResult {
  if (grade && grade.reasoning === "parse_failed" && grade.score === 0)
    return "grade failed";
  if (kept != null) return "kept";
  if (rejected != null) return "rejected";
  if (grade && grade.score >= minScore()) return "kept";
  return "rejected";
}

function convUpdate(cid: string, turn: number, data: Partial<TraceTurnView>): void {
  const c = liveConvs[cid];
  if (!c) return;
  const i = turn - 1;
  c.turns[i] = {
    idx: turn,
    q: data.q ?? c.turns[i]?.q ?? "",
    a: data.a ?? c.turns[i]?.a ?? "",
    th: data.th ?? c.turns[i]?.th ?? null,
    steps: c.turns[i]?.steps ?? [],
  };
}

function convStep(cid: string, turn: number, step: TraceStepView): void {
  const c = liveConvs[cid];
  if (!c) return;
  const i = turn - 1;
  if (!c.turns[i]) {
    c.turns[i] = { idx: turn, q: "", a: "", th: null, steps: [] };
  }
  c.turns[i]!.steps.push(step);
}

function snapshotTrace(c: ConvLive): { turns: TraceTurnView[]; grade: Grade | null } {
  const turns = c.turns.filter((t): t is TraceTurnView => t !== null);
  return { turns, grade: null };
}

function pushRound(row: RoundRow): void {
  run.rounds = [row, ...run.rounds];
}

function finalizeConv(e: ProgressEvent): void {
  const c = liveConvs[e.conversation_id ?? ""];
  if (!c) return;
  const grade = e.grade ?? null;
  const result = classifyFinal(grade, e.kept, e.rejected);
  const turnsArr = c.turns.filter((t): t is TraceTurnView => t !== null);
  const nTurns = turnsArr.length;
  const toolsUsed = turnsArr.some((t) => t.steps.length > 0);
  const firstQ = turnsArr[0]?.q ?? "";
  pushRound({
    id: e.conversation_id ?? "",
    idx: c.idx,
    question: firstQ,
    turns: nTurns,
    grade,
    result,
    toolsUsed,
    reasoning: grade?.reasoning ?? e.message ?? "",
    trace: { turns: turnsArr, grade },
  });
  delete liveConvs[e.conversation_id ?? ""];
}

function addRound(ans: ProgressEvent, grade: Grade): void {
  roundIdx++;
  const result = classifyFinal(grade);
  pushRound({
    id: `single-${roundIdx}`,
    idx: roundIdx,
    question: ans.question ?? "",
    turns: 1,
    grade,
    result,
    toolsUsed: false,
    reasoning: grade.reasoning,
    trace: {
      turns: [
        { idx: 1, q: ans.question ?? "", a: ans.answer ?? "", th: ans.thinking ?? null, steps: [] },
      ],
      grade,
    },
  });
}

function applyStatus(s: SessionStatus | null): void {
  if (!s) return;
  run.status = s;
  run.kept = s.kept;
  run.target = s.target_count;
  if (s.last_error) run.lastError = s.last_error;
}

function handleEvent(e: ProgressEvent): void {
  switch (e.type) {
    case "status":
      applyStatus(e.status ?? null);
      break;
    case "question":
      break;
    case "conversation_started":
      liveConvs[e.conversation_id ?? ""] = {
        idx: ++roundIdx,
        turns: [],
        toolsActive: !!e.tools_active,
      };
      break;
    case "turn_answer":
      convUpdate(e.conversation_id ?? "", e.turn ?? 1, {
        q: e.question ?? "",
        a: e.answer ?? "",
        th: e.thinking ?? null,
      });
      break;
    case "turn_followup":
      // next question coming; nothing to render yet
      break;
    case "tool_call":
      convStep(e.conversation_id ?? "", e.turn ?? 1, {
        kind: "call",
        step: e.step ?? 0,
        content: e.answer ?? null,
        thinking: e.thinking ?? null,
      });
      break;
    case "tool_result":
      convStep(e.conversation_id ?? "", e.turn ?? 1, {
        kind: "result",
        step: e.step ?? 0,
        name: e.tool_name ?? null,
        args: e.tool_args ?? null,
        result: e.tool_result ?? null,
        policy: e.exec_policy ?? null,
        error: e.tool_error ?? null,
      });
      break;
    case "tool_unsupported":
      run.lastError = e.message ?? null;
      break;
    case "conversation_graded":
      finalizeConv(e);
      break;
    case "conversation_aborted":
      // counts handled by event fields; no row added (matches app.js)
      break;
    case "answer":
      // single-turn path only: hold until grade. The agentic path always
      // sets conversation_id on its answer/grade events; let finalizeConv own
      // those rows so we don't double-render.
      if (!e.conversation_id) pendingAnswers.set(e.question ?? "", e);
      break;
    case "grade": {
      const ans = e.conversation_id ? undefined : pendingAnswers.get(e.question ?? "");
      if (ans) {
        addRound(ans, e.grade ?? { score: 0, passed: false, reasoning: "parse_failed" });
        pendingAnswers.delete(e.question ?? "");
      }
      break;
    }
    case "kept":
    case "rejected":
    case "grade_failed":
      break;
    case "error":
      run.lastError = e.message ?? null;
      break;
    case "complete":
    case "stopped":
      void api.getSession(streamSessionId ?? "").then(applyStatus).catch(() => {});
      break;
  }

  // Streaming stat increments (flash handled in the component via $state).
  if (e.kept != null) run.kept = e.kept;
  if (run.status) {
    if (e.kept != null) run.status.kept = e.kept;
    if (e.rejected != null) run.status.rejected = e.rejected;
    if (e.aborted != null) run.status.aborted = e.aborted;
    if (e.error_count != null) run.status.error_count = e.error_count;
    if (e.grade_failed != null) run.status.grade_failed = e.grade_failed;
  }
  // Only move the bar when we actually have a kept count — conversation_started
  // carries target but not kept, so resetting to 0% there would flicker.
  if (e.kept != null && e.target != null) {
    run.kept = e.kept;
    run.target = e.target;
  }
}