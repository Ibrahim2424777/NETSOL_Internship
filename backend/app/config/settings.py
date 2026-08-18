"""Application configuration.

All runtime configuration is read from environment variables (optionally via a
local .env file). Nothing in this module should ever contain a real secret —
see .env.example for the full list of variables a deployment must provide.
"""
import json
from functools import lru_cache
from typing import Annotated, Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Application ---
    APP_NAME: str = "AI Chatbot Backend"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # --- API ---
    API_V1_PREFIX: str = "/api/v1"
    # NoDecode: pydantic-settings would otherwise try to JSON-decode this env
    # var itself (and error out) before our validator below ever sees it.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    # --- PostgreSQL (source of truth for all persisted data) ---
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_chatbot"
    # Same numbers SQLAlchemy already defaults to - made explicit and
    # tunable per-deployment rather than buried in the library, since
    # "how many concurrent DB connections can this process hold open" is a
    # real capacity question in production, not just a framework detail.
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # --- Redis (active-conversation / session cache only, never source of truth) ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- LangGraph conversational memory ---
    # How many of the most recent messages (both roles combined) are sent to
    # Gemini as context on each turn. Simple recency-based trimming, not
    # summarization - keeps the per-request payload to Gemini bounded even
    # once a chat has hundreds of messages in Postgres/the checkpoint.
    MAX_HISTORY_MESSAGES: int = 20

    # --- LangGraph routing (Phase 14) ---
    # How many of the most recent messages the router's classification call
    # sees - deliberately much smaller than MAX_HISTORY_MESSAGES, since the
    # router only needs enough context to resolve pronouns/follow-ups
    # ("where is it being played?"), not the full conversation - keeping
    # this small is what keeps the extra per-turn classification call cheap.
    ROUTER_CONTEXT_MESSAGES: int = 6

    # --- Document RAG ---
    # Local, on-disk LanceDB directory - separate storage layer from
    # Postgres/Redis, survives backend restarts on its own (see
    # app/services/vector_store_service.py).
    RAG_VECTOR_DB_PATH: str = "./data/vector_store"
    # fastembed model id (ONNX, CPU-only, no PyTorch) - free/local, no paid
    # embedding API. 384-dim, ~130MB, downloaded once and cached by fastembed.
    RAG_EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    # How many chunks the retriever returns per query - bounds how much
    # retrieved text gets sent to Gemini on top of conversation history.
    RAG_TOP_K: int = 4
    # Minimum cosine similarity (0-1) for a chunk to count as a real match.
    # LanceDB's top-k search always returns its k nearest neighbors even for
    # a completely off-topic query, just with a low score - without this
    # floor, an unrelated question would still get document chunks stuffed
    # into the prompt and shown as "Sources used". Calibrated empirically
    # against this project's test document: genuinely relevant queries
    # scored ~0.76-0.82, off-topic ones ~0.37-0.54 - 0.6 sits cleanly in the
    # gap. Recalibrate if RAG_EMBEDDING_MODEL changes.
    RAG_MIN_SCORE: float = 0.6
    # ~150-200 words: large enough that a chunk usually contains a whole rule
    # or paragraph from the source document (most facts in a policy-style
    # document span 2-4 sentences), small enough that RAG_TOP_K chunks stay a
    # reasonable prompt addition rather than most of a page.
    RAG_CHUNK_SIZE: int = 800
    # ~15% of chunk size - enough overlap that a fact split across a chunk
    # boundary still appears whole in at least one of the two chunks.
    RAG_CHUNK_OVERLAP: int = 120

    # --- Gemini ---
    # Required (no default) - same fail-fast reasoning as the secrets below.
    GEMINI_API_KEY: str
    # Overridable without a code change in case this default is ever retired
    # or a faster/cheaper model becomes the better fit. Verified working
    # against the live API as of this writing - Gemini model availability
    # shifts over time (e.g. gemini-2.5-flash is already retired for new
    # API keys), so if this 404s later, check
    # https://ai.google.dev/gemini-api/docs/models for a current name.
    GEMINI_MODEL: str = "gemini-3.5-flash"

    # --- Groq (fallback LLM provider, Phase 14.5) ---
    # Not required (empty default) - the app still starts and runs Gemini-only
    # if this is unset; a fallback simply isn't available (see
    # app/api/deps.py's get_model_service).
    GROQ_API_KEY: str = ""
    # Verified live against api.groq.com/openai/v1/models as of this writing.
    # openai/gpt-oss-120b, not one of the Llama models - Groq deprecated
    # llama-3.1-8b-instant/llama-3.3-70b-versatile (free/developer tier) in
    # favor of the gpt-oss line, so a Llama default would already be a
    # deprecated choice. 131k context, and (unlike some Groq models as of
    # this writing) supports Structured Outputs, though GroqService uses
    # JSON mode + explicit validation instead - see its classify() docstring
    # for why.
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    # Which provider handles live chat traffic. "gemini" (default) = Gemini
    # primary, Groq fallback (if GROQ_API_KEY is set and
    # LLM_FALLBACK_PROVIDER=groq). "groq" = talk to Groq directly, no
    # fallback wrapping - a development override (Phase 14.5 doc section 15)
    # for testing Groq without burning Gemini's quota first.
    LLM_PROVIDER: str = "gemini"
    # "groq" (default) or "none" to disable fallback entirely even when a
    # Groq key is configured.
    LLM_FALLBACK_PROVIDER: str = "groq"

    # --- Web search (Phase 14.6) ---
    # groq/compound-mini, not the larger groq/compound - the full compound
    # model returned a 413 "Request Entity Too Large" on ordinary,
    # non-trivial prompts in live testing (a currently-reported Groq issue,
    # not something on our end), while compound-mini handled the same
    # prompts reliably and still does real web search + returns citations.
    # This is the PRIMARY provider for the web_search route specifically -
    # the reverse of GROQ_MODEL's role, which is the FALLBACK for
    # normal/rag. Gemini is web search's fallback (see app/api/deps.py).
    GROQ_COMPOUND_MODEL: str = "groq/compound-mini"

    # --- MCP (Phase 17) ---
    # The standalone MCP server (../mcp-server) - a separate process/project
    # with its own lifecycle, not started by this app. Configurable rather
    # than hardcoded (Phase 17 doc section 22) so a deployment can point at
    # an MCP server running anywhere, not just localhost.
    MCP_SERVER_URL: str = "http://127.0.0.1:8100/mcp"
    MCP_REQUEST_TIMEOUT_SECONDS: float = 15.0

    # --- Google OAuth 2.0 ---
    # Required (no default): there is no safe placeholder for an OAuth client
    # secret, so the app fails fast at startup instead of failing confusingly
    # on the first login attempt.
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str = "http://localhost:5173/auth/callback"

    # --- JWT ---
    # Required for the same reason as the Google secrets above - signing
    # tokens with a predictable default would be a real vulnerability, so
    # there is no fallback value.
    JWT_SECRET: str
    JWT_REFRESH_SECRET: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: Any) -> Any:
        """Allow CORS_ORIGINS to be set in .env either as JSON
        (CORS_ORIGINS=["http://localhost:3000"]) or, more conveniently, as a
        plain comma-separated string (CORS_ORIGINS=http://localhost:3000,http://localhost:5173).
        """
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                return json.loads(stripped)
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor. Use this (not Settings() directly) everywhere,
    so the process reads and parses the environment exactly once.
    """
    return Settings()
