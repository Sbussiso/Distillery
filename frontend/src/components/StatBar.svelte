<script lang="ts">
  import { run } from "../lib/state/run.svelte";
  import StatTile from "./StatTile.svelte";

  // The 7 live counters. Before the initial status snapshot, show "–".
  let kept = $derived(run.status?.kept ?? "–");
  let rejected = $derived(run.status?.rejected ?? "–");
  let gradeFailed = $derived(run.status?.grade_failed ?? "–");
  let aborted = $derived(run.status?.aborted ?? "–");
  let errors = $derived(run.status?.error_count ?? "–");
  let rate = $derived(run.acceptRate);
  let tokens = $derived(run.status?.tokens?.total ?? "–");
</script>

<div class="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-7 gap-px bg-border rounded-lg border border-border overflow-hidden">
  <StatTile label="kept" value={kept} dot="success" />
  <StatTile label="rejected" value={rejected} dot="danger" />
  <StatTile label="grade failed" value={gradeFailed} dot="warn" />
  <StatTile label="aborted" value={aborted} dot="muted" />
  <StatTile label="errors" value={errors} dot="danger" />
  <StatTile label="accept rate" value={rate} dot="accent" />
  <StatTile label="judge tokens" value={tokens} dot="info" mono />
</div>