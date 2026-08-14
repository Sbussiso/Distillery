// Small transient toast queue (replaces the original alert()). Each toast
// auto-dismisses after 4s. Rendered by a Toasts.svelte component near the root.

export type ToastKind = "info" | "error" | "ok";

export interface Toast {
  id: number;
  msg: string;
  kind: ToastKind;
  leaving: boolean;
}

let nextId = 1;

export class ToastState {
  items = $state<Toast[]>([]);

  push(msg: string, kind: ToastKind = "info"): void {
    const id = nextId++;
    this.items.push({ id, msg, kind, leaving: false });
    setTimeout(() => this.dismiss(id), 4000);
  }

  dismiss(id: number): void {
    const t = this.items.find((x) => x.id === id);
    if (!t) return;
    t.leaving = true;
    setTimeout(() => {
      this.items = this.items.filter((x) => x.id !== id);
    }, 300);
  }
}

export const toasts = new ToastState();