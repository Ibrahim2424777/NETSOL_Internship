"""HTTP-level tests for app/weather/client.py and app/weather/geocoding.py -
transport failures (timeout, 5xx, 429, malformed JSON) mocked via
pytest-httpx, verifying each is translated into the right WeatherError
subclass rather than leaking a raw httpx/JSON exception.
"""
import httpx
import pytest

from app.weather import client
from app.weather.errors import (
    LocationNotFoundError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitedError,
)
from app.weather.geocoding import resolve_location


@pytest.mark.asyncio
async def test_geocoding_timeout_raises_provider_timeout_error(httpx_mock):
    httpx_mock.add_exception(httpx.TimeoutException("timed out"))

    with pytest.raises(ProviderTimeoutError):
        await resolve_location("Multan, Pakistan")


@pytest.mark.asyncio
async def test_geocoding_network_failure_raises_provider_unavailable(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))

    with pytest.raises(ProviderUnavailableError):
        await resolve_location("Multan, Pakistan")


@pytest.mark.asyncio
async def test_geocoding_rate_limit_raises_rate_limited_error(httpx_mock):
    httpx_mock.add_response(status_code=429, json={"error": "rate limited"})

    with pytest.raises(RateLimitedError):
        await resolve_location("Multan, Pakistan")


@pytest.mark.asyncio
async def test_geocoding_server_error_raises_provider_unavailable(httpx_mock):
    httpx_mock.add_response(status_code=503, json={"error": "unavailable"})

    with pytest.raises(ProviderUnavailableError):
        await resolve_location("Multan, Pakistan")


@pytest.mark.asyncio
async def test_geocoding_malformed_json_raises_provider_unavailable(httpx_mock):
    httpx_mock.add_response(status_code=200, content=b"not json{{{")

    with pytest.raises(ProviderUnavailableError):
        await resolve_location("Multan, Pakistan")


@pytest.mark.asyncio
async def test_geocoding_no_results_raises_location_not_found(httpx_mock):
    httpx_mock.add_response(status_code=200, json={"generationtime_ms": 0.1})

    with pytest.raises(LocationNotFoundError):
        await resolve_location("Zzzxxqqnonexistentplace12345")


@pytest.mark.asyncio
async def test_geocoding_falls_back_to_text_before_comma(httpx_mock):
    """Reproduces the real "London, UK" gap found via live testing:
    Open-Meteo's geocoder doesn't recognize "UK" as a country token, so the
    full-string query returns zero results - resolve_location must retry
    with just "London" rather than failing outright."""
    httpx_mock.add_response(
        url=httpx.URL("https://geocoding-api.open-meteo.com/v1/search", params={
            "name": "London, UK", "count": "1", "language": "en", "format": "json",
        }),
        json={"generationtime_ms": 0.1},  # no "results" key = no match
    )
    httpx_mock.add_response(
        url=httpx.URL("https://geocoding-api.open-meteo.com/v1/search", params={
            "name": "London", "count": "1", "language": "en", "format": "json",
        }),
        json={
            "results": [
                {
                    "name": "London", "country": "United Kingdom", "admin1": "England",
                    "latitude": 51.50853, "longitude": -0.12574, "timezone": "Europe/London",
                }
            ]
        },
    )

    place = await resolve_location("London, UK")

    assert place.name == "London"
    assert place.country == "United Kingdom"


@pytest.mark.asyncio
async def test_forecast_client_timeout_raises_provider_timeout_error(httpx_mock):
    httpx_mock.add_exception(httpx.TimeoutException("timed out"))

    with pytest.raises(ProviderTimeoutError):
        await client.fetch_current(30.19679, 71.47824)


@pytest.mark.asyncio
async def test_forecast_client_server_error_raises_provider_unavailable(httpx_mock):
    httpx_mock.add_response(status_code=500, json={"error": "internal"})

    with pytest.raises(ProviderUnavailableError):
        await client.fetch_daily_forecast(30.19679, 71.47824, 5)
