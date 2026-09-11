const BADGE_STYLES: Record<string, string> = {
  "STRONG SETUP": "badge badge-strong",
  "GOOD SETUP": "badge badge-good",
  "MODERATE SETUP": "badge badge-moderate",
  "WEAK SETUP": "badge badge-weak",
  BULLISH: "badge badge-bullish",
  NEUTRAL: "badge badge-neutral",
  "HIGH RISK": "badge badge-highrisk",
  "BEARISH DIVERGENCE": "badge badge-highrisk",
  "NO DIVERGENCE": "badge badge-bullish",
  "SECTOR OUTPERFORMING": "badge badge-bullish",
  "SECTOR UNDERPERFORMING": "badge badge-weak",
};

export function Badge({ label }: { label: string }) {
  const cls = BADGE_STYLES[label] ?? "badge badge-neutral";
  return <span className={cls}>{label}</span>;
}
