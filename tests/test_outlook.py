import math

from backend.services.outlook_service import _ranges, trend_of, vix_band


def test_vix_range_is_close_times_vix_times_sqrt_time():
    r = _ranges(25000.0, 16.0)
    week = 25000 * 0.16 * math.sqrt(5 / 252)
    assert abs(r["week"]["move_1s"] - week) < 0.01
    assert abs(r["week"]["high_2s"] - (25000 + 2 * week)) < 0.02
    assert r["month"]["move_1s"] > r["week"]["move_1s"]


def test_weather_labels():
    assert trend_of(110, 100, 90).startswith("uptrend")
    assert trend_of(80, 100, 90).startswith("downtrend")
    assert trend_of(95, 100, 90).startswith("mixed")
    assert vix_band(12) == "calm (<14)" and vix_band(26) == "fearful (24+)"
