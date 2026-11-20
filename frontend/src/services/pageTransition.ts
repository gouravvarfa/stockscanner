import type { MouseEvent } from "react";
import { flushSync } from "react-dom";

/**
 * Smooth page changes (2026-11-20): the content area cross-fades into the next page using the browser's View
 * Transitions API, while the sidebar and top bar stay put (see `view-transition-name: page` in design.css).
 * The app uses <BrowserRouter>, where React Router's own `viewTransition` option does nothing, so the menu links
 * call this from their onClick. Falls back to the normal instant navigation when the browser has no
 * startViewTransition, the user prefers reduced motion, or the click opens a new tab/window.
 */
type DocWithVT = Document & { startViewTransition?: (cb: () => void) => { finished: Promise<void> } };

export function canAnimatePageChange(): boolean {
  if (typeof document === "undefined") return false;
  const doc = document as DocWithVT;
  if (typeof doc.startViewTransition !== "function") return false;
  try {
    return !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return true;
  }
}

/** onClick for a menu link: animates the change when possible; otherwise lets the link navigate as usual. */
export function navigateSmoothly(e: MouseEvent<HTMLAnchorElement>, navigate: (to: string) => void, to: string): void {
  if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  if (!canAnimatePageChange()) return;
  e.preventDefault();
  const root = document.documentElement;
  root.classList.add("vt-nav"); // the page's own fade-in is skipped while the view transition animates it
  const t = (document as DocWithVT).startViewTransition!(() => {
    flushSync(() => navigate(to));
  });
  t.finished.finally(() => root.classList.remove("vt-nav"));
}
