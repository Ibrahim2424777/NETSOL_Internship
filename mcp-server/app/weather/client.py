"""Thin HTTP client over Open-Meteo's free Forecast API.

Only responsible for making the request and handling transport-level
failures (timeout, network error, non-2xx, malformed JSON) - turning the raw
response into the MCP tools' structured result shape is tools.py's job, not
this module's, so this stays a plain "talk to the provider" layer (same
split the main backend's *_service.py modules use for Gemini/Groq/etc.).
"""
import logging

import httpx

from app.config import get_settings
from app.weather.errors import ProviderTimeoutError, ProviderUnavailableError, RateLimitedError

logger = logging.getLogger(__name__)

_CURRENT_FIELDS = (
    "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,"
    "precipitation,weather_code,wind_speed_10m,wind_direction_10m"
)
_DAILY_FIELDS = (
    "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,"
    "precipitation_probability_max,wind_speed_10m_max"
)


async def _get(params: dict) -> dict:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.WEATHER_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(settings.OPEN_METEO_FORECAST_URL, params=params)
    except httpx.TimeoutException as exc:
        raise ProviderTimeoutError("The weather provider took too long to respond.") from exc
    except httpx.HTTPError as exc:
        logger.exception("Open-Meteo request failed")
        raise ProviderUnavailableError("Could not reach the weather provider.") from exc

    if response.status_code == 429:
        raise RateLimitedError("The weather provider is rate-limiting requests. Try again shortly.")
    if response.status_code >= 500:
        raise ProviderUnavailableError(f"Weather provider returned {response.status_code}.")
    if response.status_code != 200:
        logger.warning("Unexpected Open-Meteo status %s: %s", response.status_code, response.text[:300])
        raise ProviderUnavailableError(f"Weather provider returned an unexpected {response.status_code}.")

    try:
        return response.json()
    except ValueError as exc:
        raise ProviderUnavailableError("Weather provider returned a malformed response.") from exc


async def fetch_current(latitude: float, longitude: float) -> dict:
    """Raw current-conditions payload - see _CURRENT_FIELDS for exactly
    which fields are requested. Only fields Open-Meteo actually returns end
    up here; nothing is invented downstream."""
    return await _get(
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": _CURRENT_FIELDS,
            "timezone": "auto",
        }
    )


async def fetch_daily_forecast(latitude: float, longitude: float, forecast_days: int) -> dict:
    """Raw daily-forecast payload covering `forecast_days` days starting
    today (Open-Meteo's own indexing - day 0 is today)."""
    return await _get(
        {
            "latitude": latitude,
            "longitude": longitude,
            "daily": _DAILY_FIELDS,
            "timezone": "auto",
            "forecast_days": forecast_days,
        }
    )
