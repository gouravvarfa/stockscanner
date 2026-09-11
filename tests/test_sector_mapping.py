from backend.config.sector_mapping import resolve_sector_index


def test_known_sector_resolves_to_index():
    assert resolve_sector_index("Banks") == "Nifty Bank"
    assert resolve_sector_index("Information Technology") == "Nifty IT"


def test_unmapped_sector_returns_none_not_a_guess():
    # Note: "Aerospace & Defense" is a speculative mapping (see
    # sector_mapping.py's comment) pending verification, so it's excluded here.
    assert resolve_sector_index("Food Products") is None
    assert resolve_sector_index("Textiles") is None


def test_unknown_sector_returns_none():
    assert resolve_sector_index("Not A Real Sector") is None
