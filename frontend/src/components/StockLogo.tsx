import { useState } from "react";
import stockLogos from "../data/stockLogos.json";

// Company logos: TradingView's public logo images, their ids looked up once for every stock in the sector lists
// (data/stockLogos.json). Shared by the Heatmap and Weekly Sectors (2026-11-22).
const LOGOS = stockLogos as Record<string, string>;

/**
 * A stock's company logo in a 22px circle. It stays hidden while it loads (no empty white circle on a slow network).
 * With no logo, or when the image fails, the symbol's first letter takes its place, so every row keeps the same shape.
 */
export function StockLogo({ symbol }: { symbol: string }) {
  const id = LOGOS[symbol];
  const [state, setState] = useState<"loading" | "ok" | "failed">(
    id ? "loading" : "failed",
  );
  if (state === "failed")
    return (
      <span className="stock-logo stock-logo-ok stock-logo-mono" aria-hidden="true">
        {symbol.charAt(0)}
      </span>
    );
  return (
    <img
      className={state === "ok" ? "stock-logo stock-logo-ok" : "stock-logo"}
      src={`https://s3-symbol-logo.tradingview.com/${id}.svg`}
      alt=""
      loading="lazy"
      decoding="async"
      onLoad={() => setState("ok")}
      onError={() => setState("failed")}
    />
  );
}
