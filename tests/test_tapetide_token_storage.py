import json
import time

import pytest
from mcp.shared.auth import OAuthToken

from backend.providers.tapetide_client import EXPIRY_SAFETY_MARGIN_SECONDS, FileTokenStorage


@pytest.fixture
def storage(tmp_path):
    return FileTokenStorage(str(tmp_path / "token.json"))


async def test_set_tokens_persists_an_absolute_expiry(storage):
    await storage.set_tokens(OAuthToken(access_token="abc", expires_in=3600, refresh_token="r1"))

    saved = json.loads(storage._path.read_text())["tokens"]
    assert "expires_at" in saved
    assert saved["expires_at"] == pytest.approx(time.time() + 3600, abs=5)


async def test_live_token_is_returned_with_remaining_lifetime(storage):
    await storage.set_tokens(OAuthToken(access_token="abc", expires_in=3600, refresh_token="r1"))

    token = await storage.get_tokens()
    assert token.access_token == "abc"  # still usable, handed back as-is
    assert 3500 < token.expires_in <= 3600  # counted down, not the original relative value


async def test_expired_token_is_blanked_so_the_client_refreshes_instead_of_reauthorizing(storage):
    # The real bug this guards: OAuthToken carries only a RELATIVE expires_in and
    # the MCP client tracks absolute expiry in memory only, so a token restored
    # from disk used to look "valid forever" — it got sent long after expiry,
    # drew a 401, and forced a full browser re-authorization on every restart.
    await storage.set_tokens(OAuthToken(access_token="abc", expires_in=3600, refresh_token="r1"))
    data = json.loads(storage._path.read_text())
    data["tokens"]["expires_at"] = time.time() - 10  # already lapsed
    storage._path.write_text(json.dumps(data))

    token = await storage.get_tokens()
    assert token.access_token == ""  # falsy -> is_token_valid() is False
    assert token.refresh_token == "r1"  # intact -> can_refresh_token() stays True


async def test_token_inside_the_safety_margin_is_treated_as_expired(storage):
    await storage.set_tokens(OAuthToken(access_token="abc", expires_in=3600, refresh_token="r1"))
    data = json.loads(storage._path.read_text())
    data["tokens"]["expires_at"] = time.time() + (EXPIRY_SAFETY_MARGIN_SECONDS - 5)
    storage._path.write_text(json.dumps(data))

    # Refreshed proactively rather than lapsing mid-request.
    assert (await storage.get_tokens()).access_token == ""


async def test_legacy_token_without_expires_at_is_refreshed_not_trusted(storage):
    # Files written before expires_at existed have an unknowable issue time.
    storage._path.write_text(json.dumps({
        "tokens": {"access_token": "old", "token_type": "Bearer", "expires_in": 3600, "refresh_token": "r1"}
    }))

    token = await storage.get_tokens()
    assert token.access_token == ""
    assert token.refresh_token == "r1"


async def test_expired_token_without_a_refresh_token_is_left_alone(storage):
    # Nothing to refresh with — blanking it would just lose information.
    storage._path.write_text(json.dumps({
        "tokens": {"access_token": "old", "token_type": "Bearer", "expires_in": 3600}
    }))

    assert (await storage.get_tokens()).access_token == "old"


async def test_no_tokens_stored_returns_none(storage):
    assert await storage.get_tokens() is None
