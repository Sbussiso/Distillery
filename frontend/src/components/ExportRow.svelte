<script lang="ts">
  import { form } from "../lib/state/form.svelte";
  import { run } from "../lib/state/run.svelte";
  import { downloadExport } from "../lib/actions";
  import Button from "./Button.svelte";
  import { checkCls, labelCls, helperCls, selectCls } from "../lib/ui";

  let ready = $derived(run.status?.status === "completed" || (run.status?.kept ?? 0) > 0);
  let isSharegpt = $derived(form.expFmt === "sharegpt");
</script>

<div class="rounded-lg border border-border bg-surface p-5 shadow-sm">
  <div class="flex items-center gap-3 mb-4">
    <span class="size-6 rounded-full bg-accent/10 text-accent text-xs font-semibold grid place-items-center">↓</span>
    <h2 class="text-lg font-semibold tracking-tight text-fg">Export dataset</h2>
    <span class="text-sm text-muted">— download the kept samples</span>
  </div>

  <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-5">
    <label class="flex flex-col gap-1.5">
      <span class={labelCls}>Format</span>
      <div class="relative">
        <select bind:value={form.expFmt} class={selectCls}>
          <option value="sharegpt">ShareGPT</option>
          <option value="raw">raw JSON (full records)</option>
          <option value="alpaca">Alpaca</option>
        </select>
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted"><path d="m6 9 6 6 6-6"/></svg>
      </div>
      <span class={helperCls}>{isSharegpt ? "messages: [{role, content, thinking?}]" : form.expFmt === "raw" ? "one full record per line" : "instruction / output / thinking / grade"}</span>
    </label>

    <label class="flex flex-col gap-1.5" class:opacity-50={!isSharegpt}>
      <span class={labelCls}>Thinking <span class={helperCls}>(ShareGPT only)</span></span>
      <div class="relative">
        <select bind:value={form.expFormat} class={selectCls} disabled={!isSharegpt}>
          <option value="separate_field">separate field</option>
          <option value="inline_tags">inline &lt;think&gt; tags</option>
          <option value="strip">strip thinking</option>
        </select>
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted"><path d="m6 9 6 6 6-6"/></svg>
      </div>
      <span class={helperCls}>how the teacher's reasoning is encoded</span>
    </label>
  </div>

  <div class="flex flex-wrap items-center gap-5 mb-5" class:opacity-50={!isSharegpt}>
    <label class="flex items-center gap-2">
      <input bind:checked={form.expThinking} type="checkbox" class={checkCls} disabled={!isSharegpt} />
      <span class={labelCls}>Include thinking</span>
    </label>
    <label class="flex items-center gap-2">
      <input bind:checked={form.expToolsSpec} type="checkbox" class={checkCls} disabled={!isSharegpt} />
      <span class={labelCls}>Include tools spec</span>
      <span class={helperCls}>(agentic sessions)</span>
    </label>
  </div>

  <div class="flex flex-wrap items-center gap-3">
    <Button variant="primary" onclick={() => downloadExport(form.expFmt)} disabled={!ready}>
      Download {form.expFmt}
    </Button>
    {#if !ready}
      <span class="text-xs text-muted">no kept samples yet</span>
    {/if}
  </div>
</div>