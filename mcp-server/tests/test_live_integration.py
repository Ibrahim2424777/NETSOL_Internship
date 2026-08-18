"""Live network tests against the real Open-Meteo API - the doc's own
example calls (Phase 16 doc section 13), run for real rather than mocked,
so at least one test in the suite proves actual weather data comes back
correctly end-to-end. Skippable via `-m "not live"` if network access isn't
available (e.g. a restricted CI runner); not skipped by default since
Open-Meteo needs no API key/account, so there's no secret to be missing.
"""
from datetime import date, timedelta

import pytest

from app.weather.tools import get_current_weather, get_weather_forecast

pytestmark = pytest.mark.live


@pytest.mark.asyncio
async def test_live_current_weather_multan():
    result = await get_current_weather("Multan, Pakistan")

    assert "Multan" in result.location
    assert isinstance(result.temperature_c, float)
    assert -50 < result.temperature_c < 60  # sanity bounds, not a fabricated exact value
    assert result.condition
    assert result.timezone == "Asia/Karachi"


@pytest.mark.asyncio
async def test_live_current_weather_london():
    result = await get_current_weather("London, UK")

    assert "London" in result.location
    assert isinstance(result.temperature_c, float)
    assert result.condition
    assert result.timezone == "Europe/London"


@pytest.mark.asyncio
async def test_live_forecast_supported_future_date():
    target = (date.today() + timedelta(days=3)).isoformat()

    result = await get_weather_forecast("Multan, Pakistan", target)

    assert "Multan" in result.location
    assert result.requested_date == target
    assert result.temp_max_c >= result.temp_min_c
    assert result.condition
