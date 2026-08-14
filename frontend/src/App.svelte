<script lang="ts">
  import Header from "./components/Header.svelte";
  import SetupForm from "./components/SetupForm.svelte";
  import RunView from "./components/RunView.svelte";
  import SessionsTable from "./components/SessionsTable.svelte";
  import ToastContainer from "./components/ToastContainer.svelte";
  import { run } from "./lib/state/run.svelte";
</script>

<Header />

<main class="mx-auto max-w-6xl px-6 py-8 flex flex-col gap-8">
  {#if run.sessionId}
    <RunView />
  {:else}
    <SetupForm />
  {/if}
  <SessionsTable />
</main>

<ToastContainer />