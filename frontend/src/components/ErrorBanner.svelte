<script lang="ts">
  let { message, onDismiss }: { message: string; onDismiss?: () => void } = $props();
</script>

<div class="flex items-start gap-3 rounded-lg border border-danger/30 bg-danger/5 px-4 py-3 animate-fade-in">
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-danger shrink-0 mt-0.5">
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="8" x2="12" y2="12" />
    <line x1="12" y1="16" x2="12.01" y2="16" />
  </svg>
  <div class="flex-1 text-sm text-fg">
    <div class="font-medium text-danger">Something went wrong</div>
    <div class="text-fg-muted font-mono text-xs mt-0.5 whitespace-pre-wrap break-words">{message}</div>
  </div>
  {#if onDismiss}
    <button
      type="button"
      onclick={onDismiss}
      class="text-muted hover:text-fg transition-colors shrink-0"
      aria-label="Dismiss error"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
    </button>
  {/if}
</div>