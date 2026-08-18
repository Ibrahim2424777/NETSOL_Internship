"""Weather tool error types.

Every one of these is caught at the tool boundary (see tools.py) and turned
into a clean, structured error dict - never a raw exception/stack trace
surfaced to the MCP client (Phase 16 doc section 9). Each subclass exists so
the tool layer can report a specific, useful `error_type` string rather than
one generic "something went wrong".
"""


class WeatherError(Exception):
    """Base class for all weather-tool failures. `error_type` is a short,
    stable machine-readable tag included in the structured error result -
    stable across message wording changes, so a caller (eventually an LLM
    deciding whether to retry/rephrase) can branch on it."""

    error_type = "weather_error"


class LocationNotFoundError(WeatherError):
    error_type = "location_not_found"


class UnsupportedForecastDateError(WeatherError):
    error_type = "unsupported_forecast_date"


class ProviderTimeoutError(WeatherError):
    error_type = "provider_timeout"


class ProviderUnavailableError(WeatherError):
    """Network failure, non-2xx response, or a malformed/unexpected response
    body from Open-Meteo - all treated the same way at the tool layer (the
    provider couldn't be reached or didn't answer usefully), while still
    being logged with the real underlying detail server-side."""

    error_type = "provider_unavailable"


class RateLimitedError(WeatherError):
    error_type = "rate_limited"
