// Shared Tailwind class recipes for form primitives (spec §5.2–5.4). Kept in
// one place so every input/select/textarea/checkbox looks identical and a
// tweak propagates everywhere.

export const inputCls =
  "flex h-9 w-full rounded-md border border-border bg-surface px-3 py-1 text-sm text-fg shadow-xs transition-colors placeholder:text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:border-accent disabled:cursor-not-allowed disabled:opacity-50";

export const selectCls =
  "flex h-9 w-full rounded-md border border-border bg-surface px-3 py-1 text-sm text-fg shadow-xs transition-colors appearance-none pr-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:border-accent disabled:cursor-not-allowed disabled:opacity-50";

export const smallInputCls =
  "flex h-8 w-full rounded-md border border-border bg-surface px-2.5 text-sm text-fg shadow-xs transition-colors placeholder:text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:border-accent";

export const smallSelectCls =
  "flex h-8 w-full rounded-md border border-border bg-surface px-2 text-xs text-fg shadow-xs transition-colors appearance-none pr-7 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:border-accent";

export const textareaMonoCls =
  "flex min-h-24 w-full rounded-md border border-border bg-surface p-3 font-mono text-xs leading-relaxed text-fg shadow-xs transition-colors placeholder:text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:border-accent";

export const textareaCls =
  "flex min-h-20 w-full rounded-md border border-border bg-surface p-3 text-sm leading-relaxed text-fg shadow-xs transition-colors placeholder:text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:border-accent";

export const checkCls =
  "h-4 w-4 rounded-[5px] border border-border-strong bg-surface shadow-xs accent-accent cursor-pointer focus-visible:ring-2 focus-visible:ring-accent/50";

export const labelCls = "text-sm font-medium text-fg";

export const helperCls = "text-xs text-muted";

export const numberInputCls =
  inputCls + " [appearance:textfield] [&::-webkit-inner-spin-button]:opacity-0 [&::-webkit-outer-spin-button]:opacity-0";

// Chevron SVG injected next to selects (appearance-none removes the native one).
export const chevronSvg =
  '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted"><path d="m6 9 6 6 6-6"/></svg>';