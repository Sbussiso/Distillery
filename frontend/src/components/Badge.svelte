<script lang="ts">
  type Kind = "kept" | "rejected" | "failed" | "aborted" | "error" | "running";
  let { kind }: { kind: Kind } = $props();

  const styles: Record<Kind, string> = {
    kept: "border-success/25 bg-success/10 text-success",
    rejected: "border-danger/25 bg-danger/10 text-danger",
    failed: "border-warn/25 bg-warn/10 text-warn",
    aborted: "border-border bg-surface-3 text-muted",
    error: "border-danger/25 bg-danger/10 text-danger",
    running: "border-accent/25 bg-accent/10 text-accent",
  };
  const labels: Record<Kind, string> = {
    kept: "kept",
    rejected: "rejected",
    failed: "grade failed",
    aborted: "aborted",
    error: "error",
    running: "running",
  };
</script>

<span class="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium {styles[kind]}">
  {#if kind === "running"}<span class="h-1.5 w-1.5 rounded-full bg-current animate-pulse-dot"></span>{/if}
  {labels[kind]}
</span>