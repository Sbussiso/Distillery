<script lang="ts">
  import { meta } from "../lib/state/meta.svelte";

  // unknown while we've never heard back; ok/bad once health resolves.
  let state = $derived(
    meta.ollamaHealth === null ? "unknown" : meta.ollamaHealth.ok ? "ok" : "bad",
  ) as "ok" | "bad" | "unknown";

  const dot: Record<string, string> = {
    ok: "bg-success",
    bad: "bg-danger",
    unknown: "bg-muted animate-pulse-dot",
  };
  const label: Record<string, string> = {
    ok: "Ollama online",
    bad: "Ollama offline",
    unknown: "Checking…",
  };
</script>

<span class="inline-flex items-center gap-2 rounded-full border border-border bg-surface pl-2 pr-3 py-1 text-xs font-medium shadow-xs">
  <span class="h-2 w-2 rounded-full {dot[state]}"></span>
  {label[state]}
</span>