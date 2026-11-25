"""Ratio charts data (2026-11-25, user: Gold/Nifty style ratio charts from our own end-of-day data).

ratios.json        - the ready-made pairs: weekly closes of each leg (the site works out ratio, zones and backtest itself)
ratio_closes.json  - monthly closes of every active NSE stock / ETF, for any "build your own" A / B ratio:
                     {SYM: [year*12 + month-1 of the first month, close, close, ...]}
Rows are [unix seconds, close]; all prices are split/bonus adjusted (store.py).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

# key, label, A, B, what a HIGH ratio means
PRESETS = [
    ("gold_nifty", "Gold / Nifty", "GOLDBEES", "NIFTYBEES", "Gold", "Nifty"),
    ("bank_nifty", "Bank Nifty / Nifty", "BANKBEES", "NIFTYBEES", "Bank Nifty", "Nifty"),
    ("psubank_nifty", "PSU Bank / Nifty", "PSUBNKBEES", "NIFTYBEES", "PSU Bank", "Nifty"),
    ("next50_nifty", "Nifty Next 50 / Nifty", "JUNIORBEES", "NIFTYBEES", "Next 50", "Nifty"),
    ("midcap_nifty", "Midcap 100 / Nifty", "MOM100", "NIFTYBEES", "Midcap 100", "Nifty"),
    ("infra_nifty", "Infra / Nifty", "INFRABEES", "NIFTYBEES", "Infra", "Nifty"),
    ("cpse_nifty", "CPSE / Nifty", "CPSEETF", "NIFTYBEES", "CPSE", "Nifty"),
    ("consumption_nifty", "Consumption / Nifty", "CONSUMBEES", "NIFTYBEES", "Consumption", "Nifty"),
    ("nasdaq_nifty", "Nasdaq 100 / Nifty", "MON100", "NIFTYBEES", "Nasdaq 100", "Nifty"),
    ("it_nifty", "IT / Nifty", "ITBEES", "NIFTYBEES", "IT", "Nifty"),
    ("pharma_nifty", "Pharma / Nifty", "PHARMABEES", "NIFTYBEES", "Pharma", "Nifty"),
    ("silver_gold", "Silver / Gold", "SILVERBEES", "GOLDBEES", "Silver", "Gold"),
]


def _rows(s: pd.Series) -> list:
    return [[int(ts.timestamp()), float(f"{v:.6g}")] for ts, v in s.items() if pd.notna(v) and v > 0]


def write(out_dir: Path, store: dict[str, pd.DataFrame]) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    last = max(df.index[-1] for df in store.values() if len(df))
    presets = []
    for key, label, a, b, an, bn in PRESETS:
        if a not in store or b not in store:
            continue
        wa = store[a]["close"].astype(float).resample("W-FRI").last().dropna()
        wb = store[b]["close"].astype(float).resample("W-FRI").last().dropna()
        presets.append({"key": key, "label": label, "a": a, "b": b, "a_name": an, "b_name": bn, "a_rows": _rows(wa), "b_rows": _rows(wb)})
    (out_dir / "ratios.json").write_text(json.dumps({"data_as_of": last.date().isoformat(), "presets": presets}, separators=(",", ":")), encoding="utf-8")

    # every symbol still trading (a row in the last 30 days) with 2+ years of history
    cutoff = last - pd.Timedelta(days=30)
    closes = {}
    for sym, df in store.items():
        if len(df) < 500 or df.index[-1] < cutoff:
            continue
        m = df["close"].astype(float).resample("MS").last().ffill().dropna()
        # [first month as year*12 + month-1, close, close, ...] - one value per calendar month, no dates repeated
        closes[sym] = [m.index[0].year * 12 + m.index[0].month - 1] + [float(f"{v:.5g}") for v in m]
    (out_dir / "ratio_closes.json").write_text(json.dumps({"data_as_of": last.date().isoformat(), "symbols": closes}, separators=(",", ":")), encoding="utf-8")
    return len(presets)
