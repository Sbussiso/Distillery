<script lang="ts">
  import { form } from "../lib/state/form.svelte";
  import { meta } from "../lib/state/meta.svelte";
  import { startDistill, testJudge } from "../lib/actions";
  import { refreshModelsNow } from "../lib/boot";
  import type { TestResult } from "../lib/actions";
  import Button from "./Button.svelte";
  import ToolCard from "./ToolCard.svelte";
  import {
    inputCls,
    selectCls,
    numberInputCls,
    textareaCls,
    textareaMonoCls,
    checkCls,
    labelCls,
    helperCls,
  } from "../lib/ui";
  import type { ToolDef, ToolPreset } from "../lib/types";

  // Auto-select the first model once the model list loads.
  $effect(() => {
    if (meta.models.length && !form.teacherModel) {
      form.teacherModel = meta.models[0].name;
    }
  });

  let teacherDetail = $derived(
    meta.models.find((m) => m.name === form.teacherModel) ?? null,
  );

  function onTeacherChange(): void {
    if (teacherDetail?.thinking) form.includeThinking = true;
  }

  // Judge test
  let judgeTesting = $state(false);
  let judgeResult = $state<TestResult | null>(null);
  async function runJudgeTest(): Promise<void> {
    judgeTesting = true;
    judgeResult = null;
    judgeResult = await testJudge();
    judgeTesting = false;
  }

  // Tools
  let presetIdx = $state<number | "">("");
  function addPreset(): void {
    if (presetIdx === "") return;
    const p = meta.toolPresets[Number(presetIdx)];
    if (p) addToolFrom(p);
    presetIdx = "";
  }
  function addBlankTool(): void {
    addToolFrom({
      name: "",
      description: "",
      parameters: { type: "object", properties: {} },
      exec_policy: "simulate",
    });
  }
  function addToolFrom(p: ToolPreset | ToolDef): void {
    form.tools.push({
      name: p.name,
      description: p.description,
      parameters: JSON.parse(JSON.stringify(p.parameters)),
      exec_policy: p.exec_policy,
    });
  }
  function removeTool(i: number): void {
    form.tools.splice(i, 1);
  }

  let canStart = $derived(meta.healthOk && !!form.teacherModel);

  async function start(): Promise<void> {
    await startDistill();
  }
</script>

<section class="rounded-lg border border-border bg-surface shadow-sm">
  <div class="p-5 sm:p-6 space-y-6">
    <!-- ============ 1 · Teacher ============ -->
    <div>
      <div class="flex items-center gap-3">
        <span class="size-6 rounded-full bg-accent/10 text-accent text-xs font-semibold grid place-items-center">1</span>
        <h2 class="text-xl font-semibold tracking-tight text-fg">Teacher</h2>
        <span class="text-sm text-muted">— the local Ollama model being distilled</span>
      </div>
      <div class="mt-4 flex flex-wrap items-center gap-3">
        <div class="relative flex-1 min-w-64">
          <select bind:value={form.teacherModel} onchange={onTeacherChange} class={selectCls} disabled={!meta.models.length}>
            {#if !meta.models.length}
              <option value="">— no models —</option>
            {/if}
            {#each meta.models as m}
              <option value={m.name}>{m.name} ({m.param_size || "?"}, {m.quant || "?"})</option>
            {/each}
          </select>
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted"><path d="m6 9 6 6 6-6"/></svg>
        </div>
        <Button variant="secondary" onclick={() => refreshModelsNow()} disabled={meta.modelsLoading}>{meta.modelsLoading ? "loading…" : "Refresh models"}</Button>
      </div>
      <p class="mt-2 text-xs text-muted">
        {#if meta.modelsError}
          <span class="text-danger">{meta.modelsError}</span>
        {:else if teacherDetail}
          {teacherDetail.name} ({teacherDetail.param_size || "?"}, {teacherDetail.quant || "?"}){teacherDetail.thinking ? " · 🧠 thinking model" : ""}
        {:else}
          pick a model to distill
        {/if}
      </p>
    </div>

    <hr class="border-0 border-t border-border my-6" />

    <!-- ============ 2 · Judge ============ -->
    <div>
      <div class="flex items-center gap-3">
        <span class="size-6 rounded-full bg-accent/10 text-accent text-xs font-semibold grid place-items-center">2</span>
        <h2 class="text-xl font-semibold tracking-tight text-fg">Judge</h2>
        <span class="text-sm text-muted">— generates questions & grades answers (any LiteLLM provider)</span>
      </div>
      <div class="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
        <label class="flex flex-col gap-1.5">
          <span class={labelCls}>Model</span>
          <input bind:value={form.judgeModel} list="judge-models" placeholder="anthropic/claude-opus-5" class={inputCls} />
          <datalist id="judge-models">
            {#each meta.providers as p}
              {#each p.models as m}
                <option value={m}></option>
              {/each}
            {/each}
          </datalist>
        </label>
        <label class="flex flex-col gap-1.5">
          <span class={labelCls}>Reasoning effort</span>
          <div class="relative">
            <select bind:value={form.judgeReasoningEffort} class={selectCls}>
              <option value="none">no thinking</option>
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
            </select>
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted"><path d="m6 9 6 6 6-6"/></svg>
          </div>
        </label>
        <label class="flex flex-col gap-1.5 sm:col-span-2">
          <span class={labelCls}>API key <span class={helperCls}>(optional; else read from env)</span></span>
          <div class="flex flex-wrap items-center gap-3">
            <input bind:value={form.judgeApiKey} type="password" placeholder="API key (optional; else from env)" class={inputCls + " flex-1 min-w-48"} />
            <Button variant="secondary" onclick={runJudgeTest} disabled={judgeTesting}>{judgeTesting ? "testing…" : "Test judge"}</Button>
            <span class="text-xs {judgeResult?.ok === true ? 'text-success' : judgeResult?.ok === false ? 'text-danger' : 'text-muted'}">
              {#if judgeTesting}testing…
              {:else if judgeResult?.ok === true}✓ ok
              {:else if judgeResult?.ok === false}✗ {judgeResult.detail ?? "failed"}
              {/if}
            </span>
          </div>
        </label>
      </div>
    </div>

    <hr class="border-0 border-t border-border my-6" />

    <!-- ============ 3 · Distillation ============ -->
    <div>
      <div class="flex items-center gap-3">
        <span class="size-6 rounded-full bg-accent/10 text-accent text-xs font-semibold grid place-items-center">3</span>
        <h2 class="text-xl font-semibold tracking-tight text-fg">Distillation</h2>
      </div>
      <div class="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
        <label class="flex flex-col gap-1.5 sm:col-span-2">
          <span class={labelCls}>Topics <span class={helperCls}>(comma-separated)</span></span>
          <input bind:value={form.topics} placeholder="python debugging, algorithms" class={inputCls} />
        </label>
        <label class="flex flex-col gap-1.5">
          <span class={labelCls}>Difficulty</span>
          <div class="relative">
            <select bind:value={form.difficulty} class={selectCls}>
              <option value="any">any</option>
              <option value="easy">easy</option>
              <option value="medium">medium</option>
              <option value="hard">hard</option>
            </select>
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted"><path d="m6 9 6 6 6-6"/></svg>
          </div>
        </label>
        <label class="flex flex-col gap-1.5">
          <span class={labelCls}>Target count</span>
          <input bind:value={form.targetCount} type="number" min="1" class={numberInputCls} />
        </label>
        <label class="flex flex-col gap-1.5">
          <span class={labelCls}>Min score (1–10)</span>
          <input bind:value={form.minScore} type="number" min="1" max="10" class={numberInputCls} />
        </label>
        <label class="flex flex-col gap-1.5">
          <span class={labelCls}>Concurrency</span>
          <input bind:value={form.concurrency} type="number" min="1" max="16" class={numberInputCls} />
        </label>
        <label class="flex items-center gap-2 sm:col-span-2 pt-1">
          <input bind:checked={form.includeThinking} type="checkbox" class={checkCls} />
          <span class={labelCls}>Capture teacher thinking</span>
        </label>
        <label class="flex flex-col gap-1.5 sm:col-span-2">
          <span class={labelCls}>Seed questions <span class={helperCls}>(one per line, optional)</span></span>
          <textarea bind:value={form.seeds} rows="3" placeholder="Why does this list comprehension raise?" class={textareaMonoCls}></textarea>
        </label>
        <label class="flex flex-col gap-1.5">
          <span class={labelCls}>Teacher system prompt <span class={helperCls}>(optional)</span></span>
          <textarea bind:value={form.teacherSystemPrompt} rows="2" placeholder="Leave blank for default CoT prompt" class={textareaCls}></textarea>
        </label>
        <label class="flex flex-col gap-1.5">
          <span class={labelCls}>Grading criteria <span class={helperCls}>(optional)</span></span>
          <textarea bind:value={form.gradingCriteria} rows="2" placeholder="e.g. must include a code example" class={textareaCls}></textarea>
        </label>
      </div>
    </div>

    <hr class="border-0 border-t border-border my-6" />

    <!-- ============ 4 · Multi-turn (collapsible) ============ -->
    <details class="group rounded-lg border border-border bg-surface-2 shadow-xs">
      <summary class="flex cursor-pointer list-none items-center justify-between p-4">
        <div class="flex items-center gap-3">
          <span class="size-6 rounded-full bg-accent/10 text-accent text-xs font-semibold grid place-items-center">4</span>
          <h2 class="text-xl font-semibold tracking-tight text-fg">Multi-turn</h2>
          <span class="text-sm text-muted">(optional)</span>
        </div>
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-muted transition-transform group-open:rotate-180"><path d="m6 9 6 6 6-6"/></svg>
      </summary>
      <div class="border-t border-border p-4 animate-fade-in">
        <p class={helperCls}>Each sample becomes a multi-turn conversation. The judge plays a curious user asking follow-ups.</p>
        <label class="flex items-center gap-2 mt-4">
          <input bind:checked={form.multiTurn} type="checkbox" class={checkCls} />
          <span class={labelCls}>Enable multi-turn conversations</span>
        </label>
        {#if form.multiTurn}
          <div class="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label class="flex flex-col gap-1.5">
              <span class={labelCls}>Min turns</span>
              <input bind:value={form.minTurns} type="number" min="1" max="20" class={numberInputCls} />
            </label>
            <label class="flex flex-col gap-1.5">
              <span class={labelCls}>Max turns</span>
              <input bind:value={form.maxTurns} type="number" min="1" max="20" class={numberInputCls} />
            </label>
            <label class="flex flex-col gap-1.5">
              <span class={labelCls}>Min turn score (veto) <span class={helperCls}>(optional, 1–10)</span></span>
              <input bind:value={form.minTurnScore} type="number" min="1" max="10" placeholder="off" class={numberInputCls} />
            </label>
            <label class="flex items-center gap-2">
              <input bind:checked={form.historyIncludeThinking} type="checkbox" class={checkCls} />
              <span class={labelCls}>Feed prior thinking back into history</span>
            </label>
          </div>
        {/if}
      </div>
    </details>

    <!-- ============ 5 · Tools / agents (collapsible) ============ -->
    <details class="group rounded-lg border border-border bg-surface-2 shadow-xs">
      <summary class="flex cursor-pointer list-none items-center justify-between p-4">
        <div class="flex items-center gap-3">
          <span class="size-6 rounded-full bg-accent/10 text-accent text-xs font-semibold grid place-items-center">5</span>
          <h2 class="text-xl font-semibold tracking-tight text-fg">Tools / agents</h2>
          <span class="text-sm text-muted">(optional)</span>
        </div>
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-muted transition-transform group-open:rotate-180"><path d="m6 9 6 6 6-6"/></svg>
      </summary>
      <div class="border-t border-border p-4 animate-fade-in space-y-4">
        <p class={helperCls}>
          Give the teacher tools. The full tool-call trace (calls + results + final answer) is recorded so a student can be trained to act agentic.
          <strong class="text-fg">builtin</strong> runs safe executors (calculator);
          <strong class="text-fg">simulate</strong> has the judge produce a plausible result;
          <strong class="text-fg">off</strong> omits the tool.
        </p>
        <label class="flex items-center gap-2">
          <input bind:checked={form.toolsEnabled} type="checkbox" class={checkCls} />
          <span class={labelCls}>Enable tools</span>
        </label>
        {#if form.toolsEnabled}
          <div class="flex flex-wrap items-center gap-3">
            <div class="relative flex-1 min-w-48">
              <select bind:value={presetIdx} class={selectCls}>
                <option value="">— add preset —</option>
                {#each meta.toolPresets as p, i}
                  <option value={i}>{p.name} ({p.exec_policy})</option>
                {/each}
              </select>
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted"><path d="m6 9 6 6 6-6"/></svg>
            </div>
            <Button variant="secondary" onclick={addPreset}>+ Add preset</Button>
            <Button variant="secondary" onclick={addBlankTool}>+ Blank tool</Button>
          </div>

          {#if form.tools.length}
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
              {#each form.tools as tool, i (tool)}
                <ToolCard tool={tool} onRemove={() => removeTool(i)} />
              {/each}
            </div>
          {/if}

          <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-1">
            <label class="flex flex-col gap-1.5">
              <span class={labelCls}>Max tool rounds <span class={helperCls}>(inner loop cap per turn)</span></span>
              <input bind:value={form.maxToolRounds} type="number" min="1" max="20" class={numberInputCls} />
            </label>
            <label class="flex flex-col gap-1.5">
              <span class={labelCls}>Tool call timeout (s)</span>
              <input bind:value={form.toolCallTimeout} type="number" min="5" max="600" class={numberInputCls} />
            </label>
            <label class="flex items-center gap-2 self-end">
              <input bind:checked={form.keepPartialOnAbort} type="checkbox" class={checkCls} />
              <span class={labelCls}>Keep completed turns on abort</span>
            </label>
          </div>
        {/if}
      </div>
    </details>
  </div>

  <!-- Sticky start row inside the card -->
  <div class="sticky bottom-0 -mx-5 sm:-mx-6 mt-2 bg-surface/95 backdrop-blur-sm border-t border-border px-5 sm:px-6 py-4 rounded-b-lg">
    <div class="flex items-center gap-3">
      <Button variant="cta" onclick={start} disabled={!canStart || form.starting}>{form.starting ? "starting…" : "Start distillation"}</Button>
      {#if form.startMsg}
        <span class="text-sm {form.startMsg.startsWith("✗") ? "text-danger" : "text-muted"}">{form.startMsg}</span>
      {/if}
    </div>
  </div>
</section>