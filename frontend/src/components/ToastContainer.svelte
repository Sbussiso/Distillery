<script lang="ts">
  import { toasts } from "../lib/state/toasts.svelte";
</script>

<div class="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
  {#each toasts.items as t (t.id)}
    <div
      class="animate-fade-in rounded-md border bg-surface px-4 py-3 text-sm shadow-lg {t.kind ===
      "error"
        ? "border-danger/30 text-fg"
        : t.kind === "ok"
          ? "border-success/30 text-fg"
          : "border-border text-fg"}"
    >
      {t.msg}
    </div>
  {/each}
</div>