/**
 * Reads the scanner's own CSS custom properties (index.css) so the chart
 * always matches the app's current light/dark theme instead of carrying
 * its own hardcoded palette.
 */
export interface ChartThemeColors {
  background: string;
  text: string;
  border: string;
  grid: string;
  success: string;
  danger: string;
  accent: string;
  purple: string;
  warning: string;
  muted: string;
}

function cssVar(name: string, fallback: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

export function getChartThemeColors(): ChartThemeColors {
  return {
    background: cssVar("--bg-surface", "#ffffff"),
    text: cssVar("--text-primary", "#0f172a"),
    border: cssVar("--border", "#e4e8ef"),
    grid: cssVar("--bg-hover", "#f1f5fb"),
    success: cssVar("--success", "#16a34a"),
    danger: cssVar("--danger", "#dc2626"),
    accent: cssVar("--accent", "#2563eb"),
    purple: cssVar("--purple", "#7c3aed"),
    warning: cssVar("--warning", "#d97706"),
    muted: cssVar("--text-muted", "#64748b"),
  };
}
