// The live run view state: session id, status snapshot, the rounds table
// (newest-first), the selected round for the trace panel, progress, and the
// last error. The WS reducer in stream.ts mutates this state directly.
//
// `liveConvs` (in-progress multi-turn/agentic conversations) and the
// single-turn `pendingAnswer` are kept as plain module state in stream.ts —
// they are scratch buffers, not reactive UI; only completed rounds get pushed
// here, exactly as the original app.js only touched the DOM on finalize.

import type { Grade, SessionStatus } from "../types";

export type RoundResult = "kept" | "rejected" | "grade failed";

export interface TraceStepView {
  kind: "call" | "result";
  step: number;
  content?: string | null;
  thinking?: string | null;
  name?: string | null;
  args?: Record<string, any> | null;
  result?: string | null;
  policy?: string | null;
  error?: string | null;
}

export interface TraceTurnView {
  idx: number; // 1-based
  q: string;
  a: string;
  th: string | null;
  steps: TraceStepView[];
}

export interface RoundRow {
  id: string; // conversation_id or synthetic for single-turn
  idx: number;
  question: string; // first question (truncated in the table view)
  turns: number;
  grade: Grade | null;
  result: RoundResult;
  toolsUsed: boolean;
  reasoning: string;
  trace: { turns: TraceTurnView[]; grade: Grade | null };
}

export class RunState {
  sessionId = $state<string | null>(null);
  active = $state(false);
  status = $state<SessionStatus | null>(null);
  rounds = $state<RoundRow[]>([]);
  selectedRoundId = $state<string | null>(null);
  kept = $state(0);
  target = $state(0);
  lastError = $state<string | null>(null);

  get selectedRound(): RoundRow | null {
    return this.rounds.find((r) => r.id === this.selectedRoundId) ?? null;
  }

  get progressPct(): number {
    return this.target
      ? Math.min(100, (this.kept / this.target) * 100)
      : 0;
  }

  get acceptRate(): string {
    if (!this.status) return "—";
    const total =
      this.status.kept + this.status.rejected + this.status.grade_failed;
    return total ? Math.round((this.status.kept / total) * 100) + "%" : "—";
  }

  reset(sessionId: string, target: number): void {
    this.sessionId = sessionId;
    this.active = true;
    this.status = null;
    this.rounds = [];
    this.selectedRoundId = null;
    this.kept = 0;
    this.target = target;
    this.lastError = null;
  }
}

export const run = new RunState();