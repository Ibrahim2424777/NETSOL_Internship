"""Gemini implementation of ModelService, using Google's google-genai SDK.

Nothing outside this file (and the settings it reads) knows this app talks to
Gemini specifically - the rest of the AI layer only ever sees the ModelService
interface.
"""
import json
import logging
from collections.abc import AsyncIterator

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.services.model_service import ModelService, ModelTurn, ProviderUnavailableError

logger = logging.getLogger(__name__)


class GeminiServiceError(Exception):
    """A Gemini call failed. Callers should turn this into a clean,
    generic-to-the-client error - never surface the raw provider exception."""


# Gemini/google-genai's own status strings for the specific conditions
# Phase 14.5 wants to treat as "try another provider" - rate limit, quota
# exhaustion, and transient overload/unavailability. Anything else (a bad
# request, a safety block, an auth error) stays a plain GeminiServiceError,
# so a fallback is never attempted for a failure Groq would hit too.
_RETRYABLE_CODES = {429, 503}
_RETRYABLE_STATUSES = {"RESOURCE_EXHAUSTED", "UNAVAILABLE"}


def _raise_classified(exc: Exception, message: str) -> None:
    """Turns a caught exception into either ProviderUnavailableError (safe to
    fall back to another provider) or GeminiServiceError (anything else),
    always chaining the original exception via `from exc` so it's still
    visible in logs/tracebacks."""
    if isinstance(exc, genai_errors.APIError) and (
        exc.code in _RETRYABLE_CODES or exc.status in _RETRYABLE_STATUSES
    ):
        logger.warning("Gemini reported a retryable failure (code=%s, status=%s)", exc.code, exc.status)
        raise ProviderUnavailableError(message) from exc
    raise GeminiServiceError(message) from exc


def _to_contents(history: list[ModelTurn]) -> list[types.Content]:
    """Gemini uses "model" (not "assistant") for its own turns - ModelTurn's
    role values already match, so this is a direct field mapping."""
    return [
        types.Content(role=turn["role"], parts=[types.Part(text=turn["content"])])
        for turn in history
    ]


class GeminiService(ModelService):
    def __init__(self, *, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def generate(self, history: list[ModelTurn], *, on_search_result=None) -> str:
        # Gemini has no built-in search/tool-use in this integration -
        # on_search_result is accepted for interface conformance but never
        # called.
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=_to_contents(history),
            )
        except Exception as exc:
            logger.exception("Gemini generate_content call failed")
            _raise_classified(exc, "Failed to get a response from Gemini")

        if not response.text:
            logger.warning("Gemini returned no text (possibly blocked by safety filters)")
            raise GeminiServiceError("Gemini returned an empty response")

        return response.text

    async def generate_stream(self, history: list[ModelTurn], *, on_search_result=None) -> AsyncIterator[str]:
        try:
            # generate_content_stream returns a coroutine that resolves to
            # the actual async iterator - it must be awaited before iterating.
            stream = await self._client.aio.models.generate_content_stream(
                model=self._model,
                contents=_to_contents(history),
            )
        except Exception as exc:
            logger.exception("Gemini generate_content_stream call failed to start")
            _raise_classified(exc, "Failed to start a response from Gemini")

        try:
            async for chunk in stream:
                if chunk.text:
                    yield chunk.text
        except Exception as exc:
            # Classified the same way as a pre-stream failure (may raise
            # ProviderUnavailableError) - but whether it's actually SAFE to
            # fall back to another provider from here depends on whether
            # this generator already yielded output, which only the caller
            # (FallbackModelService) knows. This method's job is only to
            # classify the failure, not to decide what to do about it.
            logger.exception("Gemini streaming failed mid-response")
            _raise_classified(exc, "Gemini's response was interrupted")

    async def classify(self, history: list[ModelTurn], *, instructions: str, choices: list[str]) -> str:
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=_to_contents(history),
                config=types.GenerateContentConfig(
                    system_instruction=instructions,
                    response_mime_type="application/json",
                    response_schema={
                        "type": "OBJECT",
                        "properties": {"choice": {"type": "STRING", "enum": choices}},
                        "required": ["choice"],
                    },
                ),
            )
        except Exception as exc:
            logger.exception("Gemini classify() call failed")
            _raise_classified(exc, "Failed to classify with Gemini")

        if not response.text:
            logger.warning("Gemini classify() returned no text")
            raise GeminiServiceError("Gemini returned an empty classification")

        try:
            parsed = json.loads(response.text)
            choice = parsed["choice"]
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("Gemini classify() returned unparseable JSON: %r", response.text)
            raise GeminiServiceError("Gemini returned a malformed classification") from exc

        if choice not in choices:
            # response_schema's enum constrains generation, but isn't a
            # hard guarantee across every possible model/SDK version - a
            # value outside `choices` is treated as a provider failure,
            # never silently accepted, since callers rely on the invariant
            # that the return value is always one of `choices`.
            logger.warning("Gemini classify() returned an out-of-schema choice: %r", choice)
            raise GeminiServiceError(f"Gemini returned an unrecognized classification: {choice!r}")

        return choice
