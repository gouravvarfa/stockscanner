from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./scanner.db"
    cache_url: str = "file://.cache/tapetide_cache.pkl"
    environment: str = "development"
    log_level: str = "INFO"

    tapetide_mcp_url: str = "https://mcp.tapetide.com/mcp"
    tapetide_token_cache_path: str = ".tapetide_token.json"

    # Angel One SmartAPI — intraday (15m/1h) data source for Expiry Level 1 only.
    angelone_api_key: str = ""
    angelone_client_code: str = ""
    angelone_pin: str = ""
    angelone_totp_secret: str = ""

    @property
    def angelone_configured(self) -> bool:
        return bool(self.angelone_api_key and self.angelone_client_code and self.angelone_pin and self.angelone_totp_secret)

    # TradingView webhook — an OPTIONAL, additional signal source (Pine Script
    # alert -> webhook), never a replacement for the existing market-data
    # providers. Safe-by-default: disabled unless explicitly turned on, and
    # the webhook route itself is inert (returns configuration-required)
    # while disabled, regardless of whether a secret is set.
    tradingview_enabled: bool = False
    tradingview_webhook_secret: str = ""


settings = Settings()
