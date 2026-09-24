import pickle

import pandas as pd
import pytest

from backend.providers import cup_disk_cache


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path, monkeypatch):
    """Every test gets its own throwaway cache directory — never touches
    the real .cache/cup_history/ the running app uses."""
    monkeypatch.setattr(cup_disk_cache, "CACHE_DIR", tmp_path / "cup_history")


def _df(rows: int = 5, base: float = 100.0) -> pd.DataFrame:
    idx = pd.bdate_range("2024-01-01", periods=rows)
    closes = [base + i for i in range(rows)]
    return pd.DataFrame(
        {"open": closes, "high": [c + 1 for c in closes], "low": [c - 1 for c in closes],
         "close": closes, "volume": [1000.0] * rows},
        index=idx,
    )


def test_cache_miss_returns_none():
    assert cup_disk_cache.load("NOSUCHSYMBOL") is None


def test_save_then_load_round_trips():
    df = _df()
    cup_disk_cache.save("RELIANCE", df)
    entry = cup_disk_cache.load("RELIANCE")
    assert entry is not None
    assert entry.symbol == "RELIANCE"
    assert entry.rows == len(df)
    assert entry.oldest_date == df.index.min()
    assert entry.newest_date == df.index.max()
    pd.testing.assert_frame_equal(entry.data, df)


def test_one_symbol_file_does_not_contain_another_symbols_history():
    cup_disk_cache.save("AAA", _df(rows=5, base=100.0))
    cup_disk_cache.save("BBB", _df(rows=8, base=500.0))

    a = cup_disk_cache.load("AAA")
    b = cup_disk_cache.load("BBB")
    assert a is not None and b is not None
    assert a.rows == 5 and b.rows == 8
    assert a.data["close"].iloc[0] == 100.0
    assert b.data["close"].iloc[0] == 500.0
    # Each symbol lives in its OWN file — writing BBB must never touch AAA's file.
    a_path = cup_disk_cache._path_for("AAA")
    b_path = cup_disk_cache._path_for("BBB")
    assert a_path != b_path
    a_mtime_before = a_path.stat().st_mtime
    cup_disk_cache.save("BBB", _df(rows=9, base=600.0))
    assert a_path.stat().st_mtime == a_mtime_before  # untouched by BBB's write


def test_corrupt_cache_file_is_safely_ignored_not_a_crash():
    path = cup_disk_cache._path_for("CORRUPT")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"this is not a valid pickle file at all")
    assert cup_disk_cache.load("CORRUPT") is None  # never raises


def test_schema_version_mismatch_is_treated_as_a_miss():
    path = cup_disk_cache._path_for("OLDVERSION")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump({"schema_version": 999, "symbol": "OLDVERSION", "data": _df()}, f)
    assert cup_disk_cache.load("OLDVERSION") is None


def test_malformed_payload_missing_data_key_is_a_miss():
    path = cup_disk_cache._path_for("MALFORMED")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump({"schema_version": cup_disk_cache.SCHEMA_VERSION, "symbol": "MALFORMED"}, f)
    assert cup_disk_cache.load("MALFORMED") is None


def test_empty_dataframe_is_treated_as_a_miss():
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    cup_disk_cache.save("EMPTYSYM", empty)
    assert cup_disk_cache.load("EMPTYSYM") is None


def test_delete_removes_the_symbols_file_only():
    cup_disk_cache.save("KEEPME", _df())
    cup_disk_cache.save("DELETEME", _df())
    cup_disk_cache.delete("DELETEME")
    assert cup_disk_cache.load("DELETEME") is None
    assert cup_disk_cache.load("KEEPME") is not None


def test_no_shared_in_memory_store_exists_in_this_module():
    """Structural guarantee behind 'memory doesn't grow across a scan': this
    module must not define any module-level container that writes/reads
    accumulate into (unlike the shared FileCache's self._store dict)."""
    import inspect

    source = inspect.getsource(cup_disk_cache)
    # No module-level mutable collection declared anywhere in this file.
    assert "_store" not in source
    assert not any(line.strip().startswith(("_CACHE = {", "_CACHE: dict", "CACHE = {")) for line in source.splitlines())


def test_writing_many_symbols_creates_one_file_each_not_one_growing_file(tmp_path):
    symbols = [f"SYM{i}" for i in range(50)]
    for i, sym in enumerate(symbols):
        cup_disk_cache.save(sym, _df(rows=3, base=float(i)))

    files = list(cup_disk_cache.CACHE_DIR.glob("*.pkl"))
    assert len(files) == 50  # one file per symbol, not one shared file
    # Each file is small (a handful of rows) — nowhere near the size a
    # single growing multi-symbol store would reach at 50 entries.
    for f in files:
        assert f.stat().st_size < 5_000
