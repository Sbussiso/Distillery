<script lang="ts">
  import type { ToolDef } from "../lib/types";
  import Button from "./Button.svelte";
  import { testToolSimulate } from "../lib/actions";
  import { smallInputCls, smallSelectCls, textareaMonoCls } from "../lib/ui";
  import { untrack } from "svelte";

  let { tool, onRemove }: { tool: ToolDef; onRemove: () => void } = $props();

  // Seed the editable JSON text from the prop's initial value only — referencing
  // `tool.parameters` inside $state would otherwise capture it reactively and
  // re-seed (wiping edits) whenever the parent updates the object. untrack keeps
  // this a one-time seed, exactly as the warning-free intent.
  let paramsText = $state(
    untrack(() =>
      JSON.stringify(tool.parameters ?? { type: "object", properties: {} }, null, 2),
    ),
  );
  let argsText = $state("");
  let outText = $state("");
  let outOk = $state<boolean | null>(null);
  let testing = $state(false);

  function syncParams(): void {
    try {
      tool.parameters = JSON.parse(paramsText || "{}");
    } catch {
      // keep previous valid parameters (matches original app)
    }
  }

  async function runTest(): Promise<void> {
    testing = true;
    outText = "…";
    outOk = null;
    const r = await testToolSimulate(tool, argsText);
    testing = false;
    if (r.ok) {
      outText = truncate(r.result ?? "", 120);
      outOk = true;
    } else {
      outText = "✗ " + (r.detail ?? "failed");
      outOk = false;
    }
  }

  function truncate(s: string, n: number): string {
    return s && s.length > n ? s.slice(0, n) + "…" : s;
  }
</script>

<div class="rounded-lg border border-border bg-surface-2 p-4 shadow-xs space-y-3">
  <div class="flex items-center justify-between gap-2">
    <input bind:value={tool.name} placeholder="tool name (snake_case)" class={smallInputCls + " font-medium"} />
    <div class="relative">
      <select bind:value={tool.exec_policy} class={smallSelectCls}>
        <option value="simulate">simulate</option>
        <option value="builtin">builtin</option>
        <option value="off">off</option>
      </select>
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 text-muted"><path d="m6 9 6 6 6-6"/></svg>
    </div>
    <Button variant="icon" onclick={onRemove} title="remove tool" ariaLabel="remove tool">✕</Button>
  </div>

  <input bind:value={tool.description} placeholder="description" class={smallInputCls + " text-fg-muted"} />

  <textarea bind:value={paramsText} onblur={syncParams} rows="3" placeholder={"parameters JSON, e.g. " + '{"type":"object","properties":{"x":{"type":"string"}},"required":["x"]}'} class={textareaMonoCls}></textarea>

  <div class="flex flex-wrap items-center gap-2">
    <input bind:value={argsText} placeholder={"test args JSON, e.g. " + '{"expression":"2+2"}'} class={smallInputCls + " flex-1 min-w-48"} />
    <Button variant="secondary" onclick={runTest} disabled={testing}>test simulate</Button>
    <span class="text-xs font-mono {outOk === true ? "text-success" : outOk === false ? "text-danger" : "text-muted"}">{outText}</span>
  </div>
</div>