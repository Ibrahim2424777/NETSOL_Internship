"""Unit tests for app/weather/tools.py's business logic (date validation,
field mapping, error propagation) - resolve_location/client calls are faked
via monkeypatch so these run fast and deterministically, with no network.

See tests/test_client_errors.py for HTTP-level error-translation tests, and
tests/test_live_integration.py for real-network smoke tests against the
actual Open-Meteo API (the doc's own example calls).
"""
from datetime import date, timedelta

import pytest

from app.weather import tools
from app.weather.errors import LocationNotFoundError, ProviderUnavailableError, UnsupportedForecastDateError
from app.weather.geocoding import ResolvedLocation

MULTAN = ResolvedLocation(
    name="Multan", country="Pakistan", admin1="Punjab",
    latitude=30.19679, longitude=71.47824, timezone="Asia/Karachi",
)

FAKE_CURRENT_RESPONSE = {
    "timezone": "Asia/Karachi",
    "current": {
        "time": "2026-08-17T10:30",
        "temperature_2m": 34.5,
        "relative_humidity_2m": 51,
        "apparent_temperature": 38.7,
        "is_day": 1,
        "precipitation": 0.0,
        "weather_code": 0,
        "wind_speed_10m": 14.7,
        "wind_direction_10m": 192,
    },
}


def _fake_daily_response(dates: list[str]) -> dict:
    n = len(dates)
    return {
        "timezone": "Asia/Karachi",
        "daily": {
            "time": dates,
            "weather_code": [0] * n,
            "temperature_2m_max": [38.9] * n,
            "temperature_2m_min": [30.6] * n,
            "precipitation_sum": [0.0] * n,
            "precipitation_probability_max": [14] * n,
            "wind_speed_10m_max": [13.2] * n,
        },
    }


@pytest.mark.asyncio
async def test_get_current_weather_valid_result(monkeypatch):
    async def fake_resolve(query: str):
        assert query == "Multan, Pakistan"
        return MULTAN

    async def fake_fetch_current(lat, lon):
        assert (lat, lon) == (MULTAN.latitude, MULTAN.longitude)
        return FAKE_CURRENT_RESPONSE

    monkeypatch.setattr(tools, "resolve_location", fake_resolve)
    monkeypatch.setattr(tools.client, "fetch_current", fake_fetch_current)

    result = await tools.get_current_weather("Multan, Pakistan")

    assert result.location == "Multan, Punjab, Pakistan"
    assert result.temperature_c == 34.5
    assert result.feels_like_c == 38.7
    assert result.condition == "Clear sky"
    assert result.humidity_percent == 51
    assert result.wind_kph == 14.7
    assert result.wind_direction_deg == 192
    assert result.is_day is True
    assert result.timezone == "Asia/Karachi"


@pytest.mark.asyncio
async def test_get_current_weather_another_location(monkeypatch):
    london = ResolvedLocation(
        name="London", country="United Kingdom", admin1="England",
        latitude=51.50853, longitude=-0.12574, timezone="Europe/London",
    )

    async def fake_resolve(query: str):
        return london

    async def fake_fetch_current(lat, lon):
        return {
            "timezone": "Europe/London",
            "current": {
                "time": "2026-08-17T11:30",
                "temperature_2m": 19.2,
                "relative_humidity_2m": 70,
                "apparent_temperature": 18.5,
                "is_day": 1,
                "precipitation": 0.2,
                "weather_code": 61,
                "wind_speed_10m": 10.1,
                "wind_direction_10m": 240,
            },
        }

    monkeypatch.setattr(tools, "resolve_location", fake_resolve)
    monkeypatch.setattr(tools.client, "fetch_current", fake_fetch_current)

    result = await tools.get_current_weather("London, UK")

    assert result.location == "London, England, United Kingdom"
    assert result.condition == "Slight rain"
    assert result.precipitation_mm == 0.2


@pytest.mark.asyncio
async def test_get_weather_forecast_valid_date(monkeypatch):
    target = (date.today() + timedelta(days=3)).isoformat()

    async def fake_resolve(query: str):
        return MULTAN

    async def fake_fetch_daily(lat, lon, forecast_days):
        assert forecast_days == 4  # today + 3 days ahead, inclusive
        return _fake_daily_response(
            [(date.today() + timedelta(days=i)).isoformat() for i in range(forecast_days)]
        )

    monkeypatch.setattr(tools, "resolve_location", fake_resolve)
    monkeypatch.setattr(tools.client, "fetch_daily_forecast", fake_fetch_daily)

    result = await tools.get_weather_forecast("Multan, Pakistan", target)

    assert result.location == "Multan, Punjab, Pakistan"
    assert result.requested_date == target
    assert result.condition == "Clear sky"
    assert result.temp_max_c == 38.9
    assert result.temp_min_c == 30.6
    assert result.precipitation_probability_percent == 14


@pytest.mark.asyncio
async def test_invalid_location_raises_clean_error(monkeypatch):
    async def fake_resolve(query: str):
        raise LocationNotFoundError(f"No location found matching {query!r}.")

    monkeypatch.setattr(tools, "resolve_location", fake_resolve)

    with pytest.raises(LocationNotFoundError, match="No location found"):
        await tools.get_current_weather("Zzzxxqqnonexistentplace12345")


@pytest.mark.asyncio
async def test_unsupported_future_date_raises_clean_error():
    # Deliberately outside the ~16-day window - no monkeypatching needed,
    # since date validation happens before any network call.
    too_far = (date.today() + timedelta(days=100)).isoformat()

    with pytest.raises(UnsupportedForecastDateError, match="outside the supported forecast range"):
        await tools.get_weather_forecast("Multan, Pakistan", too_far)


@pytest.mark.asyncio
async def test_past_date_raises_clean_error():
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    with pytest.raises(UnsupportedForecastDateError):
        await tools.get_weather_forecast("Multan, Pakistan", yesterday)


@pytest.mark.asyncio
async def test_malformed_date_raises_clean_error():
    with pytest.raises(UnsupportedForecastDateError, match="not a valid date"):
        await tools.get_weather_forecast("Multan, Pakistan", "not-a-date")


@pytest.mark.asyncio
async def test_provider_failure_propagates_as_weather_error(monkeypatch):
    """Mocks the provider itself failing (not just a transport error) -
    e.g. a malformed/incomplete response missing the fields the tool needs -
    and verifies it's turned into a clean WeatherError, not an unhandled
    KeyError/TypeError leaking out of the tool."""
    async def fake_resolve(query: str):
        return MULTAN

    async def fake_fetch_current(lat, lon):
        return {"timezone": "Asia/Karachi"}  # missing "current" entirely

    monkeypatch.setattr(tools, "resolve_location", fake_resolve)
    monkeypatch.setattr(tools.client, "fetch_current", fake_fetch_current)

    with pytest.raises(ProviderUnavailableError):
        await tools.get_current_weather("Multan, Pakistan")
