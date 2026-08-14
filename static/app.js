"use strict";

const $ = (id) => document.getElementById(id);

let currentSession = null;
let ws = null;
let roundIdx = 0;
let modelMeta = {};
let pendingAnswer = null;
// conversation_id -> { idx, turns: [{q,a,th,steps:[]}] } while in progress
let liveConvs = {};
let toolPresets = [];

// ---------- helpers ----------
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const truncate = (s, n) => (s && s.length > n ? s.slice(0, n) + "…" : s ?? "");

// Set a stat counter; briefly flash it when it changes (streaming increments only).
function setStat(id, val, bump) {
  const el = $(id);
  const next = String(val);
  if (el.textContent === next) return;
  el.textContent = next;
  if (bump) {
    el.classList.add("bump");
    setTimeout(() => el.classList.remove("bump"), 130);
  }
}

// Small transient toast (replaces alert()).
function toast(msg, kind) {
  const root = $("toast-root");
  if (!root) return;
  const t = document.createElement("div");
  t.className = "toast" + (kind ? " " + kind : "");
  t.textContent = msg;
  root.appendChild(t);
  setTimeout(() => {
    t.classList.add("leaving");
    t.addEventListener("transitionend", () => t.remove(), { once: true });
    setTimeout(() => t.remove(), 400); // safety if transitionend never fires
  }, 4000);
}

async function jget(path) {
  const r = await fetch("/api" + path);
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  return r.json();
}
async function jpost(path, body) {
  const r = await fetch("/api" + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  return r.json();
}

// ---------- Ollama health ----------
async function checkHealth() {
  try {
    const h = await jget("/ollama/health");
    const el = $("ollama-health");
    el.textContent = h.ok ? "Ollama: connected" : "Ollama: down";
    el.className = "pill " + (h.ok ? "ok" : "bad");
    $("start").disabled = !h.ok || !$("teacher-model").value;
  } catch {
    $("ollama-health").textContent = "Ollama: down";
    $("ollama-health").className = "pill bad";
  }
}

// ---------- models ----------
async function refreshModels() {
  try {
    const models = await jget("/ollama/models");
    const sel = $("teacher-model");
    sel.innerHTML = "";
    modelMeta = {};
    if (!models.length) {
      sel.innerHTML = '<option value="">— no models, run ollama pull —</option>';
      return;
    }
    models.forEach((m) => {
      modelMeta[m.name] = m;
      const o = document.createElement("option");
      o.value = m.name;
      o.textContent = `${m.name} (${m.param_size || "?"}, ${m.quant || "?"})`;
      sel.appendChild(o);
    });
    sel.value = models[0].name;
    onTeacherChange();
  } catch (e) {
    $("teacher-detail").textContent = "Failed to list models: " + e.message;
  }
}
function onTeacherChange() {
  const sel = $("teacher-model");
  const name = sel.value;
  const m = modelMeta[name];
  if (m) {
    const tag = m.thinking ? " 🧠 thinking model" : "";
    $("teacher-detail").textContent = `${m.name} (${m.param_size || "?"}, ${m.quant || "?"})${tag}`;
    if (m.thinking) $("include-thinking").checked = true;
  } else {
    $("teacher-detail").textContent = "";
  }
  $("start").disabled = !$("ollama-health").classList.contains("ok") || !name;
}

// ---------- judge providers ----------
async function loadJudges() {
  const provs = await jget("/judges/providers");
  const dl = $("judge-models");
  dl.innerHTML = "";
  provs.forEach((p) => p.models.forEach((m) => {
    const o = document.createElement("option");
    o.value = m;
    dl.appendChild(o);
  }));
  if (!$("judge-model").value) $("judge-model").value = provs[0].models[0];
}

async function testJudge() {
  $("judge-test-result").textContent = "testing…";
  $("judge-test-result").style.color = "";
  try {
    const h = await jpost("/judges/test", {
      model: $("judge-model").value,
      api_key: $("judge-key").value || null,
      reasoning_effort: $("judge-effort").value || null,
    });
    $("judge-test-result").textContent = h.ok ? "✓ ok" : "✗ failed";
    $("judge-test-result").style.color = h.ok ? "var(--accent-2)" : "var(--danger)";
  } catch (e) {
    $("judge-test-result").textContent = "✗ " + e.message;
    $("judge-test-result").style.color = "var(--danger)";
  }
}

// ---------- multi-turn + tools UI ----------
function toggleMultiTurn() { $("mt-controls").classList.toggle("is-collapsed", !$("multi-turn").checked); }

async function loadToolPresets() {
  try { toolPresets = await jget("/tools/presets"); } catch { toolPresets = []; }
  const sel = $("tool-preset-select");
  sel.innerHTML = '<option value="">— add preset —</option>';
  toolPresets.forEach((p, i) => {
    const o = document.createElement("option");
    o.value = i;
    o.textContent = `${p.name} (${p.exec_policy})`;
    sel.appendChild(o);
  });
}

function addToolCard(preset) {
  const wrap = $("tools-list");
  const card = document.createElement("div");
  card.className = "tool-card";
  const p = preset || { name: "", description: "", parameters: { type: "object", properties: {} }, exec_policy: "simulate" };
  card.innerHTML = `
    <div class="row">
      <input class="t-name" placeholder="tool name (snake_case)" value="${esc(p.name)}" />
      <select class="t-policy">
        <option value="simulate" ${p.exec_policy === "simulate" ? "selected" : ""}>simulate</option>
        <option value="builtin" ${p.exec_policy === "builtin" ? "selected" : ""}>builtin</option>
        <option value="off" ${p.exec_policy === "off" ? "selected" : ""}>off</option>
      </select>
      <button class="btn t-del">remove</button>
    </div>
    <input class="t-desc" placeholder="description" value="${esc(p.description)}" />
    <textarea class="t-params" rows="3" placeholder='parameters JSON, e.g. {"type":"object","properties":{"x":{"type":"string"}}},"required":["x"]}'>${esc(JSON.stringify(p.parameters || { type: "object", properties: {} }, null, 2))}</textarea>
    <div class="row t-test-row">
      <input class="t-args" placeholder='test args JSON, e.g. {"expression":"2+2"}' />
      <button class="btn t-test">test simulate</button>
      <span class="t-test-out muted small"></span>
    </div>`;
  card.querySelector(".t-del").addEventListener("click", () => card.remove());
  card.querySelector(".t-test").addEventListener("click", () => testToolSimulate(card));
  wrap.appendChild(card);
}

async function testToolSimulate(card) {
  const out = card.querySelector(".t-test-out");
  out.textContent = "…";
  out.style.color = "";
  try {
    const params = JSON.parse(card.querySelector(".t-params").value || "{}");
    const args = JSON.parse(card.querySelector(".t-args").value || "{}");
    const res = await jpost("/tools/simulate", {
      tool_name: card.querySelector(".t-name").value || "tool",
      description: card.querySelector(".t-desc").value,
      parameters: params,
      arguments: args,
      judge_model: $("judge-model").value,
      judge_api_key: $("judge-key").value || null,
      judge_reasoning_effort: $("judge-effort").value || null,
    });
    out.textContent = res.ok ? truncate(res.result, 120) : "✗ " + (res.error || "failed");
    out.style.color = res.ok ? "var(--accent-2)" : "var(--danger)";
  } catch (e) { out.textContent = "✗ " + e.message; out.style.color = "var(--danger)"; }
}

function collectTools() {
  if (!$("tools-enabled").checked) return [];
  const tools = [];
  document.querySelectorAll("#tools-list .tool-card").forEach((card) => {
    const name = card.querySelector(".t-name").value.trim();
    if (!name) return;
    let params = { type: "object", properties: {} };
    try { params = JSON.parse(card.querySelector(".t-params").value || "{}"); } catch { /* keep default */ }
    tools.push({
      name,
      description: card.querySelector(".t-desc").value.trim() || name,
      parameters: params,
      exec_policy: card.querySelector(".t-policy").value,
    });
  });
  return tools;
}

// ---------- start ----------
async function startDistill() {
  const tools = collectTools();
  const body = {
    teacher_model: $("teacher-model").value,
    judge_model: $("judge-model").value,
    judge_api_key: $("judge-key").value || null,
    judge_reasoning_effort: $("judge-effort").value || null,
    topics: $("topics").value.split(",").map((s) => s.trim()).filter(Boolean),
    seeds: $("seeds").value.split("\n").map((s) => s.trim()).filter(Boolean),
    difficulty: $("difficulty").value,
    target_count: parseInt($("target").value, 10) || 10,
    min_score: parseInt($("min-score").value, 10) || 7,
    include_thinking: $("include-thinking").checked,
    teacher_system_prompt: $("teacher-prompt").value.trim() || null,
    grading_criteria: $("grading-criteria").value.trim() || null,
    concurrency: parseInt($("concurrency").value, 10) || 1,
    multi_turn: $("multi-turn").checked,
    min_turns: parseInt($("min-turns").value, 10) || 1,
    max_turns: parseInt($("max-turns").value, 10) || 1,
    history_include_thinking: $("history-include-thinking").checked,
    min_turn_score: parseInt($("min-turn-score").value, 10) || null,
    tools,
    max_tool_rounds: parseInt($("max-tool-rounds").value, 10) || 6,
    tool_call_timeout: parseFloat($("tool-call-timeout").value) || 60,
    keep_partial_on_abort: $("keep-partial").checked,
  };
  if (!body.topics.length) { $("start-msg").textContent = "add at least one topic"; return; }
  if (!body.teacher_model) { $("start-msg").textContent = "pick a teacher model"; return; }
  if (body.multi_turn && body.min_turns > body.max_turns) { $("start-msg").textContent = "min turns > max turns"; return; }
  $("start-msg").textContent = "starting…";
  $("start").classList.add("is-loading");
  try {
    const res = await jpost("/distill", body);
    currentSession = res.session_id;
    $("start-msg").textContent = "";
    $("start").classList.remove("is-loading");
    showRun(res.session_id, body.teacher_model, body.judge_model, body.target_count, body);
  } catch (e) {
    $("start-msg").textContent = "✗ " + e.message;
    $("start").classList.remove("is-loading");
  }
}

function showRun(sessionId, teacher, judge, target) {
  $("setup").classList.add("hidden");
  $("run").classList.remove("hidden");
  $("run-session").textContent = `#${sessionId} · ${teacher} ← ${judge}`;
  roundIdx = 0;
  liveConvs = {};
  $("rounds").querySelector("tbody").innerHTML = "";
  $("trace-view").classList.add("is-collapsed");
  $("progress-bar").classList.remove("done");
  setProgress(0, target);
  openStream(sessionId);
}

// ---------- websocket ----------
function openStream(sessionId) {
  if (ws) ws.close();
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/api/distill/${sessionId}/stream`);
  ws.onmessage = (ev) => handleEvent(JSON.parse(ev.data));
  ws.onclose = () => { if (currentSession === sessionId) refreshSessions(); };
}

function handleEvent(e) {
  switch (e.type) {
    case "status":
      applyStatus(e.status);
      break;
    case "question":
      break;
    case "conversation_started":
      liveConvs[e.conversation_id] = { idx: ++roundIdx, turns: [], toolsActive: e.tools_active };
      break;
    case "turn_answer":
      convUpdate(e.conversation_id, e.turn, { q: e.question, a: e.answer, th: e.thinking });
      break;
    case "turn_followup":
      // next question coming; nothing to render yet
      break;
    case "tool_call":
      convStep(e.conversation_id, e.turn, { kind: "call", step: e.step, content: e.answer, thinking: e.thinking });
      break;
    case "tool_result":
      convStep(e.conversation_id, e.turn, { kind: "result", step: e.step, name: e.tool_name, args: e.tool_args, result: e.tool_result, policy: e.exec_policy, error: e.tool_error });
      break;
    case "tool_unsupported":
      $("last-error").textContent = e.message;
      $("last-error").classList.remove("hidden");
      break;
    case "conversation_graded":
      finalizeConv(e);
      break;
    case "conversation_aborted":
      // counts handled by event fields; show note
      break;
    case "answer":
      // single-turn path only: hold until grade. The agentic path always sets
      // conversation_id on its answer/grade events; let finalizeConv own those
      // rows so we don't double-render (pendingAnswer must stay single-turn).
      if (!e.conversation_id) pendingAnswer = e;
      break;
    case "grade":
      if (pendingAnswer && !e.conversation_id) { addRound(pendingAnswer, e.grade); pendingAnswer = null; }
      break;
    case "kept":
    case "rejected":
    case "grade_failed":
      break;
    case "error":
      $("last-error").textContent = e.message;
      $("last-error").classList.remove("hidden");
      break;
    case "complete":
    case "stopped":
      $("progress-bar").classList.add("done");
      jget(`/distill/${currentSession}`).then(applyStatus).catch(() => {});
      break;
  }
  if (e.kept != null) setStat("s-kept", e.kept, true);
  if (e.rejected != null) setStat("s-rejected", e.rejected, true);
  if (e.aborted != null) setStat("s-aborted", e.aborted, true);
  // Only move the bar when we actually have a kept count — conversation_started
  // carries target but not kept, so the old `e.kept ?? 0` reset the bar to 0%
  // at the start of every new conversation. The `status` event handles the
  // initial 0% render via applyStatus.
  if (e.kept != null && e.target != null) setProgress(e.kept, e.target);
}

function convUpdate(cid, turn, data) {
  const c = liveConvs[cid];
  if (!c) return;
  c.turns[turn - 1] = Object.assign(c.turns[turn - 1] || { steps: [] }, data);
}
function convStep(cid, turn, step) {
  const c = liveConvs[cid];
  if (!c) return;
  c.turns[turn - 1] = c.turns[turn - 1] || { q: "", a: "", th: null, steps: [] };
  c.turns[turn - 1].steps.push(step);
}

function finalizeConv(e) {
  const c = liveConvs[e.conversation_id];
  if (!c) return;
  const grade = e.grade || {};
  const minScore = parseInt($("min-score").value, 10) || 7;
  let result, cls;
  if (grade.reasoning === "parse_failed" && grade.score === 0) { result = "grade failed"; cls = "failed"; }
  else if (e.kept != null) { result = "kept"; cls = "kept"; }
  else if (e.rejected != null) { result = "rejected"; cls = "rejected"; }
  else if (grade.score != null && grade.score >= minScore) { result = "kept"; cls = "kept"; }
  else { result = "rejected"; cls = "rejected"; }

  const nTurns = (c.turns.filter(Boolean)).length;
  const toolsUsed = c.turns.some((t) => t && t.steps && t.steps.length);
  const tr = document.createElement("tr");
  tr.className = "conv-row";
  tr.dataset.cid = e.conversation_id;
  tr.innerHTML = `
    <td>${c.idx}</td>
    <td class="q">${esc(truncate(c.turns[0]?.q || "", 200))}</td>
    <td>${nTurns}</td>
    <td>${grade.score != null ? grade.score + "/10" : "—"}</td>
    <td><span class="badge ${cls}">${result}</span></td>
    <td>${toolsUsed ? "✓" : "—"}</td>`;
  tr.title = `Judge: ${grade.reasoning || ""}`;
  tr.addEventListener("click", () => {
    document.querySelectorAll("#rounds .conv-row.selected").forEach((r) => r.classList.remove("selected"));
    tr.classList.add("selected");
    showTrace(c, grade);
  });
  $("rounds").querySelector("tbody").prepend(tr);
  delete liveConvs[e.conversation_id];
}

function showTrace(c, grade) {
  const v = $("trace-view");
  v.classList.remove("is-collapsed");
  let html = `<div class="trace-head">Conversation #${c.idx} — ${grade.reasoning || ""}</div>`;
  c.turns.forEach((t, i) => {
    if (!t) return;
    html += `<div class="trace-turn"><div class="trace-turn-h">Turn ${i + 1}</div>`;
    html += `<div class="trace-q"><b>Q:</b> ${esc(t.q || "")}</div>`;
    t.steps.forEach((s) => {
      if (s.kind === "call") {
        html += `<div class="trace-step"><span class="tag call">tool call</span> ${esc(truncate(s.content || "(no content)", 200))}</div>`;
      } else {
        html += `<div class="trace-step"><span class="tag result">result</span> <b>${esc(s.name)}</b> [${esc(s.policy)}] ${esc(truncate(s.result || "", 300))}${s.error ? ` <span class="error">${esc(s.error)}</span>` : ""}</div>`;
      }
    });
    if (t.th) html += `<div class="trace-th"><b>thinking:</b> ${esc(truncate(t.th, 400))}</div>`;
    html += `<div class="trace-a"><b>A:</b> ${esc(truncate(t.a || "", 400))}</div>`;
    html += `</div>`;
  });
  v.innerHTML = html;
}

function addRound(ans, grade) {
  roundIdx++;
  const minScore = parseInt($("min-score").value, 10) || 7;
  let result, cls;
  if (grade.reasoning === "parse_failed" && grade.score === 0) { result = "grade failed"; cls = "failed"; }
  else if (grade.score >= minScore) { result = "kept"; cls = "kept"; }
  else { result = "rejected"; cls = "rejected"; }
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td>${roundIdx}</td>
    <td class="q">${esc(truncate(ans.question, 200))}</td>
    <td>1</td>
    <td>${grade.score}/10</td>
    <td><span class="badge ${cls}">${result}</span></td>
    <td>—</td>`;
  tr.title = `Judge: ${grade.reasoning}`;
  $("rounds").querySelector("tbody").prepend(tr);
}

function applyStatus(s) {
  if (!s) return;
  setStat("s-kept", s.kept, false);
  setStat("s-rejected", s.rejected, false);
  setStat("s-grade-failed", s.grade_failed, false);
  setStat("s-aborted", s.aborted ?? 0, false);
  setStat("s-errors", s.error_count, false);
  const total = s.kept + s.rejected + s.grade_failed;
  setStat("s-rate", total ? Math.round((s.kept / total) * 100) + "%" : "—", false);
  setStat("s-tokens", s.tokens.total, false);
  setProgress(s.kept, s.target_count);
  $("topic-counts").textContent = Object.entries(s.topic_counts || {})
    .map(([k, v]) => `${k}: ${v}`).join("  ·  ");
  if (s.last_error) {
    $("last-error").textContent = s.last_error;
    $("last-error").classList.remove("hidden");
  }
}

function setProgress(kept, target) {
  const pct = target ? Math.min(100, (kept / target) * 100) : 0;
  $("progress-bar").style.width = pct + "%";
}

// ---------- stop ----------
async function stopRun() {
  if (!currentSession) return;
  await jpost(`/distill/${currentSession}/stop`, {}).catch(() => {});
}

// ---------- export ----------
function exportUrl(fmt) {
  const t = $("exp-thinking").checked ? "true" : "false";
  const toolspec = $("exp-tools-spec").checked ? "true" : "false";
  return `/api/distill/${currentSession}/export?fmt=${fmt}&include_thinking=${t}&thinking_format=${$("exp-format").value}&include_tools_spec=${toolspec}`;
}

// ---------- sessions ----------
async function refreshSessions() {
  try {
    const rows = await jget("/distill/sessions");
    const tb = $("sessions-table").querySelector("tbody");
    tb.innerHTML = "";
    rows.forEach((s) => {
      const mode = [s.multi_turn ? "MT" : null, s.tools_active ? "tools" : null].filter(Boolean).join("+") || "1T";
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${esc(s.id)}</td>
        <td>${esc(s.teacher_model)}</td>
        <td>${esc(s.judge_model)}</td>
        <td class="q">${esc((s.topics || []).join(", "))}</td>
        <td>${esc(mode)}</td>
        <td>${esc(s.status)}</td>
        <td>${s.kept}/${s.target_count}</td>
        <td>${esc((s.updated_at || "").slice(0, 19))}</td>
        <td>
          <button class="btn" data-resume="${esc(s.id)}">resume</button>
          <a class="btn" href="/api/distill/${esc(s.id)}/export?fmt=sharegpt" target="_blank">sharegpt</a>
        </td>`;
      tb.appendChild(tr);
    });
    tb.querySelectorAll("[data-resume]").forEach((b) =>
      b.addEventListener("click", () => resumeSession(b.getAttribute("data-resume")))
    );
  } catch {}
}

async function resumeSession(id) {
  try {
    const res = await jpost(`/distill/${id}/resume`, {});
    currentSession = res.session_id;
    const st = await jget(`/distill/${res.session_id}`);
    showRun(res.session_id, st.teacher_model, st.judge_model, st.target_count);
    applyStatus(st);
  } catch (e) {
    toast("resume failed: " + e.message, "error");
  }
}

// ---------- wire up ----------
document.addEventListener("DOMContentLoaded", () => {
  $("refresh-models").addEventListener("click", refreshModels);
  $("teacher-model").addEventListener("change", onTeacherChange);
  $("judge-test").addEventListener("click", testJudge);
  $("start").addEventListener("click", startDistill);
  $("stop").addEventListener("click", stopRun);
  $("multi-turn").addEventListener("change", toggleMultiTurn);
  $("tool-add").addEventListener("click", () => {
    const i = $("tool-preset-select").value;
    addToolCard(i !== "" ? toolPresets[parseInt(i, 10)] : null);
  });
  $("tool-add-empty").addEventListener("click", () => addToolCard(null));
  document.querySelectorAll(".export-controls [data-fmt]").forEach((b) =>
    b.addEventListener("click", () => { if (currentSession) window.location.href = exportUrl(b.getAttribute("data-fmt")); })
  );
  $("refresh-sessions").addEventListener("click", refreshSessions);

  refreshModels();
  loadJudges();
  loadToolPresets();
  checkHealth();
  refreshSessions();
  setInterval(checkHealth, 10000);
});