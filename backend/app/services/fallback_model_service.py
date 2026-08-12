"""Wraps two ModelService implementations - a primary and a fallback - behind
the same ModelService interface (Phase 14.5).

This is the ONE place fallback logic lives. Neither model_node.py nor
router_node.py (the only two callers of ModelService anywhere in the app)
change at all or gain any Gemini/Groq-specific branching - they already
depend only on ModelService, so handing either of them a
FallbackModelService instead of a bare GeminiService is transparent by
construction (see app/api/deps.py's get_model_service).

Fallback only ever triggers on ProviderUnavailableError - the signal a
provider raises for a transient/quota/rate-limit failure specifically (see
model_service.py). Any other exception (a bug, a malformed prompt, a safety
block) propagates from the primary as-is; trying a second provider for a
failure that isn't about provider availability could hide a real bug and
burns fallback-provider quota for nothing.
"""
import logging
from collections.abc import AsyncIterator, Callable

from app.services.model_service import ModelService, ModelTurn, ProviderUnavailableError, SearchCitation

logger = logging.getLogger(__name__)


class FallbackModelService(ModelService):
    def __init__(
        self,
        primary: ModelService,
        fallback: ModelService | None,
        *,
        primary_name: str = "primary",
        fallback_name: str = "fallback",
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._primary_name = primary_name
        self._fallback_name = fallback_name

    async def generate(
        self,
        history: list[ModelTurn],
        *,
        on_search_result: Callable[[SearchCitation], None] | None = None,
    ) -> str:
        try:
            result = await self._primary.generate(history, on_search_result=on_search_result)
            logger.info("LLM provider: %s", self._primary_name)
            return result
        except ProviderUnavailableError:
            if self._fallback is None:
                raise
            logger.warning(
                "%s unavailable - falling back to %s", self._primary_name, self._fallback_name
            )
            # Not passed through to the fallback call: a citation callback
            # is meaningless once we've switched away from the provider that
            # was actually going to use it to report ITS OWN search results.
            result = await self._fallback.generate(history)
            logger.info("LLM provider: %s", self._fallback_name)
            return result

    async def generate_stream(
        self,
        history: list[ModelTurn],
        *,
        on_search_result: Callable[[SearchCitation], None] | None = None,
    ) -> AsyncIterator[str]:
        yielded_any = False
        try:
            async for chunk in self._primary.generate_stream(history, on_search_result=on_search_result):
                yielded_any = True
                yield chunk
            logger.info("LLM provider: %s", self._primary_name)
            return
        except ProviderUnavailableError:
            # Once the primary has already streamed real output to the
            # caller, that output can't be un-sent - switching providers
            # mid-response would mean stitching together two different
            # models' half-answers, which is worse than just failing the
            # turn. Only safe to retry on the fallback provider if NOTHING
            # from the primary has reached the caller yet.
            if yielded_any or self._fallback is None:
                raise
            logger.warning(
                "%s unavailable before any output - falling back to %s",
                self._primary_name,
                self._fallback_name,
            )

        async for chunk in self._fallback.generate_stream(history):
            yield chunk
        logger.info("LLM provider: %s", self._fallback_name)

    async def classify(self, history: list[ModelTurn], *, instructions: str, choices: list[str]) -> str:
        try:
            result = await self._primary.classify(history, instructions=instructions, choices=choices)
            logger.info("LLM provider (classify): %s", self._primary_name)
            return result
        except ProviderUnavailableError:
            if self._fallback is None:
                raise
            logger.warning(
                "%s unavailable for classify() - falling back to %s",
                self._primary_name,
                self._fallback_name,
            )
            result = await self._fallback.classify(history, instructions=instructions, choices=choices)
            logger.info("LLM provider (classify): %s", self._fallback_name)
            return result
