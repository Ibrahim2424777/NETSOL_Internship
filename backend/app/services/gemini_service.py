"""Gemini implementation of ModelService, using Google's google-genai SDK.

Nothing outside this file (and the settings it reads) knows this app talks to
Gemini specifically - the rest of the AI layer only ever sees the ModelService
interface.
"""
import base64
import json
import logging
from collections.abc import AsyncIterator

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.services.model_service import (
    ModelService,
    ModelToolResponse,
    ModelTurn,
    ProviderUnavailableError,
    ToolCall,
    ToolExchange,
    ToolSpec,
)

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

    async def generate(self, history: list[ModelTurn]) -> str:
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

    async def generate_with_tools(
        self,
        history: list[ModelTurn],
        *,
        tools: list[ToolSpec],
        exchanges: list[ToolExchange] | None = None,
    ) -> ModelToolResponse:
        contents = _to_contents(history)
        for exchange in exchanges or []:
            call = exchange["tool_call"]
            # The model's own function-call turn, then our function-response
            # turn - Gemini's required shape for continuing a tool-calling
            # conversation. gemini-3.5-flash is a "thinking" model and
            # requires the ORIGINAL thought_signature to be replayed on this
            # part when there's more than one tool-calling round-trip in a
            # turn (verified live: a single-exchange test worked without it,
            # but a real 2-tool-offered agent loop failed with "Function
            # call is missing a thought_signature... required for tools to
            # work correctly" once a second call/response pair was added) -
            # see ToolCall.provider_data in model_service.py.
            raw_signature = call.get("provider_data", {}).get("thought_signature")
            thought_signature = base64.b64decode(raw_signature) if raw_signature else None
            contents.append(
                types.Content(
                    role="model",
                    parts=[types.Part(
                        function_call=types.FunctionCall(
                            id=call["id"], name=call["name"], args=call["arguments"],
                        ),
                        thought_signature=thought_signature,
                    )],
                )
            )
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part(function_response=types.FunctionResponse(
                        id=call["id"], name=call["name"],
                        response=json.loads(exchange["result_content"]),
                    ))],
                )
            )

        gemini_tool = types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name=tool["name"], description=tool["description"], parameters=tool["parameters"],
                )
                for tool in tools
            ]
        )

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=contents,
                config=types.GenerateContentConfig(tools=[gemini_tool]),
            )
        except Exception as exc:
            logger.exception("Gemini generate_with_tools() call failed")
            _raise_classified(exc, "Failed to get a response from Gemini")

        candidate = response.candidates[0] if response.candidates else None
        if candidate is None or candidate.content is None or not candidate.content.parts:
            raise GeminiServiceError("Gemini returned an empty tool-calling response")

        tool_calls: list[ToolCall] = []
        text_parts: list[str] = []
        for part in candidate.content.parts:
            if part.function_call is not None:
                provider_data = {}
                if part.thought_signature:
                    provider_data["thought_signature"] = base64.b64encode(part.thought_signature).decode()
                tool_calls.append(
                    {
                        "id": part.function_call.id or part.function_call.name,
                        "name": part.function_call.name,
                        "arguments": dict(part.function_call.args or {}),
                        "provider_data": provider_data,
                    }
                )
            elif part.text:
                text_parts.append(part.text)

        return {"text": "".join(text_parts) or None, "tool_calls": tool_calls}
