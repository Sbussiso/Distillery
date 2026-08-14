<script lang="ts">
  import { sessions } from "../lib/state/sessions.svelte";
  import { openSession, deleteSession } from "../lib/actions";
  import Button from "./Button.svelte";
  import type { SessionMeta } from "../lib/types";

  function fmtDate(s: string | null | undefined): string {
    if (!s) return "—";
    const d = new Date(s);
    return Number.isNaN(d.getTime()) ? s : d.toLocaleString();
  }

  function statusCls(s: string): string {
    if (s === "completed") return "text-success";
    if (s === "errored") return "text-danger";
    if (s === "stopped") return "text-muted";
    return "text-accent";
  }

  function open(s: SessionMeta): void {
    openSession(s.id);
  }

  async function remove(s: SessionMeta, ev: MouseEvent): Promise<void> {
    ev.stopPropagation();
    const label = s.id.slice(0, 8);
    if (!confirm(`Delete session ${label}?\nThis removes its dataset on disk. Cannot be undone.`))
      return;
    await deleteSession(s.id);
  }
</script>

<section class="rounded-lg border border-border bg-surface shadow-sm">
  <div class="flex items-center justify-between p-4 border-b border-border">
    <h2 class="text-base font-semibold tracking-tight text-fg">Past distillations</h2>
    {#if sessions.loading}<span class="text-xs text-muted">loading…</span>{/if}
  </div>
  <div class="overflow-x-auto">
    <table class="w-full text-sm">
      <thead class="border-b border-border bg-surface-2">
        <tr>
          <th class="px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-muted">Session</th>
          <th class="px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-muted">Teacher</th>
          <th class="hidden md:table-cell px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-muted">Topics</th>
          <th class="hidden sm:table-cell px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-muted">Mode</th>
          <th class="px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-muted">Status</th>
          <th class="px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-muted">Kept</th>
          <th class="hidden lg:table-cell px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-muted">Updated</th>
          <th class="px-4 py-2.5"></th>
        </tr>
      </thead>
      <tbody class="divide-y divide-border">
        {#each sessions.rows as s (s.id)}
          <tr class="transition-colors hover:bg-surface-2 animate-row-in">
            <td class="px-4 py-3 font-mono text-xs text-fg-muted">{s.id.slice(0, 8)}…</td>
            <td class="px-4 py-3 font-mono text-xs text-fg truncate max-w-[16ch]">{s.teacher_model}</td>
            <td class="hidden md:table-cell px-4 py-3 text-fg-muted truncate max-w-[20ch]">{s.topics.join(", ") || "—"}</td>
            <td class="hidden sm:table-cell px-4 py-3 text-xs font-mono text-fg-muted">{sessions.mode(s)}</td>
            <td class="px-4 py-3 text-xs font-medium uppercase tracking-wide {statusCls(s.status)}">{s.status}</td>
            <td class="px-4 py-3 tabular-nums text-fg">{s.kept}/{s.target_count}</td>
            <td class="hidden lg:table-cell px-4 py-3 text-xs text-muted whitespace-nowrap">{fmtDate(s.updated_at)}</td>
            <td class="px-4 py-3">
              <div class="flex items-center justify-end gap-1">
                {#if s.status !== "running"}
                  <Button variant="ghost" onclick={() => open(s)}>Open</Button>
                {:else}
                  <Button variant="ghost" onclick={() => open(s)}>View</Button>
                {/if}
                <button
                  type="button"
                  title="Delete session"
                  aria-label="Delete session"
                  onclick={(e) => remove(s, e)}
                  class="grid h-9 w-9 place-items-center rounded-md text-muted transition-colors hover:bg-danger/10 hover:text-danger focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M10 11v6M14 11v6"/></svg>
                </button>
              </div>
            </td>
          </tr>
        {/each}
        {#if !sessions.rows.length}
          <tr>
            <td colspan="8" class="px-4 py-8 text-center text-fg-muted italic text-sm">
              No past distillations yet — start one above.
            </td>
          </tr>
        {/if}
      </tbody>
    </table>
  </div>
</section>