"""Configuration for the standalone MCP server.

Mirrors the main backend's pydantic-settings pattern (backend/app/config/settings.py)
for consistency, even though this is a fully separate project with its own
dependencies/.env - see the repo root README for why they're separate.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Server ---
    MCP_SERVER_NAME: str = "Personal AI Tools"
    MCP_HOST: str = "127.0.0.1"
    MCP_PORT: int = 8100
    # Streamable HTTP is served at http://{MCP_HOST}:{MCP_PORT}{MCP_STREAMABLE_HTTP_PATH}
    MCP_STREAMABLE_HTTP_PATH: str = "/mcp"
    LOG_LEVEL: str = "INFO"

    # --- Weather (Open-Meteo) ---
    # Open-Meteo's forecast and geocoding APIs are free for non-commercial use
    # and require NO API key at all - see README.md's "Weather API" section
    # for why this was chosen over WeatherAPI.com (3-day free forecast cap)
    # and OpenWeatherMap (free tier's location-by-name lookup is deprecated,
    # forecast is 5 days in coarse 3-hour buckets, not per-day). There is
    # deliberately no WEATHER_API_KEY setting here - documenting that
    # absence explicitly, per the Phase 16 doc's "if the selected provider
    # does not require a key, document that clearly" instruction, rather
    # than leaving an unused/confusing env var in .env.example.
    OPEN_METEO_GEOCODING_URL: str = "https://geocoding-api.open-meteo.com/v1/search"
    OPEN_METEO_FORECAST_URL: str = "https://api.open-meteo.com/v1/forecast"
    WEATHER_REQUEST_TIMEOUT_SECONDS: float = 10.0
    # Open-Meteo's free daily forecast covers today + up to 15 days ahead
    # (forecast_days=16 total, verified live against the API on 2026-08-17) -
    # used to validate a requested forecast date before ever calling the API,
    # so an out-of-range date fails fast with a clear message instead of a
    # confusing empty/malformed response.
    WEATHER_MAX_FORECAST_DAYS: int = 16

    # --- Email (Gmail API, Phase 17) ---
    # OAuth 2.0, NOT a password - see scripts/gmail_authorize.py for the
    # one-time interactive setup that produces GMAIL_REFRESH_TOKEN. This is
    # a SEPARATE OAuth authorization from the main chatbot's Google login
    # (backend/.env's GOOGLE_CLIENT_ID) - deliberately so, per the Phase 17
    # doc section 10: "do NOT assume [app login] automatically grants
    # permission to read/send email... keep application login authentication
    # separate from email-provider authorization." Empty defaults so the
    # server still starts without email configured - email tools simply
    # aren't registered in that case (see server.py).
    GMAIL_CLIENT_ID: str = ""
    GMAIL_CLIENT_SECRET: str = ""
    GMAIL_REFRESH_TOKEN: str = ""
    # The Gmail account these credentials were authorized for - also the
    # resolution target for send_email(to="me"), since this server is
    # single-user ("Personal AI Tools", not multi-tenant).
    GMAIL_USER_EMAIL: str = ""
    EMAIL_REQUEST_TIMEOUT_SECONDS: float = 10.0
    # Hard server-side cap on list_recent_emails' limit, regardless of what
    # the model requests - Phase 17 doc section 13: "do not dump an entire
    # inbox... use pagination/limits."
    EMAIL_LIST_MAX_RESULTS: int = 25
    # Gmail body content kept in a read_email result - long emails are
    # truncated rather than handed to the model in full (doc section 14:
    # "only retrieve the minimum content required").
    EMAIL_BODY_MAX_CHARS: int = 4000

    @property
    def email_configured(self) -> bool:
        return bool(self.GMAIL_CLIENT_ID and self.GMAIL_CLIENT_SECRET and self.GMAIL_REFRESH_TOKEN and self.GMAIL_USER_EMAIL)


@lru_cache
def get_settings() -> Settings:
    return Settings()
