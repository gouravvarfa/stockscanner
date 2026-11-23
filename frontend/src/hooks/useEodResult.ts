import { useEffect, useState } from "react";

/**
 * End-of-day results built from NSE's daily bhavcopy (2026-11-23): Cup Breakout and Value Buy over every NSE stock,
 * computed once a day and shipped with the site as /eod/<name>.json - so the page has a full result instantly, without
 * a scan. A live scan the user runs afterwards is newer and takes over.
 */
export type EodMeta = { data_as_of: string; generated_at: string; source: string };

/** undefined while the file is loading, null when there is none. */
export function useEodResult<T>(name: "cup" | "value_buy" | "setup"): (T & EodMeta) | null | undefined {
  const [data, setData] = useState<(T & EodMeta) | null | undefined>(undefined);
  useEffect(() => {
    let alive = true;
    fetch(`/eod/${name}.json?d=${new Date().toISOString().slice(0, 10)}`, { cache: "no-cache" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => { if (alive) setData(j && j.data_as_of ? (j as T & EodMeta) : null); })
      .catch(() => { if (alive) setData(null); });
    return () => { alive = false; };
  }, [name]);
  return data;
}

/** The live result when it is newer than the end-of-day one, otherwise the end-of-day one. */
export function newerOf<T extends { finished_at?: string }>(live: T | null | undefined, eod: (T & EodMeta) | null | undefined): { shown: T | null; isEod: boolean } {
  if (live && (!eod || new Date(live.finished_at ?? 0).getTime() > new Date(eod.generated_at).getTime())) return { shown: live, isEod: false };
  return { shown: eod ?? null, isEod: !!eod };
}
