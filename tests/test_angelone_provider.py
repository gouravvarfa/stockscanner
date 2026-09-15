import datetime as dt

import pytest

import backend.providers.angelone_provider as angelone_provider_module
from backend.providers.angelone_client import AngelOneApiError, AngelOneSession
from backend.providers.angelone_provider import AngelOneProvider
from backend.services import angelone_credential_store


@pytest.fixture(autouse=True)
def fake_credentials(monkeypatch):
    monkeypatch.setattr(
        angelone_credential_store,
        "get_credentials",
        lambda: angelone_credential_store.AngelOneCredentials(
            api_key="k", client_code="C1", pin="1234", totp_secret="SECRET"
        ),
    )


def _session(tag: str) -> AngelOneSession:
    return AngelOneSession(api_key="k", jwt_token=f"jwt-{tag}", feed_token="f", refresh_token="r", client_code="C1")


_PAST_DATE = (dt.datetime.now() - dt.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S") + "+05:30"
_SAMPLE_ROW = [_PAST_DATE, 1.0, 2.0, 0.5, 1.5, 100]


async def test_get_intraday_ohlc_succeeds_on_first_try_without_relogin(monkeypatch):
    login_calls = {"count": 0}
    candle_calls = {"count": 0}

    async def fake_login(*a, **kw):
        login_calls["count"] += 1
        return _session("initial")

    async def fake_get_candle_data(session, **kw):
        candle_calls["count"] += 1
        return [_SAMPLE_ROW]

    monkeypatch.setattr(angelone_provider_module, "login", fake_login)
    monkeypatch.setattr(angelone_provider_module, "get_candle_data", fake_get_candle_data)

    provider = AngelOneProvider()
    df = await provider.get_intraday_ohlc("NSE", "3045", "ONE_DAY", days_back=5)

    assert not df.empty
    assert login_calls["count"] == 1
    assert candle_calls["count"] == 1


async def test_invalidated_session_triggers_one_relogin_and_recovers(monkeypatch):
    """
    Real bug this guards against: Angel One invalidates the cached session
    when a second login happens elsewhere (app/web) — every subsequent call
    with the stale session used to fail identically forever, until the
    backend process was manually restarted. Now it must self-heal: detect
    the failure, force exactly one fresh re-login, and retry once.
    """
    login_calls = {"count": 0}
    candle_attempts: list[str] = []

    async def fake_login(*a, **kw):
        login_calls["count"] += 1
        return _session(f"login-{login_calls['count']}")

    async def fake_get_candle_data(session, **kw):
        candle_attempts.append(session.jwt_token)
        if session.jwt_token == "jwt-login-1":
            # The stale/invalidated first session always fails.
            raise AngelOneApiError("Angel One returned a non-JSON response (HTTP 403).", "data", retryable=True)
        return [_SAMPLE_ROW]

    monkeypatch.setattr(angelone_provider_module, "login", fake_login)
    monkeypatch.setattr(angelone_provider_module, "get_candle_data", fake_get_candle_data)

    provider = AngelOneProvider()
    df = await provider.get_intraday_ohlc("NSE", "3045", "ONE_DAY", days_back=5)

    assert not df.empty
    assert login_calls["count"] == 2  # initial login + exactly one forced re-login
    assert candle_attempts == ["jwt-login-1", "jwt-login-2"]


async def test_failure_after_relogin_still_surfaces_the_real_error(monkeypatch):
    # If credentials are genuinely bad (not just a stale session), the
    # second attempt fails too and the real error must propagate, not be
    # silently swallowed.
    async def fake_login(*a, **kw):
        return _session("dead")

    async def fake_get_candle_data(session, **kw):
        raise AngelOneApiError("Invalid credentials", "auth", retryable=False)

    monkeypatch.setattr(angelone_provider_module, "login", fake_login)
    monkeypatch.setattr(angelone_provider_module, "get_candle_data", fake_get_candle_data)

    provider = AngelOneProvider()
    with pytest.raises(AngelOneApiError, match="Invalid credentials"):
        await provider.get_intraday_ohlc("NSE", "3045", "ONE_DAY", days_back=5)


async def test_relogin_reuses_ensure_session_and_persists_new_session(monkeypatch):
    # After a successful recovery, the NEW session must be the one cached
    # for subsequent calls (not silently reverted to the dead one).
    login_calls = {"count": 0}

    async def fake_login(*a, **kw):
        login_calls["count"] += 1
        return _session(f"login-{login_calls['count']}")

    call_log: list[str] = []

    async def fake_get_candle_data(session, **kw):
        call_log.append(session.jwt_token)
        if session.jwt_token == "jwt-login-1":
            raise AngelOneApiError("stale session", "data", retryable=True)
        return [_SAMPLE_ROW]

    monkeypatch.setattr(angelone_provider_module, "login", fake_login)
    monkeypatch.setattr(angelone_provider_module, "get_candle_data", fake_get_candle_data)

    provider = AngelOneProvider()
    await provider.get_intraday_ohlc("NSE", "3045", "ONE_DAY", days_back=5)
    assert provider._session.jwt_token == "jwt-login-2"

    # A second, unrelated call must reuse the now-healthy cached session —
    # no further login should happen.
    await provider.get_intraday_ohlc("NSE", "9999", "ONE_DAY", days_back=5)
    assert login_calls["count"] == 2
