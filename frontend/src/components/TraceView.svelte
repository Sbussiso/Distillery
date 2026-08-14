<script lang="ts">
  import type { RoundRow } from "../lib/state/run.svelte";

  let { round }: { round: RoundRow } = $props();

  function truncate(s: string | null | undefined, n: number): string {
    if (!s) return "";
    return s.length > n ? s.slice(0, n) + "…" : s;
  }
</script>

<div class="bg-surface-2 px-4 py-4 border-t border-border animate-fade-in">
  {#if round.reasoning}
    <div class="text-xs text-muted mb-3 italic">{round.reasoning}</div>
  {/if}

  <div class="space-y-3 border-l-2 border-accent pl-4">
    {#each round.trace.turns as t, i (i)}
      <div>
        <div class="text-[10px] font-semibold uppercase tracking-wide text-accent mb-1">Turn {i + 1}</div>

        <div class="text-sm text-fg">
          <span class="text-xs font-semibold uppercase tracking-wide text-accent mr-1.5">Q</span>{t.q}
        </div>

        {#each t.steps as s, j (j)}
          {#if s.kind === "call"}
            <div class="my-1.5 flex items-start gap-2">
              <span class="rounded-md border border-accent/25 bg-accent/10 px-2 py-0.5 font-mono text-xs text-accent shrink-0">tool call</span>
              <span class="font-mono text-xs text-fg-muted whitespace-pre-wrap">{truncate(s.content || "(no content)", 200)}</span>
            </div>
          {:else}
            <div class="my-1.5 rounded-md border border-border bg-surface p-2 font-mono text-xs text-fg-muted whitespace-pre-wrap">
              <span class="rounded-md border border-accent/25 bg-accent/10 px-2 py-0.5 text-accent mr-1.5">result</span>
              <b class="text-fg">{s.name}</b>{#if s.policy}<span class="text-muted"> [{s.policy}]</span>{/if}
              {truncate(s.result || "", 300)}
              {#if s.error}<span class="text-danger"> {s.error}</span>{/if}
            </div>
          {/if}
        {/each}

        {#if t.th}
          <div class="my-1.5 rounded-md border border-border bg-surface p-3 font-mono text-xs leading-relaxed text-fg-muted whitespace-pre-wrap">
            <div class="text-[10px] font-semibold uppercase tracking-wide text-muted mb-1">thinking</div>
            {truncate(t.th, 400)}
          </div>
        {/if}

        <div class="text-sm text-fg">
          <span class="text-xs font-semibold uppercase tracking-wide text-success mr-1.5">A</span>{truncate(t.a || "", 400)}
        </div>
      </div>
    {/each}
  </div>
</div>