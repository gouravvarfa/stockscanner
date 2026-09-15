import { useEffect, useRef, useState } from "react";
import { searchFutures, type FutureContract } from "../../services/topBottomApi";

interface Props {
  onSelect: (contract: FutureContract) => void;
  selected: FutureContract | null;
}

export function FuturesSearchBox({ onSelect, selected }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<FutureContract[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }
    const handle = setTimeout(() => {
      setLoading(true);
      searchFutures(query)
        .then((r) => {
          setResults(r);
          setOpen(true);
        })
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(handle);
  }, [query]);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  return (
    <div ref={boxRef} className="tb-field tb-search-field" style={{ position: "relative" }}>
      <label>
        Search Futures
        <input
          type="text"
          value={selected ? `${selected.underlying} FUT — ${selected.expiry}` : query}
          onChange={(e) => {
            setQuery(e.target.value);
            if (selected) onSelect(null as unknown as FutureContract);
          }}
          onFocus={() => results.length > 0 && setOpen(true)}
          placeholder="e.g. RELIANCE, NIFTY, BANKNIFTY"
        />
      </label>
      <span className="tb-search-icon" aria-hidden="true">🔍</span>
      {open && (loading || results.length > 0) && (
        <div className="tb-search-dropdown">
          {loading && <div className="tb-search-empty">Searching…</div>}
          {!loading &&
            results.map((c) => (
              <button
                key={c.token}
                type="button"
                className="tb-search-result"
                onClick={() => {
                  onSelect(c);
                  setQuery("");
                  setOpen(false);
                }}
              >
                <div className="tb-search-result-title">{c.underlying} FUT</div>
                <div className="tb-search-result-meta">
                  Expiry: {c.expiry} · Exchange: {c.exch_seg}{c.is_index ? " · Index" : ""}
                </div>
              </button>
            ))}
          {!loading && results.length === 0 && <div className="tb-search-empty">No live futures contract found.</div>}
        </div>
      )}
    </div>
  );
}
