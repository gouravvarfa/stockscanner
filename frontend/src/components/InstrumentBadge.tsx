export type InstrumentType = "FUTURE" | "EQUITY";

/** Small FUTURE / EQUITY tag next to a symbol. Display only — the backend
 *  classification (services/instrument_classifier.py) is the single source. */
export function InstrumentBadge({ type }: { type?: InstrumentType | string | null }) {
  if (type !== "FUTURE" && type !== "EQUITY") return null;
  return <span className={`instrument-badge instrument-badge-${type.toLowerCase()}`}>{type}</span>;
}
