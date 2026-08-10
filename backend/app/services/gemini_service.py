"""Gemini implementation of ModelService, using Google's google-genai SDK.

Nothing outside this file (and the settings it reads) knows this app talks to
Gemini specifically - the rest of the AI layer only ever sees the ModelService
interface.
"""
import logging
from collections.abc import AsyncIterator

from google import genai
from google.genai import types

from app.services.model_service import ModelService, ModelTurn

logger = logging.getLogger(__name__)


class GeminiServiceError(Exception):
    """A Gemini call failed. Callers should turn this into a clean,
    generic-to-the-client error - never surface the raw provider exception."""


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

    async def generate(self, history: list[ModelTurn]) -> str:
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=_to_contents(history),
            )
        except Exception as exc:
            logger.exception("Gemini generate_content call failed")
            raise GeminiServiceError("Failed to get a response from Gemini") from exc

        if not response.text:
            logger.warning("Gemini returned no text (possibly blocked by safety filters)")
            raise GeminiServiceError("Gemini returned an empty response")

        return response.text

    async def generate_stream(self, history: list[ModelTurn]) -> AsyncIterator[str]:
        try:
            # generate_content_stream returns a coroutine that resolves to
            # the actual async iterator - it must be awaited before iterating.
            stream = await self._client.aio.models.generate_content_stream(
                model=self._model,
                contents=_to_contents(history),
            )
        except Exception as exc:
            logger.exception("Gemini generate_content_stream call failed to start")
            raise GeminiServiceError("Failed to start a response from Gemini") from exc

        try:
            async for chunk in stream:
                if chunk.text:
                    yield chunk.text
        except Exception as exc:
            logger.exception("Gemini streaming failed mid-response")
            raise GeminiServiceError("Gemini's response was interrupted") from exc
