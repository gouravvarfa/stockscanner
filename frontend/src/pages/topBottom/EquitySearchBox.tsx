import { useEffect, useRef, useState } from "react";
import { searchEquities } from "../../services/topBottomApi";

interface Props {
  selected: string;
  onSelect: (symbol: string) => void;
}

/** Symbols come from the A Group universe (A_Group_Stock_List.xlsx) via the
 *  backend — the same list the main scanner runs on, so nothing outside it
 *  can be picked here. */
export function EquitySearchBox({ selected, onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<string[]>([]);
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
      searchEquities(query)
        .then((r) => {
          setResults(r);
          setOpen(true);
        })
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 200);
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
        A Group Stock
        <input
          type="text"
          value={open || query ? query : selected}
          onChange={(e) => setQuery(e.target.value.toUpperCase())}
          onFocus={() => {
            setQuery("");
            setOpen(true);
          }}
          placeholder="e.g. ADANIGREEN"
        />
      </label>
      <span className="tb-search-icon" aria-hidden="true">🔍</span>
      {open && (loading || query.trim().length > 0) && (
        <div className="tb-search-dropdown">
          {loading && <div className="tb-search-empty">Searching…</div>}
          {!loading &&
            results.map((s) => (
              <button
                key={s}
                type="button"
                className="tb-search-result"
                onClick={() => {
                  onSelect(s);
                  setQuery("");
                  setOpen(false);
                }}
              >
                <div className="tb-search-result-title">{s}</div>
                <div className="tb-search-result-meta">NSE Equity · A Group</div>
              </button>
            ))}
          {!loading && results.length === 0 && (
            <div className="tb-search-empty">No A Group stock matches.</div>
          )}
        </div>
      )}
    </div>
  );
}
