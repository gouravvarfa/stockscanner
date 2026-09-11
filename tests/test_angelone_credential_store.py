from backend.services import angelone_credential_store as store


def test_no_file_and_no_env_settings_means_unconfigured(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "CREDENTIAL_PATH", tmp_path / "angelone_credentials.json")
    monkeypatch.setattr(store.settings, "angelone_api_key", "")
    monkeypatch.setattr(store.settings, "angelone_client_code", "")
    monkeypatch.setattr(store.settings, "angelone_pin", "")
    monkeypatch.setattr(store.settings, "angelone_totp_secret", "")

    assert store.get_credentials() is None
    assert not store.is_configured()


def test_save_then_get_round_trips(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "CREDENTIAL_PATH", tmp_path / "angelone_credentials.json")

    creds = store.AngelOneCredentials(api_key="k", client_code="C123", pin="1234", totp_secret="SECRET")
    store.save_credentials(creds)

    loaded = store.get_credentials()
    assert loaded is not None
    assert loaded.client_code == "C123"
    assert store.is_configured()


def test_clear_removes_saved_credentials(monkeypatch, tmp_path):
    path = tmp_path / "angelone_credentials.json"
    monkeypatch.setattr(store, "CREDENTIAL_PATH", path)
    monkeypatch.setattr(store.settings, "angelone_api_key", "")
    monkeypatch.setattr(store.settings, "angelone_client_code", "")
    monkeypatch.setattr(store.settings, "angelone_pin", "")
    monkeypatch.setattr(store.settings, "angelone_totp_secret", "")

    store.save_credentials(store.AngelOneCredentials(api_key="k", client_code="C123", pin="1234", totp_secret="S"))
    assert store.is_configured()

    store.clear_credentials()
    assert not path.exists()
    assert store.get_credentials() is None
