"""Sector strength from NSE's daily index-close files (2026-11-23).

For each Weekly-Sectors sector the NSE index series gives daily / weekly / monthly RSI(14) (current candle included):
- STRONG: daily, weekly and monthly RSI all above 60 (the Weekly Sectors rule)
- VALUE (the sector itself at the Value Buy support): monthly RSI 38-45
Value Buy keeps only stocks whose sector is STRONG or VALUE (user, 2026-11-23).
Members come from the sector constituents snapshot the Weekly Sectors page uses.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

NSE_INDEX_NAME = {
    "psu_bank": "Nifty PSU Bank", "bank": "Nifty Bank", "fin_service": "Nifty Financial Services", "realty": "Nifty Realty",
    "infra": "Nifty Infrastructure", "pharma": "Nifty Pharma", "media": "Nifty Media", "capital_markets": "Nifty Capital Markets",
    "it": "Nifty IT", "auto": "Nifty Auto", "fmcg": "Nifty FMCG", "metal": "Nifty Metal", "energy": "Nifty Energy",
    "pvt_bank": "Nifty Private Bank", "pse": "Nifty PSE", "cpse": "Nifty CPSE", "healthcare": "Nifty Healthcare Index",
    "oil_gas": "Nifty Oil & Gas", "consumer_durables": "Nifty Consumer Durables", "defence": "Nifty India Defence",
    "chemicals": "Nifty Chemicals",
}
STRONG_RSI = 60.0
VALUE_MIN, VALUE_MAX = 38.0, 45.0
FULL_MONTHS = 36  # a sector index needs 3 full years of daily closes (>= 10 days every month) to be judged
CONSTITUENTS = Path(__file__).resolve().parent.parent / "data" / "sector_constituents.json"
INDUSTRY_FILE = Path(__file__).resolve().parent.parent / "data" / "nse_industry.csv"
# NSE industry -> the sectors whose stocks it adds (2026-11-23, user: every stock of a sector, not only the index members)
INDUSTRY_TO_SECTORS = {
    "Healthcare": ["pharma", "healthcare"], "Information Technology": ["it"], "Automobile and Auto Components": ["auto"],
    "Fast Moving Consumer Goods": ["fmcg"], "Metals & Mining": ["metal"], "Oil Gas & Consumable Fuels": ["oil_gas", "energy"],
    "Power": ["energy"], "Realty": ["realty"], "Media Entertainment & Publication": ["media"], "Chemicals": ["chemicals"],
    "Consumer Durables": ["consumer_durables"], "Construction": ["infra"], "Construction Materials": ["infra"], "Capital Goods": ["infra"],
}
PSU_BANKS = {"SBIN", "PNB", "BANKBARODA", "CANBK", "UNIONBANK", "BANKINDIA", "INDIANB", "IOB", "UCOBANK", "CENTRALBK", "MAHABANK", "PSB"}


def industry_members() -> dict[str, list[str]]:
    """sector key -> symbols, from NSE's industry tags (Nifty Total Market + Microcap 250 lists)."""
    import csv

    out: dict[str, list[str]] = {}
    if not INDUSTRY_FILE.exists():
        return out
    with open(INDUSTRY_FILE, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            sym, name, ind = r["symbol"], r["company"], r["industry"]
            keys = list(INDUSTRY_TO_SECTORS.get(ind, []))
            if ind == "Financial Services":
                keys.append("fin_service")
                if " bank" in f" {name.lower()}" and "finance" not in name.lower():
                    keys += ["bank", "psu_bank" if sym in PSU_BANKS else "pvt_bank"]
            for k in keys:
                out.setdefault(k, []).append(sym)
    return out


def _rsi(closes: pd.Series, length: int = 14) -> float | None:
    closes = closes.dropna()
    if len(closes) < length + 1:
        return None
    d = closes.diff().dropna()
    g = d.clip(lower=0).ewm(alpha=1 / length, adjust=False, min_periods=length).mean().iloc[-1]
    l_ = (-d.clip(upper=0)).ewm(alpha=1 / length, adjust=False, min_periods=length).mean().iloc[-1]
    return 100.0 if l_ == 0 else float(100 - 100 / (1 + g / l_))


def load_index_closes(root: Path) -> dict[str, pd.Series]:
    want = {v.lower(): k for k, v in NSE_INDEX_NAME.items()}
    rows: dict[str, dict] = {k: {} for k in NSE_INDEX_NAME}
    for p in sorted((root / "raw_idx").glob("*/*.csv")):
        try:
            df = pd.read_csv(p, usecols=["Index Name", "Index Date", "Closing Index Value"])
        except (ValueError, pd.errors.EmptyDataError):
            continue
        for name, date, close in df.itertuples(index=False):
            key = want.get(str(name).strip().lower())
            if key is None:
                continue
            try:
                rows[key][pd.to_datetime(date, dayfirst=True)] = float(close)
            except (ValueError, TypeError):
                continue
    return {k: pd.Series(v).sort_index() for k, v in rows.items() if v}


def classify(root: Path) -> dict:
    """{'sectors': [{key,label,rsi:{d,w,m},status}], 'members': {symbol: [{'key','label','status'}]}}"""
    from backend.services.sector_strength_service import SECTORS

    labels = {s["key"]: s["label"] for s in SECTORS}
    closes = load_index_closes(root)
    snap = json.loads(CONSTITUENTS.read_text(encoding="utf-8")).get("sectors", {})
    extra = industry_members()
    sectors, members = [], {}
    for key, ser in closes.items():
        monthly = ser.resample("ME").last()
        recent = monthly.iloc[-FULL_MONTHS:]
        complete = len(recent) == FULL_MONTHS and bool(recent.notna().all()) and ser.resample("ME").count().iloc[-FULL_MONTHS:].min() >= 10
        d = _rsi(ser)
        w = _rsi(ser.resample("W-FRI").last())
        m = _rsi(monthly)
        status = None
        if not complete:
            # 2026-11-23 (Capital Markets): an index missing from many NSE files has gaps - its RSI is not trustworthy,
            # so it is never called strong or at the 40 support
            d = w = m = None
        if None not in (d, w, m) and d > STRONG_RSI and w > STRONG_RSI and m > STRONG_RSI:
            status = "strong"
        elif m is not None and VALUE_MIN <= m <= VALUE_MAX:
            status = "value"
        rsi = {"d": None if d is None else round(d, 1), "w": None if w is None else round(w, 1), "m": None if m is None else round(m, 1)}
        sectors.append({"key": key, "label": labels.get(key, key), "rsi": rsi, "status": status, "as_of": ser.index[-1].date().isoformat()})
        if status:
            syms = {m["symbol"] for m in snap.get(key, [])} | set(extra.get(key, []))
            for sym in syms:
                members.setdefault(sym, []).append({"key": key, "label": labels.get(key, key), "status": status})
    return {"sectors": sectors, "members": members}
