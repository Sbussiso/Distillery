// User actions that cross store boundaries: start/stop/resume a distillation,
// return to the setup view, export a dataset, test the judge, and test a tool
// simulation. These call the api client and mutate the run/form/meta state.

import { api } from "./api";
import { form } from "./state/form.svelte";
import { run } from "./state/run.svelte";
import { sessions } from "./state/sessions.svelte";
import { toasts } from "./state/toasts.svelte";
import { openStream, closeStream } from "./stream";
import { samplesToRounds } from "./sampleMapper";
import type { Sample, SessionStatus } from "./types";

export async function startDistill(): Promise<void> {
  const err = form.validate();
  if (err) {
    form.startMsg = err;
    return;
  }
  form.starting = true;
  form.startMsg = "starting…";
  try {
    const body = form.toRequest();
    const res = await api.startDistill(body);
    run.reset(res.session_id, body.target_count);
    openStream(res.session_id);
    form.startMsg = "";
  } catch (e) {
    form.startMsg = "✗ " + (e as Error).message;
  } finally {
    form.starting = false;
  }
}

export async function stopRun(): Promise<void> {
  if (!run.sessionId) return;
  await api.stopSession(run.sessionId).catch(() => {});
}

export async function resumeSession(id: string): Promise<void> {
  try {
    const res = await api.resumeSession(id);
    const st = await api.getSession(res.session_id);
    run.reset(res.session_id, st.target_count);
    applyStatus(st);
    // Attach the stream first so no round finishing during the load is
    // missed, then merge in the conversations already collected on disk.
    openStream(res.session_id);
    await loadSamplesIntoRounds(res.session_id);
  } catch (e) {
    toasts.push("resume failed: " + (e as Error).message, "error");
  }
}

/** Open a session in view-only mode (from the past-distillations table): load
 *  its status + already-kept samples into the run view without (re)starting
 *  it. Only attaches the live stream if the session is actually running. */
export async function openSession(id: string): Promise<void> {
  // Always detach the previous session's stream, or its events would keep
  // landing in the run view now showing this session.
  closeStream();
  try {
    const st = await api.getSession(id);
    run.sessionId = id;
    run.active = st.status === "running";
    run.status = st;
    run.kept = st.kept;
    run.target = st.target_count;
    run.rounds = [];
    run.selectedRoundId = null;
    run.lastError = st.last_error ?? null;
    if (st.status === "running") openStream(id);
    await loadSamplesIntoRounds(id);
  } catch (e) {
    toasts.push("open failed: " + (e as Error).message, "error");
  }
}

/** Fetch every kept sample (paged, capped at 1000) and merge them into
 *  run.rounds so the conversations table + TraceView render past data. Rows
 *  that streamed in while loading may also be on disk; those are dropped in
 *  favour of the disk copy (multi-turn rows share the conversation id;
 *  single-turn questions are unique per session). */
async function loadSamplesIntoRounds(id: string): Promise<void> {
  const PAGE = 200;
  const CAP = 1000;
  let offset = 0;
  const all: Sample[] = [];
  for (let n = PAGE; n === PAGE && all.length < CAP; offset += PAGE) {
    const page = await api.getSamples(id, offset, PAGE);
    all.push(...page.items);
    n = page.items.length;
    if (page.total <= all.length) break;
  }
  if (run.sessionId !== id || !all.length) return; // switched sessions meanwhile
  const disk = samplesToRounds(all);
  const ids = new Set(disk.map((r) => r.id));
  const singleQs = new Set(disk.filter((r) => r.turns === 1).map((r) => r.question));
  const live = run.rounds.filter((r) => !ids.has(r.id) && !(r.turns === 1 && singleQs.has(r.question)));
  run.rounds = [...live, ...disk];
}

export function newDistillation(): void {
  closeStream();
  run.sessionId = null;
  run.active = false;
  run.status = null;
  run.rounds = [];
  run.selectedRoundId = null;
  run.lastError = null;
}

export async function deleteSession(id: string): Promise<void> {
  try {
    await api.deleteSession(id);
    if (run.sessionId === id) newDistillation();
    await sessions.reload();
    toasts.push("session deleted", "ok");
  } catch (e) {
    toasts.push("delete failed: " + (e as Error).message, "error");
  }
}

export function downloadExport(fmt: "sharegpt" | "raw" | "alpaca"): void {
  if (!run.sessionId) return;
  const url = api.exportUrl(run.sessionId, fmt, {
    include_thinking: form.expThinking,
    thinking_format: form.expFormat,
    include_tools_spec: form.expToolsSpec,
  });
  window.location.href = url;
}

export interface TestResult {
  ok: boolean;
  detail?: string;
}

export async function testJudge(): Promise<TestResult> {
  try {
    const h = await api.judgeTest({
      model: form.judgeModel,
      api_key: form.judgeApiKey || null,
      reasoning_effort: form.judgeReasoningEffort || null,
    });
    return { ok: h.ok, detail: h.detail ?? undefined };
  } catch (e) {
    return { ok: false, detail: (e as Error).message };
  }
}

export async function testToolSimulate(
  tool: { name: string; description: string; parameters: Record<string, any> },
  argsJson: string,
): Promise<TestResult & { result?: string }> {
  let args: Record<string, any> = {};
  try {
    args = argsJson.trim() ? JSON.parse(argsJson) : {};
  } catch {
    return { ok: false, detail: "invalid args JSON" };
  }
  try {
    const res = await api.toolSimulate({
      tool_name: tool.name || "tool",
      description: tool.description,
      parameters: tool.parameters,
      arguments: args,
      judge_model: form.judgeModel,
      judge_api_key: form.judgeApiKey || null,
      judge_reasoning_effort: form.judgeReasoningEffort || null,
    });
    return { ok: res.ok, detail: res.error ?? undefined, result: res.result };
  } catch (e) {
    return { ok: false, detail: (e as Error).message };
  }
}

function applyStatus(s: SessionStatus): void {
  run.status = s;
  run.kept = s.kept;
  run.target = s.target_count;
  if (s.last_error) run.lastError = s.last_error;
}