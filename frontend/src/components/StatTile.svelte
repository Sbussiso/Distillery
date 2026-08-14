<script lang="ts">
  type Dot = "success" | "danger" | "warn" | "muted" | "accent" | "info";
  let {
    label,
    value,
    dot,
    mono = false,
  }: {
    label: string;
    value: string | number;
    dot: Dot;
    mono?: boolean;
  } = $props();

  const dotCls: Record<Dot, string> = {
    success: "bg-success",
    danger: "bg-danger",
    warn: "bg-warn",
    muted: "bg-muted",
    accent: "bg-accent",
    info: "bg-info",
  };

  let bumping = $state(false);
  let lastBump = 0;
  let prev: string | number | undefined = undefined;

  // Flash the tile frame once when its value ticks (throttled to 200ms so a
  // fast stream can't thrash). spec §5.6.
  $effect(() => {
    if (prev === undefined) {
      prev = value;
      return;
    }
    if (value !== prev) {
      prev = value;
      const now = Date.now();
      if (now - lastBump >= 200) {
        lastBump = now;
        bumping = true;
        setTimeout(() => (bumping = false), 130);
      }
    }
  });
</script>

<div class="bg-surface px-3 py-2.5 flex flex-col gap-0.5 {bumping ? "animate-stat-bump" : ""}">
  <div class="flex items-center gap-1.5">
    <span class="h-1.5 w-1.5 rounded-full {dotCls[dot]}"></span>
    <span class="text-[11px] uppercase tracking-wide text-muted">{label}</span>
  </div>
  <div class="text-lg font-semibold tabular-nums text-fg {mono ? "font-mono" : ""}">{value}</div>
</div>