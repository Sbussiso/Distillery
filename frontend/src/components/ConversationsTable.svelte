<script lang="ts">
  import { run } from "../lib/state/run.svelte";
  import { form } from "../lib/state/form.svelte";
  import Badge from "./Badge.svelte";
  import TraceView from "./TraceView.svelte";
  import type { RoundResult } from "../lib/state/run.svelte";

  function badgeKind(r: RoundResult): "kept" | "rejected" | "failed" {
    return r === "grade failed" ? "failed" : r;
  }

  function gradeCls(score: number | null | undefined): string {
    if (score == null) return "text-muted";
    return score >= form.minScore ? "text-success" : "text-danger";
  }

  function select(id: string): void {
    run.selectedRoundId = run.selectedRoundId === id ? null : id;
  }
</script>

<div class="overflow-hidden rounded-lg border border-border bg-surface shadow-sm">
  <div class="overflow-x-auto">
    <table class="w-full text-sm">
      <thead class="border-b border-border bg-surface-2">
        <tr>
          <th class="px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-muted w-10">#</th>
          <th class="px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-muted">Question</th>
          <th class="px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-muted w-16">Turns</th>
          <th class="px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-muted w-20">Grade</th>
          <th class="px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-muted w-28">Result</th>
          <th class="hidden sm:table-cell px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-muted w-16">Tools</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-border">
        {#each run.rounds as r (r.id)}
          <tr
            class="cursor-pointer transition-colors hover:bg-surface-2 animate-row-in {run.selectedRoundId === r.id ? "bg-surface-2" : ""}"
            onclick={() => select(r.id)}
          >
            <td class="px-4 py-3 font-mono text-xs text-muted">{r.idx}</td>
            <td class="px-4 py-3 text-fg">
              <span class="block truncate max-w-[40ch]">{r.question}</span>
            </td>
            <td class="px-4 py-3 tabular-nums text-fg-muted">{r.turns}</td>
            <td class="px-4 py-3 tabular-nums font-mono {gradeCls(r.grade?.score)}">
              {r.grade?.score != null ? `${r.grade.score}/10` : "—"}
            </td>
            <td class="px-4 py-3"><Badge kind={badgeKind(r.result)} /></td>
            <td class="hidden sm:table-cell px-4 py-3 text-fg-muted text-xs">{r.toolsUsed ? "✓" : "—"}</td>
          </tr>
          {#if run.selectedRoundId === r.id}
            <tr>
              <td colspan="6" class="p-0"><TraceView round={r} /></td>
            </tr>
          {/if}
        {/each}
        {#if !run.rounds.length}
          <tr>
            <td colspan="6" class="px-4 py-10 text-center text-fg-muted italic text-sm">
              No conversations yet — waiting for the judge to ask the first question…
            </td>
          </tr>
        {/if}
      </tbody>
    </table>
  </div>
</div>