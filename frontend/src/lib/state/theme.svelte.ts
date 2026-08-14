// Theme store: class-toggle dark mode on <html>. The no-FOUC boot script in
// index.html applies the class before paint; this store keeps the toggle in
// sync and persists the choice.

export type Theme = "light" | "dark";

const STORAGE_KEY = "distillery-theme";

export class ThemeState {
  current = $state<Theme>("light");

  init(): void {
    let t: Theme | null = null;
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === "light" || stored === "dark") t = stored;
    } catch {
      // localStorage unavailable; fall through
    }
    if (t === null) {
      const prefersDark =
        typeof window !== "undefined" &&
        window.matchMedia("(prefers-color-scheme: dark)").matches;
      t = prefersDark ? "dark" : "light";
    }
    this.apply(t);
  }

  set(t: Theme): void {
    this.apply(t);
    try {
      localStorage.setItem(STORAGE_KEY, t);
    } catch {
      // ignore
    }
  }

  toggle(): void {
    this.set(this.current === "dark" ? "light" : "dark");
  }

  private apply(t: Theme): void {
    this.current = t;
    if (typeof document !== "undefined") {
      document.documentElement.classList.toggle("dark", t === "dark");
    }
  }
}

export const theme = new ThemeState();