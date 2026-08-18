"""The two weather MCP tools: get_current_weather and get_weather_forecast.

Business logic (date-range validation, picking the right day out of
Open-Meteo's daily arrays, WMO code translation) lives here, on top of the
thin transport layer in client.py/geocoding.py - see those modules for why
they're split out.

Registered onto the MCPServer instance by register_weather_tools() rather
than importing a module-level `mcp` singleton, so this module has no
import-time dependency on server.py (server.py imports and calls this,
not the other way around).
"""
import logging
from datetime import date, timedelta

from app.config import get_settings
from app.weather import client
from app.weather.codes import describe_weather_code
from app.weather.errors import ProviderUnavailableError, UnsupportedForecastDateError
from app.weather.geocoding import resolve_location
from app.weather.models import CurrentWeather, DailyForecast

logger = logging.getLogger(__name__)


async def get_current_weather(location: str) -> CurrentWeather:
    """Resolves `location` via geocoding, then fetches and shapes current
    conditions. Raises a WeatherError subclass on any failure - see
    errors.py; the MCP SDK turns that into a clean isError=True tool result
    automatically (verified against the installed SDK's tool-execution code
    path), so this never needs to hand-build an error payload itself."""
    place = await resolve_location(location)
    data = await client.fetch_current(place.latitude, place.longitude)

    current = data.get("current")
    if not isinstance(current, dict):
        raise ProviderUnavailableError("Weather provider response did not include current conditions.")

    return CurrentWeather(
        location=place.display_name,
        latitude=place.latitude,
        longitude=place.longitude,
        temperature_c=current["temperature_2m"],
        feels_like_c=current["apparent_temperature"],
        condition=describe_weather_code(current.get("weather_code")),
        humidity_percent=current.get("relative_humidity_2m"),
        wind_kph=current.get("wind_speed_10m"),
        wind_direction_deg=current.get("wind_direction_10m"),
        precipitation_mm=current.get("precipitation"),
        is_day=bool(current["is_day"]) if "is_day" in current else None,
        observed_at=current.get("time", ""),
        timezone=data.get("timezone", place.timezone),
    )


async def get_weather_forecast(location: str, date_str: str) -> DailyForecast:
    """Resolves `location`, validates `date_str` (YYYY-MM-DD) is within
    Open-Meteo's free daily-forecast window (today through
    WEATHER_MAX_FORECAST_DAYS-1 days ahead), fetches the daily forecast
    block, and returns the single day that was asked for."""
    settings = get_settings()

    try:
        requested = date.fromisoformat(date_str)
    except ValueError as exc:
        raise UnsupportedForecastDateError(
            f"{date_str!r} is not a valid date - use YYYY-MM-DD format."
        ) from exc

    today = date.today()
    last_supported = today + timedelta(days=settings.WEATHER_MAX_FORECAST_DAYS - 1)
    if requested < today or requested > last_supported:
        raise UnsupportedForecastDateError(
            f"{date_str} is outside the supported forecast range "
            f"({today.isoformat()} through {last_supported.isoformat()}, "
            f"{settings.WEATHER_MAX_FORECAST_DAYS} days including today)."
        )

    place = await resolve_location(location)
    days_needed = (requested - today).days + 1
    data = await client.fetch_daily_forecast(place.latitude, place.longitude, days_needed)

    daily = data.get("daily")
    if not isinstance(daily, dict) or "time" not in daily:
        raise ProviderUnavailableError("Weather provider response did not include a daily forecast.")

    try:
        index = daily["time"].index(date_str)
    except ValueError as exc:
        raise ProviderUnavailableError(
            f"Weather provider's response did not include {date_str}."
        ) from exc

    def _at(field: str):
        values = daily.get(field)
        return values[index] if values is not None and index < len(values) else None

    temp_max = _at("temperature_2m_max")
    temp_min = _at("temperature_2m_min")
    if temp_max is None or temp_min is None:
        raise ProviderUnavailableError("Weather provider's forecast was missing temperature data.")

    return DailyForecast(
        location=place.display_name,
        latitude=place.latitude,
        longitude=place.longitude,
        requested_date=date_str,
        condition=describe_weather_code(_at("weather_code")),
        temp_max_c=temp_max,
        temp_min_c=temp_min,
        precipitation_mm=_at("precipitation_sum"),
        precipitation_probability_percent=_at("precipitation_probability_max"),
        wind_max_kph=_at("wind_speed_10m_max"),
        timezone=data.get("timezone", place.timezone),
    )


def register_weather_tools(mcp) -> None:
    """Registers both weather tools onto an MCPServer instance. Descriptions
    are deliberately detailed (arguments, return fields, limitations) - per
    the Phase 16 doc, an LLM will eventually be the one deciding whether to
    call these, so the description IS the interface it reasons over."""

    mcp.tool(
        name="get_current_weather",
        description=(
            "Get the current weather conditions for a location right now. "
            "Accepts a human-readable place name such as 'Multan', 'Lahore, Pakistan', "
            "or 'London, UK' - coordinates are resolved automatically, do not pass "
            "latitude/longitude. Returns temperature, feels-like temperature, condition, "
            "humidity, wind speed/direction, and recent precipitation, in the units shown "
            "in the result schema (Celsius, km/h, mm, percent). Any field the weather "
            "provider did not return will be omitted (null), never guessed. "
            "Data source: Open-Meteo (no forecast beyond 'now' - use get_weather_forecast "
            "for a future date)."
        ),
    )(get_current_weather)

    mcp.tool(
        name="get_weather_forecast",
        description=(
            "Get the weather forecast for a specific future (or today's) date at a "
            "location. Accepts a human-readable place name (e.g. 'Multan, Pakistan') and "
            "a date in YYYY-MM-DD format. Only supports dates from today through "
            f"{get_settings().WEATHER_MAX_FORECAST_DAYS - 1} days ahead (Open-Meteo's free-tier "
            "daily forecast window) - requesting a date outside that range returns a clear "
            "error explaining the supported range, rather than fabricated data. Returns the "
            "day's expected condition, max/min temperature, precipitation total and "
            "probability, and max wind speed."
        ),
    )(get_weather_forecast)
