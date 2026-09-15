const LABELS: Record<string, string> = {
  ANGEL_ONE: "Angel One",
  TRADINGVIEW: "TradingView",
};

export function SourceBadge({ source }: { source: string | null | undefined }) {
  if (!source) return <span className="source-badge source-badge-unknown">—</span>;
  const key = source.toLowerCase();
  const cls = key === "angel_one" || key === "tradingview" ? key : "unknown";
  return <span className={`source-badge source-badge-${cls}`}>{LABELS[source.toUpperCase()] ?? source}</span>;
}
