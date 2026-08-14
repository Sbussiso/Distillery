<script lang="ts">
  import type { Snippet } from "svelte";

  type Variant = "primary" | "cta" | "secondary" | "ghost" | "danger" | "danger-solid" | "icon";

  let {
    variant = "secondary",
    type = "button",
    disabled = false,
    title,
    ariaLabel,
    onclick,
    children,
    class: klass = "",
  }: {
    variant?: Variant;
    type?: "button" | "submit";
    disabled?: boolean;
    title?: string;
    ariaLabel?: string;
    onclick?: (e: MouseEvent) => void;
    children: Snippet;
    class?: string;
  } = $props();

  const base =
    "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-all duration-150 " +
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 " +
    "disabled:opacity-50 disabled:pointer-events-none";

  const variants: Record<Variant, string> = {
    primary:
      "h-9 px-4 bg-linear-to-r from-grad-from via-grad-via to-grad-to bg-[length:200%_auto] text-accent-fg text-sm font-semibold shadow-xs hover:bg-[position:100%_50%] hover:shadow-md",
    cta:
      "h-10 px-5 bg-linear-to-r from-grad-from via-grad-via to-grad-to bg-[length:200%_auto] text-accent-fg text-base font-semibold shadow-sm hover:bg-[position:100%_50%] hover:shadow-md",
    secondary: "h-9 px-3 border border-border bg-surface text-fg text-sm shadow-xs hover:bg-surface-2",
    ghost: "h-9 px-3 text-sm text-fg-muted hover:bg-surface-2 hover:text-fg",
    danger: "h-9 px-3 border border-danger/30 bg-danger/10 text-danger text-sm hover:bg-danger hover:text-white",
    "danger-solid": "h-9 px-4 bg-danger text-white text-sm hover:bg-danger/90",
    icon: "h-9 w-9 text-fg-muted hover:bg-surface-2 hover:text-fg",
  };
</script>

<button {type} {disabled} {title} aria-label={ariaLabel} onclick={onclick} class="{base} {variants[variant]} {klass}">
  {@render children()}
</button>