// Initial data load + recurring health poll. Called once from main.ts before
// mount so the first paint is populated. Mirrors the original app's
// DOMContentLoaded boot sequence.

import { api } from "./api";
import { meta } from "./state/meta.svelte";
import { sessions } from "./state/sessions.svelte";
import { theme } from "./state/theme.svelte";

let healthTimer: ReturnType<typeof setInterval> | null = null;

async function checkHealth(): Promise<void> {
  meta.ollamaChecking = true;
  try {
    meta.ollamaHealth = await api.ollamaHealth();
  } catch {
    meta.ollamaHealth = { ok: false, detail: "unreachable" };
  } finally {
    meta.ollamaChecking = false;
  }
}

async function refreshModels(): Promise<void> {
  meta.modelsLoading = true;
  meta.modelsError = null;
  try {
    meta.models = await api.ollamaModels();
    // Pre-select the first model if none chosen yet.
    if (!meta.models.length) {
      meta.modelsError = "no models — run `ollama pull <model>`";
    } else {
      // The form observes meta.models; component logic will auto-select.
    }
  } catch (e) {
    meta.modelsError = "failed to list models: " + (e as Error).message;
  } finally {
    meta.modelsLoading = false;
  }
}

async function loadJudges(): Promise<void> {
  try {
    meta.providers = await api.judgeProviders();
  } catch {
    // providers are only suggestions; ignore failure
  }
}

async function loadToolPresets(): Promise<void> {
  try {
    meta.toolPresets = await api.toolPresets();
  } catch {
    meta.toolPresets = [];
  }
}

export function boot(): void {
  theme.init();
  void refreshModels();
  void loadJudges();
  void loadToolPresets();
  void checkHealth();
  void sessions.reload();
  if (healthTimer === null) {
    healthTimer = setInterval(() => void checkHealth(), 10_000);
  }
}

export function refreshModelsNow(): Promise<void> {
  return refreshModels();
}

export function checkHealthNow(): Promise<void> {
  return checkHealth();
}