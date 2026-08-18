"""Groq implementation of ModelService (Phase 14.5).

Used two ways (see app/api/deps.py's get_model_service):
  - As the fallback provider, wrapped by FallbackModelService, when Gemini
    hits a transient/quota failure.
  - Directly, when LLM_PROVIDER=groq (a development override to test Groq
    without needing to exhaust Gemini's quota first).

Mirrors gemini_service.py's shape deliberately - same three ModelService
methods, same "classify a caught exception into ProviderUnavailableError vs.
a plain <Provider>ServiceError" pattern - so nothing above this layer needs
to care which provider it's talking to.

Phase 18 removed the last "compound" (Groq's autonomous-search) model usage
from this app - the web_search route now retrieves via Tavily instead (see
app/langgraph/nodes/web_search_node.py) and generates through this same
plain GroqService like every other route. Everything here is a normal Groq
chat-completions call; there is no compound-model-specific code left.
"""
import json
import logging
from collections.abc import AsyncIterator

import groq

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


class GroqServiceError(Exception):
    """A Groq call failed. Callers should turn this into a clean,
    generic-to-the-client error - never surface the raw provider exception."""


# groq-python already gives each of these its own exception class (unlike
# google-genai's single APIError-with-a-status-string), so classifying a
# retryable failure is mostly an isinstance check rather than a code/status
# lookup - RateLimitError is a 429, InternalServerError covers Groq's own
# 5xx/service-unavailable responses, APITimeoutError is a request timeout.
_RETRYABLE_EXCEPTIONS = (groq.RateLimitError, groq.InternalServerError, groq.APITimeoutError)


def _raise_classified(exc: Exception, message: str) -> None:
    if isinstance(exc, _RETRYABLE_EXCEPTIONS):
        logger.warning("Groq reported a retryable failure: %s", type(exc).__name__)
        raise ProviderUnavailableError(message) from exc
    raise GroqServiceError(message) from exc


def _to_messages(history: list[ModelTurn]) -> list[dict[str, str]]:
    # Groq's API is OpenAI-compatible: "assistant", not Gemini's "model".
    return [
        {"role": "assistant" if turn["role"] == "model" else "user", "content": turn["content"]}
        for turn in history
    ]


class GroqService(ModelService):
    def __init__(self, *, api_key: str, model: str) -> None:
        self._client = groq.AsyncGroq(api_key=api_key)
        self._model = model

    async def generate(self, history: list[ModelTurn]) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=_to_messages(history),
            )
        except Exception as exc:
            logger.exception("Groq chat.completions.create call failed")
            _raise_classified(exc, "Failed to get a response from Groq")

        content = response.choices[0].message.content
        if not content:
            logger.warning("Groq returned no content")
            raise GroqServiceError("Groq returned an empty response")

        return content

    async def generate_stream(self, history: list[ModelTurn]) -> AsyncIterator[str]:
        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=_to_messages(history),
                stream=True,
            )
        except Exception as exc:
            logger.exception("Groq streaming call failed to start")
            _raise_classified(exc, "Failed to start a response from Groq")

        try:
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        except Exception as exc:
            # Classification only - see gemini_service.py's identical
            # comment: whether it's safe to actually fall back from a
            # mid-stream failure is FallbackModelService's call, not
            # this method's, since only the caller knows if output
            # already went out to the user.
            logger.exception("Groq streaming failed mid-response")
            _raise_classified(exc, "Groq's response was interrupted")

    async def classify(self, history: list[ModelTurn], *, instructions: str, choices: list[str]) -> str:
        # json_schema/strict structured output is unreliable on at least one
        # current Groq model (openai/gpt-oss-120b silently ignores it per
        # Groq's own community reports as of this writing) - json_object
        # ("valid JSON, no schema enforcement") is the reliable feature
        # across Groq's model line, so the schema is enforced by instruction
        # text instead, then validated below exactly like Gemini's
        # response_schema enum is defensively re-validated - the guarantee
        # callers get (return value is always one of `choices`) is identical
        # either way, just enforced in code here instead of at the API level.
        system_prompt = (
            f"{instructions}\n\n"
            f'Respond with ONLY a JSON object of the exact form {{"choice": "<value>"}}, '
            f"where <value> is exactly one of: {', '.join(choices)}. No other text."
        )
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "system", "content": system_prompt}, *_to_messages(history)],
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            logger.exception("Groq classify() call failed")
            _raise_classified(exc, "Failed to classify with Groq")

        content = response.choices[0].message.content
        if not content:
            logger.warning("Groq classify() returned no content")
            raise GroqServiceError("Groq returned an empty classification")

        try:
            parsed = json.loads(content)
            choice = parsed["choice"]
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("Groq classify() returned unparseable JSON: %r", content)
            raise GroqServiceError("Groq returned a malformed classification") from exc

        if choice not in choices:
            logger.warning("Groq classify() returned an out-of-schema choice: %r", choice)
            raise GroqServiceError(f"Groq returned an unrecognized classification: {choice!r}")

        return choice

    async def generate_with_tools(
        self,
        history: list[ModelTurn],
        *,
        tools: list[ToolSpec],
        exchanges: list[ToolExchange] | None = None,
    ) -> ModelToolResponse:
        messages = _to_messages(history)
        for exchange in exchanges or []:
            call = exchange["tool_call"]
            # OpenAI-compatible shape: the model's tool_calls turn, then one
            # "tool" role message per result, matched by tool_call_id.
            messages.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {"name": call["name"], "arguments": json.dumps(call["arguments"])},
                        }
                    ],
                }
            )
            messages.append(
                {"role": "tool", "tool_call_id": call["id"], "content": exchange["result_content"]}
            )

        groq_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            }
            for tool in tools
        ]

        try:
            response = await self._client.chat.completions.create(
                model=self._model, messages=messages, tools=groq_tools,
            )
        except Exception as exc:
            logger.exception("Groq generate_with_tools() call failed")
            _raise_classified(exc, "Failed to get a response from Groq")

        message = response.choices[0].message
        tool_calls: list[ToolCall] = [
            {"id": tc.id, "name": tc.function.name, "arguments": json.loads(tc.function.arguments)}
            for tc in (message.tool_calls or [])
        ]

        return {"text": message.content or None, "tool_calls": tool_calls}
