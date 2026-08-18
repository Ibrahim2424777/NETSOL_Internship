"""Tavily web search client (Phase 18) - the retrieval layer for the
web_search route, replacing Groq compound-mini's built-in autonomous search.

Compound-mini did its own search AND generated the final answer in one
model call; it could (and reproducibly did, live - see the removed
_compound_kwargs/_COMPOUND_RETRY_ATTEMPTS in groq_service.py's history)
attempt to retrieve too many/too-large pages for an ordinary query and fail
the whole turn with a 413, with no client-side fix available. Tavily is a
plain search API with no autonomous browsing of its own: it returns a
bounded number of already-fetched result snippets, never full pages, so
there's no equivalent failure mode to reproduce.

This service is retrieval ONLY - it never generates an answer. The existing
ModelService (Gemini primary / Groq fallback, same as normal/RAG - see
app/api/deps.py's get_model_service) is what turns these results into a
grounded reply - see app/langgraph/nodes/web_search_node.py (retrieval) and
web_search_answer_node.py (generation).
"""
import logging
from typing import TypedDict

from tavily import AsyncTavilyClient
from tavily.errors import (
    BadRequestError as TavilyBadRequestError,
    ForbiddenError as TavilyForbiddenError,
    InvalidAPIKeyError as TavilyInvalidAPIKeyError,
    TimeoutError as TavilySDKTimeoutError,
    UsageLimitExceededError as TavilyUsageLimitExceededError,
)

logger = logging.getLogger(__name__)


class TavilySearchResult(TypedDict):
    """One search result, normalized from Tavily's own response shape - only
    the fields this app actually uses (Phase 18 doc section 6: "do not pass
    unnecessary raw Tavily metadata to the model")."""

    title: str
    url: str
    content: str
    score: float


class TavilyError(Exception):
    """Base class for all Tavily-layer failures. Callers (web_search_node.py)
    catch this and degrade gracefully - empty results plus an honest
    "search unavailable" instruction for the model - never a crashed turn.
    Mirrors app/mcp/errors.py's role for the MCP client."""


class TavilyNotConfiguredError(TavilyError):
    """No TAVILY_API_KEY is set. The web_search route still works, just
    without live retrieval - same "degrade, don't crash" pattern as MCP
    tools when Gmail isn't configured."""


class TavilyUnavailableError(TavilyError):
    """A configured Tavily request failed - bad key, rate/usage limit,
    timeout, network error, or a malformed response. Not distinguished
    further downstream: web_search_node.py treats every failure mode
    identically (empty results, model told to say so), since there's no
    second search provider to fall back to the way Gemini/Groq fall back to
    each other."""


class TavilySearchService:
    def __init__(self, *, api_key: str, max_results: int, timeout_seconds: float) -> None:
        self._max_results = max_results
        self._timeout_seconds = timeout_seconds
        # None (not a client with an empty key) when unconfigured, so
        # `configured` is a plain None-check rather than needing to guess
        # what an "empty key" API call would even do.
        self._client = AsyncTavilyClient(api_key=api_key) if api_key else None

    @property
    def configured(self) -> bool:
        return self._client is not None

    async def search(self, query: str) -> list[TavilySearchResult]:
        """Basic-depth search, capped at max_results (Phase 18 doc section 4:
        "do NOT retrieve dozens of pages"). Raises TavilyNotConfiguredError or
        TavilyUnavailableError on any failure - callers are expected to catch
        these and degrade gracefully rather than let a Tavily hiccup fail the
        whole turn."""
        if self._client is None:
            raise TavilyNotConfiguredError("TAVILY_API_KEY is not set")

        try:
            response = await self._client.search(
                query,
                search_depth="basic",
                max_results=self._max_results,
                timeout=self._timeout_seconds,
            )
        except (TavilyInvalidAPIKeyError, TavilyForbiddenError) as exc:
            logger.error("Tavily rejected the configured API key")
            raise TavilyUnavailableError("Tavily authentication failed") from exc
        except TavilyUsageLimitExceededError as exc:
            logger.warning("Tavily usage/rate limit exceeded")
            raise TavilyUnavailableError("Tavily rate limit exceeded") from exc
        except TavilySDKTimeoutError as exc:
            logger.warning("Tavily request timed out")
            raise TavilyUnavailableError("Tavily request timed out") from exc
        except TavilyBadRequestError as exc:
            logger.warning("Tavily rejected the search request: %s", exc)
            raise TavilyUnavailableError("Tavily rejected the search request") from exc
        except Exception as exc:
            # Network errors, malformed responses, and anything else the SDK
            # doesn't give a named exception for - classified as the same
            # generic "search unavailable this turn" signal as the cases
            # above, per the doc's own list of failure modes to handle.
            logger.exception("Tavily search failed")
            raise TavilyUnavailableError("Tavily search failed") from exc

        results = response.get("results") or []
        return [
            {
                "title": result.get("title") or result["url"],
                "url": result["url"],
                "content": result.get("content") or "",
                "score": result.get("score") or 0.0,
            }
            for result in results
            if result.get("url")
        ]
