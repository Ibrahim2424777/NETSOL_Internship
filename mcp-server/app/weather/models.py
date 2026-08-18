"""Structured result shapes for the weather MCP tools (Phase 16 doc section 8).

Returned directly from the @mcp.tool()-decorated functions in tools.py - the
SDK turns a returned Pydantic model into the tool's structured content AND
uses its schema as the tool's declared output schema (visible in MCP
Inspector / to any MCP client introspecting the tool).
"""
from pydantic import BaseModel, Field


class CurrentWeather(BaseModel):
    location: str = Field(description="Resolved, human-readable location name (e.g. 'Multan, Punjab, Pakistan')")
    latitude: float
    longitude: float
    temperature_c: float = Field(description="Current air temperature in Celsius")
    feels_like_c: float = Field(description="Apparent (\"feels like\") temperature in Celsius")
    condition: str = Field(description="Human-readable weather condition, e.g. 'Partly cloudy'")
    humidity_percent: int | None = Field(default=None, description="Relative humidity, 0-100")
    wind_kph: float | None = Field(default=None, description="Wind speed in km/h")
    wind_direction_deg: int | None = Field(default=None, description="Wind direction in degrees (0=N, 90=E, ...)")
    precipitation_mm: float | None = Field(default=None, description="Precipitation in the last hour, in mm")
    is_day: bool | None = Field(default=None, description="Whether it is currently daytime at the location")
    observed_at: str = Field(description="ISO 8601 local timestamp this reading is for")
    timezone: str = Field(description="IANA timezone of the location, e.g. 'Asia/Karachi'")


class DailyForecast(BaseModel):
    location: str = Field(description="Resolved, human-readable location name")
    latitude: float
    longitude: float
    requested_date: str = Field(description="The date this forecast is for, YYYY-MM-DD")
    condition: str = Field(description="Human-readable expected weather condition")
    temp_max_c: float = Field(description="Forecast maximum temperature in Celsius")
    temp_min_c: float = Field(description="Forecast minimum temperature in Celsius")
    precipitation_mm: float | None = Field(default=None, description="Total forecast precipitation in mm")
    precipitation_probability_percent: int | None = Field(
        default=None, description="Maximum forecast chance of precipitation that day, 0-100"
    )
    wind_max_kph: float | None = Field(default=None, description="Forecast maximum wind speed in km/h")
    timezone: str = Field(description="IANA timezone of the location")
