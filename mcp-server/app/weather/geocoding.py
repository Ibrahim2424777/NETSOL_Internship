"""Resolves a human-readable location string ("Multan, Pakistan", "London, UK")
to coordinates via Open-Meteo's free Geocoding API.

Open-Meteo's forecast API only accepts latitude/longitude, not place names -
this is the one extra step that closes that gap so callers of the weather
tools never have to supply coordinates themselves (Phase 16 doc section 7).
"""
import logging

import httpx
from pydantic import BaseModel

from app.config import get_settings
from app.weather.errors import (
    LocationNotFoundError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitedError,
)

logger = logging.getLogger(__name__)


class ResolvedLocation(BaseModel):
    name: str
    country: str | None
    admin1: str | None  # state/province/region, when the provider has one
    latitude: float
    longitude: float
    timezone: str

    @property
    def display_name(self) -> str:
        parts = [self.name, self.admin1, self.country]
        return ", ".join(p for p in parts if p)


async def _search(name: str) -> list[dict]:
    """One raw call to Open-Meteo's geocoding search. Returns the raw
    `results` list (possibly empty) - callers decide what an empty result
    means (try a fallback query, or give up)."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.WEATHER_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                settings.OPEN_METEO_GEOCODING_URL,
                params={"name": name, "count": 1, "language": "en", "format": "json"},
            )
    except httpx.TimeoutException as exc:
        raise ProviderTimeoutError(f"Geocoding lookup for {name!r} timed out.") from exc
    except httpx.HTTPError as exc:
        logger.exception("Geocoding request failed for %r", name)
        raise ProviderUnavailableError("Could not reach the geocoding service.") from exc

    if response.status_code == 429:
        raise RateLimitedError("The geocoding service is rate-limiting requests. Try again shortly.")
    if response.status_code >= 500:
        raise ProviderUnavailableError(f"Geocoding service returned {response.status_code}.")
    if response.status_code != 200:
        logger.warning("Unexpected geocoding status %s for %r", response.status_code, name)
        raise ProviderUnavailableError(f"Geocoding service returned an unexpected {response.status_code}.")

    try:
        data = response.json()
    except ValueError as exc:
        raise ProviderUnavailableError("Geocoding service returned a malformed response.") from exc

    return data.get("results") or []


async def resolve_location(query: str) -> ResolvedLocation:
    """Looks up the best-matching place for a free-text query. Raises
    LocationNotFoundError if nothing matches - callers must not fabricate
    coordinates for an unresolved location.

    Falls back to just the part before the first comma if the full query
    returns nothing - Open-Meteo's geocoder matches place-name tokens in its
    own database and does NOT recognize country abbreviations like "UK"
    (verified live: "London, UK" returns zero results, "London, United
    Kingdom" and plain "London" both work). Since "City, XY"-style queries
    are exactly the format this tool's own description invites ("Multan,
    Pakistan", "London, UK"), silently failing on the abbreviated form isn't
    acceptable - retrying with just "London" trades a little precision
    (a same-named city elsewhere could theoretically outrank the intended
    one) for actually answering the doc's own example queries.
    """
    query = query.strip()
    if not query:
        raise LocationNotFoundError("No location was provided.")

    results = await _search(query)

    if not results and "," in query:
        fallback = query.split(",", 1)[0].strip()
        if fallback:
            logger.info("Geocoding %r returned nothing - retrying with %r", query, fallback)
            results = await _search(fallback)

    if not results:
        raise LocationNotFoundError(f"No location found matching {query!r}.")

    top = results[0]
    try:
        return ResolvedLocation(
            name=top["name"],
            country=top.get("country"),
            admin1=top.get("admin1"),
            latitude=top["latitude"],
            longitude=top["longitude"],
            timezone=top.get("timezone", "UTC"),
        )
    except KeyError as exc:
        raise ProviderUnavailableError("Geocoding service response was missing expected fields.") from exc
