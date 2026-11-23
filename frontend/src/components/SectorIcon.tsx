/**
 * A small line icon for each Weekly Sectors sector (2026-11-23): bank columns, pill, car, chip, bolt... drawn inline
 * (24x24, currentColor) so it follows the card's colour in light and dark mode.
 */
const PATHS: Record<string, string> = {
  bank: "M3 10h18M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 20h18M12 3l9 5H3z",
  psu_bank: "M3 10h18M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 20h18M12 3l9 5H3z",
  pvt_bank: "M3 10h18M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 20h18M12 3l9 5H3z",
  fin_service: "M7 5h10M7 9h10M9 5c4 0 4 8 0 8H7l7 6",
  capital_markets: "M3 20h18M6 16v-4M10 16V8M14 16v-6M18 16V5",
  pharma: "M10.5 3.5a5 5 0 0 1 7 7l-7 7a5 5 0 0 1-7-7zM7 7l7 7",
  healthcare: "M3 12h4l2-5 4 10 2-5h6",
  realty: "M3 11l9-7 9 7M5 10v10h14V10M10 20v-6h4v6",
  infra: "M3 20h18M5 20V9l7-5 7 5v11M9 20v-5h6v5M12 4v3",
  auto: "M5 16h14M3 16v-3l2-5h14l2 5v3M7 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM17 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
  fmcg: "M3 4h2l2.5 11h11L21 8H6.5M9 20a1 1 0 1 0 0-2 1 1 0 0 0 0 2zM18 20a1 1 0 1 0 0-2 1 1 0 0 0 0 2z",
  metal: "M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5",
  energy: "M13 2L4 14h7l-1 8 9-12h-7z",
  oil_gas: "M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z",
  it: "M7 7h10v10H7zM10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4",
  media: "M3 6h18v12H3zM8 21h8M10 10l5 2.5-5 2.5z",
  pse: "M4 21V4M4 4h12l-2 4 2 4H4",
  cpse: "M4 21V4M4 4h12l-2 4 2 4H4",
  defence: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
  chemicals: "M9 3h6M10 3v6L4.5 19a1.5 1.5 0 0 0 1.3 2h12.4a1.5 1.5 0 0 0 1.3-2L14 9V3M7 15h10",
  consumer_durables: "M5 3h14v18H5zM5 8h14M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
};

/** Each sector's own colours (2026-11-23, user: colourful like the stock logos) - a gradient tile with a white icon. */
export const SECTOR_COLORS: Record<string, [string, string]> = {
  bank: ["#2563eb", "#1e40af"], psu_bank: ["#1d4ed8", "#172554"], pvt_bank: ["#0284c7", "#075985"],
  fin_service: ["#0d9488", "#115e59"], capital_markets: ["#4f46e5", "#3730a3"], pharma: ["#10b981", "#047857"],
  healthcare: ["#f43f5e", "#be123c"], realty: ["#b45309", "#78350f"], infra: ["#f97316", "#c2410c"],
  auto: ["#ef4444", "#991b1b"], fmcg: ["#22c55e", "#15803d"], metal: ["#64748b", "#334155"],
  energy: ["#f59e0b", "#d97706"], oil_gas: ["#0f172a", "#334155"], it: ["#8b5cf6", "#6d28d9"],
  media: ["#ec4899", "#be185d"], pse: ["#ea580c", "#9a3412"], cpse: ["#dc2626", "#7f1d1d"],
  defence: ["#4d7c0f", "#365314"], chemicals: ["#06b6d4", "#0e7490"], consumer_durables: ["#a855f7", "#7e22ce"],
};

/** The coloured tile with the sector's icon. */
export function SectorLogo({ sectorKey, size = 34 }: { sectorKey: string; size?: number }) {
  const [a, b] = SECTOR_COLORS[sectorKey] ?? ["#64748b", "#334155"];
  return (
    <span className="sector-logo" style={{ width: size, height: size, background: `linear-gradient(135deg, ${a}, ${b})` }}>
      <SectorIcon sectorKey={sectorKey} size={Math.round(size * 0.55)} />
    </span>
  );
}

export function SectorIcon({ sectorKey, size = 18 }: { sectorKey: string; size?: number }) {
  const d = PATHS[sectorKey] ?? "M4 20V10M10 20V4M16 20v-7M22 20H2";
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}
