// Past-sessions list (GET /api/distill/sessions). Refreshed at boot, after a
// run completes, and on demand.

import { api } from "../api";
import type { SessionMeta } from "../types";

export class SessionsState {
  rows = $state<SessionMeta[]>([]);
  loading = $state(false);

  async reload(): Promise<void> {
    this.loading = true;
    try {
      this.rows = await api.listSessions();
    } catch {
      // leave existing rows in place on failure
    } finally {
      this.loading = false;
    }
  }

  mode(s: SessionMeta): string {
    return (
      [s.multi_turn ? "MT" : null, s.tools_active ? "tools" : null]
        .filter(Boolean)
        .join("+") || "1T"
    );
  }
}

export const sessions = new SessionsState();