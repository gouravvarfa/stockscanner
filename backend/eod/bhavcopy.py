"""NSE end-of-day data from the daily bhavcopy files (2026-11-23).

One file per trading day holds every NSE stock's open/high/low/close/volume, so a whole-market scan needs ONE download
a day instead of thousands of Angel One calls. Files are public on nsearchives.nseindia.com:
- up to 2024-07-05: content/historical/EQUITIES/YYYY/MON/cmDDMONYYYYbhav.csv.zip  (SYMBOL, SERIES, OPEN, ... PREVCLOSE)
- from 2024-07-08 (UDiFF): content/cm/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip  (TckrSymb, SctySrs, OpnPric, ...)

Raw day files are cached as small CSVs under the data folder; a day that does not exist (holiday/weekend) is
remembered so it is never asked for again. Prices are NOT adjusted for splits/bonuses here - see store.py.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import logging
import time
import zipfile
from pathlib import Path

import httpx

logger = logging.getLogger("scanner.eod")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
BASE = "https://nsearchives.nseindia.com"
UDIFF_FROM = dt.date(2024, 7, 8)
SERIES = {"EQ", "BE", "BZ"}
COLUMNS = ["symbol", "series", "open", "high", "low", "close", "prevclose", "volume"]


def _url(day: dt.date) -> str:
    if day >= UDIFF_FROM:
        return f"{BASE}/content/cm/BhavCopy_NSE_CM_0_0_0_{day:%Y%m%d}_F_0000.csv.zip"
    mon = day.strftime("%b").upper()
    return f"{BASE}/content/historical/EQUITIES/{day:%Y}/{mon}/cm{day:%d}{mon}{day:%Y}bhav.csv.zip"


def _parse(text: str, day: dt.date) -> list[list]:
    rows = []
    reader = csv.DictReader(io.StringIO(text))
    udiff = day >= UDIFF_FROM
    for r in reader:
        r = {k.strip(): (v or "").strip() for k, v in r.items() if k}
        try:
            if udiff:
                sym, ser = r["TckrSymb"], r["SctySrs"]
                vals = [r["OpnPric"], r["HghPric"], r["LwPric"], r["ClsPric"], r["PrvsClsgPric"], r["TtlTradgVol"]]
            else:
                sym, ser = r["SYMBOL"], r["SERIES"]
                vals = [r["OPEN"], r["HIGH"], r["LOW"], r["CLOSE"], r["PREVCLOSE"], r["TOTTRDQTY"]]
            if ser not in SERIES:
                continue
            o, h, l, c, pc, v = (float(x) for x in vals)
        except (KeyError, ValueError):
            continue
        if c <= 0:
            continue
        rows.append([sym, ser, o, h, l, c, pc, int(v)])
    return rows


class BhavcopyCache:
    def __init__(self, root: Path):
        self.raw = root / "raw"
        self.raw.mkdir(parents=True, exist_ok=True)
        self.missing_file = root / "missing_days.txt"
        self.missing = set(self.missing_file.read_text().split()) if self.missing_file.exists() else set()
        self.client = httpx.Client(headers={"User-Agent": UA, "Accept": "*/*"}, timeout=30.0, follow_redirects=True)

    def path(self, day: dt.date) -> Path:
        return self.raw / f"{day:%Y}" / f"{day:%Y%m%d}.csv"

    def have(self, day: dt.date) -> bool:
        return self.path(day).exists() or day.isoformat() in self.missing

    def fetch(self, day: dt.date, pause: float = 0.35) -> bool:
        """Download one day into the cache. True if the day has data (now or before)."""
        if self.path(day).exists():
            return True
        if day.isoformat() in self.missing or day.weekday() >= 5:
            return False
        for attempt in range(3):
            try:
                resp = self.client.get(_url(day))
            except httpx.HTTPError as exc:
                logger.warning("bhavcopy %s: %s", day, exc)
                time.sleep(2 + attempt * 3)
                continue
            time.sleep(pause)
            if resp.status_code == 404:
                # today's file may simply not be out yet - only past days are remembered as missing
                if day < dt.date.today():
                    self.missing.add(day.isoformat())
                    self.missing_file.write_text("\n".join(sorted(self.missing)))
                return False
            if resp.status_code != 200:
                time.sleep(3 + attempt * 5)
                continue
            try:
                z = zipfile.ZipFile(io.BytesIO(resp.content))
                text = z.read(z.namelist()[0]).decode("utf-8", "replace")
            except (zipfile.BadZipFile, IndexError):
                time.sleep(3)
                continue
            rows = _parse(text, day)
            if not rows:
                return False
            out = self.path(day)
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(COLUMNS)
                w.writerows(rows)
            return True
        return False

    def fetch_range(self, start: dt.date, end: dt.date, progress_every: int = 100) -> int:
        got, day, n = 0, start, 0
        while day <= end:
            if not self.have(day) and day.weekday() < 5:
                if self.fetch(day):
                    got += 1
                n += 1
                if n % progress_every == 0:
                    logger.info("bhavcopy: %s (%d new files)", day, got)
            day += dt.timedelta(days=1)
        return got

    def refresh_symbol_changes(self, root: Path) -> None:
        try:
            resp = self.client.get(f"{BASE}/content/equities/symbolchange.csv")
            if resp.status_code == 200 and b"OLD SYMBOL" in resp.content[:300]:
                (root / "symbolchange.csv").write_bytes(resp.content)
        except httpx.HTTPError as exc:
            logger.warning("symbol changes: %s", exc)

    # ---- NSE index closes (2026-11-23): one file a day with every NSE index (sector strength from end-of-day data)
    def index_path(self, day: dt.date) -> Path:
        return self.raw.parent / "raw_idx" / f"{day:%Y}" / f"{day:%Y%m%d}.csv"

    def fetch_index(self, day: dt.date, pause: float = 0.3) -> bool:
        out = self.index_path(day)
        if out.exists():
            return True
        if day.weekday() >= 5 or (day.isoformat() in self.missing):
            return False
        url = f"{BASE}/content/indices/ind_close_all_{day:%d%m%Y}.csv"
        for attempt in range(3):
            try:
                resp = self.client.get(url)
            except httpx.HTTPError:
                time.sleep(2 + attempt * 3)
                continue
            time.sleep(pause)
            if resp.status_code == 404:
                return False
            if resp.status_code != 200 or b"Index Name" not in resp.content[:200]:
                time.sleep(3)
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(resp.content)
            return True
        return False

    def fetch_index_range(self, start: dt.date, end: dt.date) -> int:
        got, day = 0, start
        while day <= end:
            if day.weekday() < 5 and not self.index_path(day).exists() and self.fetch_index(day):
                got += 1
            day += dt.timedelta(days=1)
        return got

    def days(self) -> list[dt.date]:
        return sorted(dt.datetime.strptime(p.stem, "%Y%m%d").date() for p in self.raw.glob("*/*.csv"))
