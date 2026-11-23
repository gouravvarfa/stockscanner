"""python -m backend.eod backfill|update  (data folder: $SCANNER_EOD_DIR or ~/.scanner_eod)"""
import datetime as dt
import logging
import os
import sys
from pathlib import Path

from backend.eod.bhavcopy import BhavcopyCache

ROOT = Path(os.environ.get("SCANNER_EOD_DIR", Path.home() / ".scanner_eod"))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "update"
    cache = BhavcopyCache(ROOT)
    today = dt.date.today()
    if cmd == "backfill":
        years = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        got = cache.fetch_range(today - dt.timedelta(days=int(years * 365.25) + 10), today)
    elif cmd == "daily":
        # the evening job: today's file, then the scan, results into the site's public folder
        got = cache.fetch_range(today - dt.timedelta(days=10), today)
        cache.fetch_index_range(today - dt.timedelta(days=10), today)
        cache.refresh_symbol_changes(ROOT)
        from backend.eod import scan, store
        hist = store.build(ROOT)
        from backend.eod import sectors
        cup, vb = scan.run(hist, sector_info=sectors.classify(ROOT))
        out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("frontend/public/eod")
        scan.write(out, cup, vb)
        print(f"daily: {got} new day files; data to {cup['data_as_of']}; {len(cup['results'])} cups, {len(vb['strategies']['Value Buy'])} value buy -> {out}")
        return
    elif cmd == "scan":
        from backend.eod import scan, store
        hist = store.load(ROOT) if (ROOT / "history.pkl").exists() and "--rebuild" not in sys.argv else store.build(ROOT)
        from backend.eod import sectors
        cup, vb = scan.run(hist, sector_info=sectors.classify(ROOT))
        out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "out"
        scan.write(out, cup, vb)
        print(f"scan: {cup['stocks_scanned']} stocks, {len(cup['results'])} cups, {len(vb['strategies']['Value Buy'])} value buy -> {out}")
        return
    else:
        got = cache.fetch_range(today - dt.timedelta(days=10), today)
    print(f"{cmd}: {got} new day files; {len(cache.days())} days cached in {ROOT}")


if __name__ == "__main__":
    main()
