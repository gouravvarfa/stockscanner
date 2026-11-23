/**
 * Known upcoming events for the Outlook calendar (2026-11-23). Official dates only:
 * - RBI MPC: RBI press release of 23 Mar 2026 (FY2026-27 schedule); the decision comes on the last day.
 * - US Fed (FOMC): Federal Reserve calendar, revised 12 Nov 2026 (2027); Dec 2026 is the 2026 schedule (tentative).
 *   The statement is out at 2 pm US Eastern = about 00:30 IST the next day, so India reacts the day after.
 * - Union Budget: 1 February by convention since 2017.
 * - Nifty: weekly expiry every Tuesday; the monthly one on the month's last Tuesday (moved earlier on a holiday).
 * - Results season and holiday dates marked "approx" are not yet officially fixed.
 */
export type OutlookEventKind = "rbi" | "fed" | "budget" | "expiry" | "results" | "holiday" | "astro";
export interface OutlookEvent {
  date: string; // first day (YYYY-MM-DD)
  end?: string; // last day, for a range
  kind: OutlookEventKind;
  title: string;
  note: string;
  approx?: boolean;
}

export const OUTLOOK_EVENTS: OutlookEvent[] = [
  { date: "2026-11-24", kind: "expiry", title: "Nifty monthly expiry (November)", note: "Last Tuesday of the month" },
  { date: "2026-12-02", end: "2026-12-04", kind: "rbi", title: "RBI monetary policy (MPC)", note: "Rate decision on 4 Dec" },
  { date: "2026-12-08", end: "2026-12-09", kind: "fed", title: "US Fed meeting (FOMC)", note: "Decision about 00:30 IST on 10 Dec, so India reacts on 10 Dec · 2026 schedule, tentative", approx: true },
  { date: "2026-12-25", kind: "holiday", title: "Christmas — NSE closed", note: "Market holiday" },
  { date: "2026-12-29", kind: "expiry", title: "Nifty monthly expiry (December)", note: "Last Tuesday of the month" },
  { date: "2027-01-08", end: "2027-02-14", kind: "results", title: "Q3 results season", note: "Big IT and bank results usually start in the second week of January", approx: true },
  { date: "2027-01-10", kind: "astro", title: "Mangal vakri begins (Astro Watch)", note: "Nifty was up in the next 5 trading days 9 of 10 times" },
  { date: "2027-01-25", kind: "expiry", title: "Nifty monthly expiry (January)", note: "26 Jan is Republic Day, so a day earlier", approx: true },
  { date: "2027-01-26", kind: "holiday", title: "Republic Day — NSE closed", note: "Market holiday" },
  { date: "2027-01-26", end: "2027-01-27", kind: "fed", title: "US Fed meeting (FOMC)", note: "Decision about 00:30 IST on 28 Jan, so India reacts on 28 Jan" },
  { date: "2027-02-01", kind: "budget", title: "Union Budget 2027-28", note: "Budget-day record below" },
  { date: "2027-02-03", end: "2027-02-05", kind: "rbi", title: "RBI monetary policy (MPC)", note: "Rate decision on 5 Feb" },
  { date: "2027-02-23", kind: "expiry", title: "Nifty monthly expiry (February)", note: "Last Tuesday of the month" },
];
