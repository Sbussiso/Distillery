<script lang="ts">
  let {
    pct,
    kept,
    target,
    topic = "",
    running = false,
    done = false,
    aborted = false,
  }: {
    pct: number;
    kept: number;
    target: number;
    topic?: string;
    running?: boolean;
    done?: boolean;
    aborted?: boolean;
  } = $props();

  let label = $derived(done ? "complete" : aborted ? "aborted" : "distilling");
  let fillCls = $derived(
    done
      ? "bg-success"
      : aborted
        ? "bg-muted"
        : "bg-linear-to-r from-grad-from via-grad-via to-grad-to bg-[length:200%_auto]",
  );
  let live = $derived(running && !done);
</script>

<div class="w-full" data-running={live ? "" : undefined} data-done={done ? "" : undefined}>
  <div class="flex justify-between text-xs text-muted mb-1.5">
    <span>{label} · {topic || "distillation"}</span>
    <span class="font-mono text-accent tabular-nums">{kept}/{target} · {Math.round(pct)}%</span>
  </div>

  <div class="relative h-2.5 w-full overflow-hidden rounded-full bg-surface-3 border border-border">
    <div
      class="absolute inset-y-0 left-0 rounded-full {fillCls} {live
        ? "animate-flow shadow-[0_0_12px_var(--glow)]"
        : ""} transition-[width] duration-300 ease-out"
      style="width: {pct}%"
    ></div>

    {#if live}
      <div class="pointer-events-none absolute inset-0 overflow-hidden rounded-full">
        <div class="absolute inset-y-0 -left-1/3 w-1/3 bg-linear-to-r from-transparent via-white/25 to-transparent animate-shimmer skew-x-12"></div>
      </div>
      <div
        class="absolute top-1/2 -translate-y-1/2 size-2 rounded-full bg-grad-via shadow-[0_0_10px_var(--glow)] animate-pulse-dot"
        style="left: calc({pct}% - 4px)"
      ></div>
    {/if}
  </div>

  <div class="mt-1 flex justify-between text-[10px] font-mono text-muted">
    <span>0</span><span>25</span><span>50</span><span>75</span><span>100</span>
  </div>
</div>