// Two UI themes: "aurora" (colourful gradients) and "midnight" (the original navy + teal).
// The choice is stored per browser; storage failures fall back to the default silently.
import { useEffect, useState } from "react";

export type Theme = "aurora" | "midnight";
const KEY = "acfm.theme";
export const DEFAULT_THEME: Theme = "aurora";

export function initialTheme(): Theme {
  try { const v = localStorage.getItem(KEY); if (v === "aurora" || v === "midnight") return v; } catch { /* storage unavailable */ }
  return DEFAULT_THEME;
}

export function applyTheme(t: Theme) {
  document.documentElement.dataset.theme = t;
}

const THEMES: { id: Theme; label: string }[] = [
  { id: "aurora", label: "Aurora" },
  { id: "midnight", label: "Midnight" },
];

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  useEffect(() => {
    applyTheme(theme);
    try { localStorage.setItem(KEY, theme); } catch { /* storage unavailable */ }
  }, [theme]);
  return (
    <div className="theme-toggle" role="group" aria-label="Colour theme">
      {THEMES.map((t) => (
        <button key={t.id} type="button" aria-pressed={theme === t.id} onClick={() => setTheme(t.id)} title={`${t.label} theme`}>
          <span className={`swatch swatch-${t.id}`} aria-hidden="true" /><span className="theme-label">{t.label}</span>
        </button>
      ))}
    </div>
  );
}
