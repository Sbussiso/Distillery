<script lang="ts">
  import { run } from "../lib/state/run.svelte";
  import { form } from "../lib/state/form.svelte";
  import { stopRun, newDistillation, resumeSession } from "../lib/actions";
  import Button from "./Button.svelte";
  import StatBar from "./StatBar.svelte";
  import ProgressBar from "./ProgressBar.svelte";
  import ErrorBanner from "./ErrorBanner.svelte";
  import ConversationsTable from "./ConversationsTable.svelte";
  import ExportRow from "./ExportRow.svelte";

  let status = $derived(run.status?.status ?? "starting");
  let running = $derived(status === "running");
  let done = $derived(status === "completed" || status === "stopped");
  let aborted = $derived(status === "errored");

  let teacher = $derived(run.status?.teacher_model ?? form.teacherModel ?? "—");
  let judge = $derived(run.status?.judge_model ?? form.judgeModel ?? "—");

  let topicChips = $derived(
    Object.entries(run.status?.topic_counts ?? {}).map(([k, v]) => `${k}: ${v}`),
  );

  // Compact mode badge: 1T (single-turn) / MT (multi-turn) / MT+tools / tools.
  let modeBadge = $derived(
    (run.status?.multi_turn ? "MT" : "1T") + (run.status?.tools_active ? "+tools" : ""),
  );

  function fmtId(id: string): string {
    return id.length > 10 ? id.slice(0, 8) + "…" : id;
  }

  function statusBadgeCls(s: string): string {
    if (s === "completed") return "text-success";
    if (s === "errored") return "text-danger";
    if (s === "stopped") return "text-muted";
    return "text-accent";
  }
</script>

<div class="flex flex-col gap-6">
  <!-- Session header -->
  <div class="flex flex-wrap items-center justify-between gap-3">
    <div class="flex items-center gap-3 min-w-0">
      <h1 class="text-xl font-semibold tracking-tight text-fg shrink-0">
        Session <span class="font-mono text-fg-muted">{fmtId(run.sessionId ?? "")}</span>
      </h1>
      <span class="text-sm text-muted truncate">
        <span class="font-mono">{teacher}</span>
        <span class="mx-1.5 text-accent">←</span>
        <span class="font-mono">{judge}</span>
      </span>
      <span class="text-xs font-medium uppercase tracking-wide {statusBadgeCls(status)}">{status}</span>
      <span class="rounded-md border border-border bg-surface px-2 py-0.5 font-mono text-xs text-fg-muted">{modeBadge}</span>
    </div>
    <div class="flex items-center gap-2">
      {#if running}
        <Button variant="danger" onclick={stopRun}>Stop</Button>
      {/if}
      {#if done || aborted}
        <Button variant="secondary" onclick={() => resumeSession(run.sessionId!)}>Resume</Button>
      {/if}
      <Button variant="ghost" onclick={newDistillation}>New</Button>
    </div>
  </div>

  <!-- Sticky stat sub-bar -->
  <div class="sticky top-14 z-30 -mx-2 px-2 py-2 bg-bg/80 backdrop-blur-md space-y-3">
    <StatBar />
    <ProgressBar pct={run.progressPct} kept={run.kept} target={run.target} running={running} done={done} aborted={aborted} />
    {#if topicChips.length}
      <div class="flex flex-wrap gap-1.5">
        {#each topicChips as c}
          <span class="rounded-md border border-border bg-surface px-2 py-0.5 text-xs text-fg-muted">{c}</span>
        {/each}
      </div>
    {/if}
  </div>

  {#if run.lastError}
    <ErrorBanner message={run.lastError} onDismiss={() => (run.lastError = null)} />
  {/if}

  <ConversationsTable />

  <ExportRow />
</div>