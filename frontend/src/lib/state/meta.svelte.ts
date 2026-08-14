// Environment metadata: Ollama health + models, judge provider suggestions,
// tool presets. Loaded once at boot (and health is polled).

import type { HealthStatus, JudgeProvider, OllamaModel, ToolPreset } from "../types";

export class MetaState {
  ollamaHealth = $state<HealthStatus | null>(null);
  ollamaChecking = $state(true);
  models = $state<OllamaModel[]>([]);
  modelsLoading = $state(false);
  modelsError = $state<string | null>(null);
  providers = $state<JudgeProvider[]>([]);
  toolPresets = $state<ToolPreset[]>([]);

  get healthOk(): boolean {
    return this.ollamaHealth?.ok ?? false;
  }

  get healthLabel(): string {
    if (this.ollamaChecking && this.ollamaHealth === null) return "checking…";
    return this.ollamaHealth?.ok ? "connected" : "down";
  }
}

export const meta = new MetaState();