<script lang="ts">
  import HealthPill from "./HealthPill.svelte";
  import ThemeToggle from "./ThemeToggle.svelte";
</script>

<header class="sticky top-0 z-40 h-14 border-b border-border bg-bg/80 backdrop-blur-md">
  <div class="mx-auto max-w-6xl px-6 h-full flex items-center justify-between">
    <div class="flex items-center gap-2.5 min-w-0">
      <span class="grid size-7 place-items-center rounded-md bg-linear-to-r from-grad-from via-grad-via to-grad-to bg-[length:200%_auto] shadow-sm">
        <span class="text-base" aria-hidden="true">⚗️</span>
      </span>
      <div class="flex items-baseline gap-2 min-w-0">
        <span class="text-lg font-semibold tracking-tight text-fg">Distillery</span>
        <span class="hidden sm:inline truncate text-xs text-muted">distil a teacher LLM into a fine-tuning set</span>
      </div>
    </div>
    <div class="flex items-center gap-3">
      <HealthPill />
      <ThemeToggle />
    </div>
  </div>
</header>