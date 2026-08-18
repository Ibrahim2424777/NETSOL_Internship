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
"""
import json
import logging
from collections.abc import AsyncIterator, Callable

import groq

from app.services.model_service import (
    ModelService,
    ModelToolResponse,
    ModelTurn,
    ProviderUnavailableError,
    SearchCitation,
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

# Local retry budget (this attempt + N-1 retries) for a bare in-band
# groq.APIError - see _raise_classified. Confirmed live to be
# query-dependent and non-deterministic: the identical request to
# groq/compound-mini can fail with "Request Entity Too Large" and then
# succeed on a fresh retry, with no client-side change - restricting
# compound_custom.tools.enabled_tools to just web_search (see
# _compound_kwargs) was tried and confirmed live NOT to eliminate it, so
# more attempts (rather than a different request shape) is the only lever
# that's actually shown to help empirically. 3 gives a meaningfully better
# chance of getting through before falling back to Gemini, without an
# unbounded retry loop for a genuinely persistent failure.
_COMPOUND_RETRY_ATTEMPTS = 3


def _raise_classified(exc: Exception, message: str) -> None:
    # A bare groq.APIError - the EXACT type, not one of its named
    # HTTP-status subclasses (BadRequestError, AuthenticationError, ...,
    # which all also inherit from APIError) - is how the SDK surfaces an
    # in-band SSE "event: error" Groq's own service reports mid-stream (see
    # groq/_streaming.py's __stream__), separate from a normal HTTP error
    # response. Confirmed live: groq/compound-mini can hit a mid-stream
    # "Request Entity Too Large" this way when its search tool pulls back
    # a large page for a given query - a provider-side problem with THIS
    # request, not a client bug, so it's treated as retryable the same as
    # the named subclasses above. Deliberately NOT a blanket
    # isinstance(exc, groq.APIError) - that would also swallow
    # BadRequestError/AuthenticationError, which mean OUR request or
    # credentials are wrong; falling back for those would silently mask a
    # real bug instead of surfacing it.
    if isinstance(exc, _RETRYABLE_EXCEPTIONS) or type(exc) is groq.APIError:
        logger.warning("Groq reported a retryable failure: %s", type(exc).__name__)
        raise ProviderUnavailableError(message) from exc
    raise GroqServiceError(message) from exc


def _to_messages(history: list[ModelTurn]) -> list[dict[str, str]]:
    # Groq's API is OpenAI-compatible: "assistant", not Gemini's "model".
    return [
        {"role": "assistant" if turn["role"] == "model" else "user", "content": turn["content"]}
        for turn in history
    ]


def _compound_kwargs(model: str) -> dict:
    # Restricts Groq's "compound" models (Phase 14.6) to their `web_search`
    # tool only - excludes `visit_website` (fetches a full raw page, unlike
    # web_search's bounded snippets), `code_interpreter`, and `wolfram_alpha`,
    # none of which this app's web-search route needs. Confirmed live to be
    # the actual cause of a real, reproducible `413 Request Entity Too Large`
    # / bare groq.APIError on ordinary news queries (e.g. a live cricket
    # match) - compound-mini choosing to visit_website on a large live-blog
    # page, not the number of search results per se. A no-op (empty dict) for
    # any non-compound model - `compound_custom` is a compound-only concept.
    if "compound" not in model:
        return {}
    return {"compound_custom": {"tools": {"enabled_tools": ["web_search"]}}}


def _citations_from_executed_tools(executed_tools) -> list[SearchCitation]:
    """Only Groq's "compound" models set executed_tools at all (plain chat
    models like gpt-oss-120b never do) - a search tool call's results carry
    title/url pairs the model actually drew on. No-ops (returns []) for any
    other tool type (e.g. code execution) or when nothing was found."""
    citations: list[SearchCitation] = []
    for tool in executed_tools or []:
        search_results = getattr(tool, "search_results", None)
        results = getattr(search_results, "results", None) if search_results else None
        for result in results or []:
            if result.url:
                citations.append({"title": result.title or result.url, "url": result.url})
    return citations


class GroqService(ModelService):
    def __init__(self, *, api_key: str, model: str) -> None:
        self._client = groq.AsyncGroq(api_key=api_key)
        self._model = model

    async def generate(
        self,
        history: list[ModelTurn],
        *,
        on_search_result: Callable[[SearchCitation], None] | None = None,
    ) -> str:
        # Local retries, ONLY for a bare in-band groq.APIError (see
        # _raise_classified and _COMPOUND_RETRY_ATTEMPTS) - unlike
        # RateLimitError/InternalServerError, which mean the provider itself
        # is struggling and retrying locally would just waste time before an
        # inevitable fallback. response is always set by the time the loop
        # exits: _raise_classified always raises, so either this succeeds
        # within the attempt budget or the function never reaches the line
        # below.
        response = None
        for attempt in range(_COMPOUND_RETRY_ATTEMPTS):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=_to_messages(history),
                    **_compound_kwargs(self._model),
                )
                break
            except Exception as exc:
                if type(exc) is groq.APIError and attempt < _COMPOUND_RETRY_ATTEMPTS - 1:
                    logger.warning(
                        "Groq in-band error on generate() - retrying (attempt %d/%d): %s",
                        attempt + 1, _COMPOUND_RETRY_ATTEMPTS, exc,
                    )
                    continue
                logger.exception("Groq chat.completions.create call failed")
                _raise_classified(exc, "Failed to get a response from Groq")

        content = response.choices[0].message.content
        if not content:
            logger.warning("Groq returned no content")
            raise GroqServiceError("Groq returned an empty response")

        if on_search_result is not None:
            executed_tools = getattr(response.choices[0].message, "executed_tools", None)
            for citation in _citations_from_executed_tools(executed_tools):
                on_search_result(citation)

        return content

    async def generate_stream(
        self,
        history: list[ModelTurn],
        *,
        on_search_result: Callable[[SearchCitation], None] | None = None,
    ) -> AsyncIterator[str]:
        # Local retries (fresh request, from scratch each time) for a bare
        # in-band groq.APIError (see _raise_classified and
        # _COMPOUND_RETRY_ATTEMPTS) - gated on yielded_any so a retry never
        # happens after real output already reached the caller, for the
        # same reason FallbackModelService won't switch providers
        # mid-stream: two partial answers can't be stitched together. If
        # the error recurs after some output, or on the final attempt, or
        # is a different (provider-health) exception, it's classified and
        # raised for FallbackModelService to handle instead.
        for attempt in range(_COMPOUND_RETRY_ATTEMPTS):
            try:
                stream = await self._client.chat.completions.create(
                    model=self._model,
                    messages=_to_messages(history),
                    stream=True,
                    **_compound_kwargs(self._model),
                )
            except Exception as exc:
                logger.exception("Groq streaming call failed to start")
                _raise_classified(exc, "Failed to start a response from Groq")

            yielded_any = False
            try:
                async for chunk in stream:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yielded_any = True
                        yield delta.content
                    if on_search_result is not None:
                        for citation in _citations_from_executed_tools(getattr(delta, "executed_tools", None)):
                            on_search_result(citation)
                return
            except Exception as exc:
                if (
                    type(exc) is groq.APIError
                    and not yielded_any
                    and attempt < _COMPOUND_RETRY_ATTEMPTS - 1
                ):
                    logger.warning(
                        "Groq in-stream error before any output - retrying (attempt %d/%d): %s",
                        attempt + 1, _COMPOUND_RETRY_ATTEMPTS, exc,
                    )
                    continue
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
