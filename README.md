# AI Chatbot

A full-stack, ChatGPT-style AI chatbot: Google sign-in, streaming responses from Gemini through a LangGraph
workflow, and persistent conversation history. Built as a production-style reference implementation — FastAPI
backend, React frontend, PostgreSQL as the durable store, Redis as a cache layer only.

## How it works

```
Browser (React)                 FastAPI backend                  External services
────────────────                ─────────────────                 ─────────────────
Sign in with Google  ─────────▶ Verify code with Google  ───────▶ Google OAuth
                      ◀───────  Issue JWT access token +
                                 HTTP-only refresh cookie

Send a message        ─────────▶ Cache in Redis, persist to
  (SSE POST)                      Postgres concurrently,
                                   run LangGraph workflow  ───────▶ Gemini (streamed)
                      ◀─────────  Stream chunks back as SSE

Load a conversation   ─────────▶ Redis cache-aside,
                                   falls back to Postgres
                      ◀─────────  Message history
```

- **PostgreSQL is the source of truth.** Every message is durably persisted; if Redis is unreachable or
  restarted, no data is lost — requests degrade to reading Postgres directly instead of failing.
- **Redis is a cache only** — active conversation messages (fast retrieval, 1-hour sliding TTL) and refresh-token
  session state (rotation-based revocation). It is never the only copy of anything.
- **Every chat message passes through one LangGraph graph**, not a direct Gemini call. A router node decides the
  path first, then the graph conditionally branches: `messages → [router] → ([retriever (RAG)] | [web search] |
  nothing) → [model] → END`, backed by a Postgres-persisted LangGraph checkpointer — `chat_id` doubles as the
  LangGraph `thread_id`, so conversation memory survives page refreshes *and* backend restarts, not just
  in-process state. See [Intelligent routing](#intelligent-routing) below for how normal/RAG are chosen, and
  [Web search](#web-search) for why that third route is a user toggle, not something the router infers.
- **The model provider is abstracted** behind a `ModelService` interface, and is itself fallback-capable: Gemini
  is primary for routing/normal/RAG, and a transient Gemini failure (rate limit/quota/service-unavailable)
  automatically retries the same request on Groq before the user ever sees an error. See
  [Multi-provider LLM support](#multi-provider-llm-support) below.

## Tech stack

| | |
|---|---|
| **Backend** | Python, FastAPI, LangGraph (+ Postgres checkpointer), Google Gemini API, Groq API (fallback + web search via compound-mini), PostgreSQL, Redis, LanceDB (vector store), fastembed, SQLAlchemy (async), Alembic, Pydantic, JWT, Google OAuth 2.0 |
| **Frontend** | React 19, TypeScript, Bootstrap 5 (custom dark theme), React Router, Axios, TanStack Query (React Query) |

## Project structure

```
backend/
  app/
    api/            REST endpoints + dependency-injection utilities (deps.py)
    auth/            JWT encode/decode, Google OAuth verification, get_current_user
    config/          Settings (env vars) and logging setup
    core/            Windows event-loop fix for the Postgres checkpointer driver
    database/        SQLAlchemy engine/session, ORM models, repositories
    langgraph/       Graph state, nodes (router/retriever/web_search/model), the unified chat graph builder
    middleware/      Request logging, request-ID correlation, security headers
    rag/             Document ingestion pipeline + reusable RAG retriever
    redis/           Redis client, active-conversation cache
    schemas/         Pydantic request/response models
    services/        Model/embedding/vector-store service abstractions + implementations (Gemini, Groq, fallback)
    utils/           Rate limiting
    workers/         Background message persistence
  alembic/           Database migrations
  data/              Bundled RAG source document + generated vector store/embedding cache (gitignored)
frontend/
  src/
    components/      Reusable UI (chat sidebar, message bubbles, modals, error boundary)
    context/         AuthContext, SidebarContext (auth state + sidebar collapse/drawer state)
    hooks/           React Query hooks (chats, messages, send-message streaming)
    layouts/         Shared page chrome (public pages vs. authenticated app)
    pages/           Landing, Login, Chat, Profile, 404, OAuth callback
    routes/          Route definitions, protected-route guard
    services/        Axios client, auth token store, typed API calls, SSE stream parsing
```

## Prerequisites

- **Python 3.12+** and [`uv`](https://docs.astral.sh/uv/)
- **Node.js 20+** and npm
- **PostgreSQL** (a running server; the app creates its own tables via migrations)
- **Redis** (a running server)
- **A Google Cloud OAuth 2.0 Client ID** (Web application type) — see [Google's guide](https://developers.google.com/identity/protocols/oauth2)
- **A Gemini API key** from [Google AI Studio](https://aistudio.google.com/)

## Getting started

### 1. Backend

```powershell
cd backend
Copy-Item .env.example .env
```

Edit `.env`:
- `DATABASE_URL` — point at your Postgres instance and a database you've created (`CREATE DATABASE ai_chatbot;` or update the name in the URL to match one you already have).
- `REDIS_URL` — point at your Redis instance (the default `redis://localhost:6379/0` works for a local install).
- `GEMINI_API_KEY` — from Google AI Studio.
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — from Google Cloud Console.
- `JWT_SECRET` / `JWT_REFRESH_SECRET` — generate two **different** random values:
  ```powershell
  python -c "import secrets; print(secrets.token_urlsafe(64))"
  ```

Install dependencies and apply migrations:

```powershell
uv sync
uv run alembic upgrade head
```

Run the server:

```powershell
uv run uvicorn app.main:app --reload
```

The API is now at `http://localhost:8000`, with interactive docs at `http://localhost:8000/docs` and a health
check at `http://localhost:8000/api/v1/health`.

> **PowerShell script execution error?** If `npm`/`uv` commands are blocked by PowerShell's execution policy,
> either run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` once, or run these commands
> from Command Prompt (`cmd.exe`) instead, which isn't affected by the policy.

### 2. Frontend

```powershell
cd frontend
Copy-Item .env.example .env
```

Edit `.env`:
- `VITE_API_BASE_URL` — the backend URL from above, with `/api/v1` (default already matches: `http://localhost:8000/api/v1`).
- `VITE_GOOGLE_CLIENT_ID` — the **same** Client ID as the backend's `GOOGLE_CLIENT_ID` (this one is safe to expose publicly; it's not a secret).
- `VITE_GOOGLE_REDIRECT_URI` — defaults to `http://localhost:5173/auth/callback`.

Install dependencies and run:

```powershell
npm install
npm run dev
```

The app is now at `http://localhost:5173`.

### 3. Google Cloud Console setup

In your OAuth 2.0 Client ID's settings, add `http://localhost:5173/auth/callback` (or whatever
`VITE_GOOGLE_REDIRECT_URI` you're using) to **Authorized redirect URIs**. Without this, Google rejects the
sign-in with `redirect_uri_mismatch` instead of showing the consent screen.

### 4. Sign in and chat

With both servers running, open `http://localhost:5173`, sign in with Google, and start a conversation.

## Running tests / verifying it works

There's no automated test suite yet (see [Known limitations](#known-limitations--suggested-next-steps)). To
confirm everything is wired up correctly:

1. `curl http://localhost:8000/api/v1/health` should return `{"status":"ok","database":"ok","redis":"ok"}`.
2. Sign in through the browser, send a message, and confirm it streams in and appears in the sidebar.
3. Refresh the page — you should stay logged in (this is the refresh-token cookie at work, not local storage).

## Environment variables reference

### Backend (`backend/.env`)

| Variable | Required | Default | Notes |
|---|---|---|---|
| `DATABASE_URL` | No | local Postgres | `postgresql+asyncpg://...` |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | No | `5` / `10` | Raise under real concurrent load |
| `REDIS_URL` | No | `redis://localhost:6379/0` | |
| `GEMINI_API_KEY` | **Yes** | — | App fails to start without it |
| `GEMINI_MODEL` | No | `gemini-3.5-flash` | Check [Google's model list](https://ai.google.dev/gemini-api/docs/models) if this 404s later — model availability shifts over time |
| `GROQ_API_KEY` | No | *(empty)* | Free key from [console.groq.com/keys](https://console.groq.com/keys) — without it, the app runs Gemini-only, no fallback |
| `GROQ_MODEL` | No | `openai/gpt-oss-120b` | Check [Groq's model list](https://console.groq.com/docs/models) if this is retired — Groq already deprecated the Llama 3.1/3.3 models this app could have defaulted to |
| `LLM_PROVIDER` | No | `gemini` | `gemini` (real behavior: Gemini primary + Groq fallback) or `groq` (dev-only override — talk to Groq directly) |
| `LLM_FALLBACK_PROVIDER` | No | `groq` | `groq` or `none` to disable automatic fallback |
| `GROQ_COMPOUND_MODEL` | No | `groq/compound-mini` | Primary model for the web search route — the full `groq/compound` 413s on ordinary prompts as of this writing, see [Web search](#web-search) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | **Yes** | — | From Google Cloud Console |
| `GOOGLE_REDIRECT_URI` | No | `http://localhost:5173/auth/callback` | Must match the frontend and Google Cloud Console exactly |
| `JWT_SECRET` / `JWT_REFRESH_SECRET` | **Yes** | — | Two different random values; app fails to start without them |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `15` | |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | |
| `CORS_ORIGINS` | No | localhost:3000, localhost:5173 | Comma-separated |
| `ENVIRONMENT` | No | `development` | Set to `production` to enable secure cookies + HSTS |
| `RAG_VECTOR_DB_PATH` / `RAG_EMBEDDING_MODEL` | No | `./data/vector_store` / `BAAI/bge-small-en-v1.5` | LanceDB directory + fastembed model |
| `RAG_TOP_K` / `RAG_MIN_SCORE` | No | `4` / `0.6` | Chunks retrieved per query / minimum relevance to count as a match |
| `ROUTER_CONTEXT_MESSAGES` | No | `6` | How many recent messages the router's classification call sees |

Full list with inline explanations: [`backend/.env.example`](backend/.env.example).

### Frontend (`frontend/.env`)

| Variable | Notes |
|---|---|
| `VITE_API_BASE_URL` | Backend URL including `/api/v1` |
| `VITE_GOOGLE_CLIENT_ID` | Same Client ID as the backend's (public, not a secret) |
| `VITE_GOOGLE_REDIRECT_URI` | Must match the backend's `GOOGLE_REDIRECT_URI` and Google Cloud Console |

Full list: [`frontend/.env.example`](frontend/.env.example).

## Document RAG

The chatbot can answer questions grounded in a bundled fictional document (a 13-page "AI Research Handbook") via
Retrieval-Augmented Generation: the question is embedded (fastembed, local/CPU, no external API), matched against
chunks stored in a local LanceDB vector store, and the relevant chunks are handed to Gemini alongside the
question — never sent raw, always as structured "Retrieved Context" the model is instructed to ground its answer
in. See [`docs/rag.md`](docs/rag.md) for the full ingestion pipeline, chunking strategy, and why LanceDB was
chosen over the more common Chroma. To (re-)ingest the bundled document:

```powershell
cd backend
uv run python -m app.rag.ingest_cli
```

## Web search

An earlier phase tried live sports data (fixtures/scores) via TheSportsDB + CricketData.org's free tiers. Both had
real coverage gaps (TheSportsDB had **no current international cricket fixtures at all** for a real test case;
CricketData.org's data was series-level, not always per-match) that free-tier sports APIs weren't going to close.
That whole path — providers, team-name extraction, sport-specific normalization — has been retired in favor of a
general capability: a user-toggled **web search**, powered by Groq's `groq/compound-mini`, which does its own live
web search and citation-gathering while generating the answer, rather than us calling a narrow, single-purpose API.

- **It's a toggle, not something the router infers.** A small "Web search" button in the composer
  (`MessageComposer.tsx`) marks the *next* message only (it resets after sending, not a sticky per-chat mode).
  When on, the graph routes straight to the web_search branch, skipping the normal/RAG classifier call entirely —
  see [Intelligent routing](#intelligent-routing) for why this, unlike RAG, was made explicit rather than inferred.
- **One model call does search AND writes the final answer** — unlike RAG's retrieve-then-generate split, there's
  no separate "web_search retriever" node feeding a shared model node; `groq/compound-mini`'s own built-in search
  tool-use produces the grounded answer directly (`app/langgraph/nodes/web_search_node.py`), so that branch goes
  straight to `END` instead of converging on the shared model node.
- **Citations are real, not invented** — compound-mini's tool-call results (title + URL per source it actually
  used) are captured via a citation callback threaded through the `ModelService` interface
  (`on_search_result`, see `app/services/model_service.py`) and shown in the same "Sources" panel RAG uses, as
  clickable links.
- **Fallback direction is reversed here vs. everywhere else.** Routing/normal/RAG default to Gemini-primary,
  Groq-fallback (see [Multi-provider LLM support](#multi-provider-llm-support)); web search uses
  `groq/compound-mini` as **primary** (the search capability is the entire reason to route here) with **Gemini as
  fallback** if compound-mini fails — Gemini has no live search in this integration, so its fallback answer comes
  from its own training data, with an explicit instruction to say so if it isn't confident the information is
  current (verified live: it does — see Known limitations).
- **A real bug found and fixed during testing:** the first version of the grounding instruction literally said
  "use web search," which Gemini's `gemini-3.5-flash` interpreted as a tool-call directive — since no tools are
  configured on that call, it returned `finish_reason=MALFORMED_FUNCTION_CALL` with empty text every time the
  fallback path was hit. Fixed by rewording the instruction to describe the *goal* ("answer with current
  information, and say so if you're not confident") without ever using words that read as a tool invocation to
  Gemini. Verified live before and after the fix.
- **`groq/compound-mini`, deliberately not the larger `groq/compound`** — the full compound model returned a live
  `413 Request Entity Too Large` on an ordinary, non-trivial prompt in testing (a currently-reported Groq issue,
  not something on our end), reproduced twice; compound-mini handled the identical prompt reliably both times.
- **Verified live, not just by design:** a real "when is Pakistan's next cricket match" query via compound-mini
  correctly found the same Aug 19 2026 Pakistan vs. England Test fixture verified in earlier phases, with real
  cited sources; forcing compound-mini to fail confirmed the Gemini fallback answers cleanly (no crash, no empty
  response after the wording fix, zero citations as expected since Gemini didn't search); a multi-turn
  conversation (web search turn, then a plain turn) confirmed no source/state leakage across the turn boundary and
  correct memory continuity.

## Intelligent routing

The chat graph's router node decides, per message, whether a turn needs document retrieval:

- **How it decides:** the router node (`app/langgraph/nodes/router_node.py`) sends the last
  `ROUTER_CONTEXT_MESSAGES` (default 6) turns to Gemini with a structured-output call
  (`ModelService.classify()`, `response_mime_type="application/json"` + an enum-constrained `response_schema`) that
  is forced to return exactly one of `"normal"`, `"rag"` — never free text, so there's no parsing ambiguity. The
  classification prompt is intent-based, not keyword-based, and uses a short window of recent history to resolve
  follow-ups like "why is that important?" using whatever document topic the previous turn established.
- **`"web_search"` is deliberately NOT a classifier output.** It's a third possible value of the same `route`
  field in `ChatState`, but the router only ever writes it as an explicit override — see
  [Web search](#web-search). When the frontend's toggle sets `web_search_requested=True`, the router skips the
  classification call entirely and routes straight there; the classifier itself only ever chooses between
  `normal` and `rag` on its own. This was a deliberate design choice, not a limitation: a wrong *inferred* search
  would burn Groq quota on every ambiguous message, while a wrong classification between normal/RAG just means a
  slightly less-grounded (but still relevant) answer.
- **The graph:** `messages → [router] →` a conditional edge to `[retriever]`, `[web_search]`, or straight to
  `[model]`. The `rag`/`normal` branches converge on the shared model node (`[model] → END`); `web_search` does
  **not** — see [Web search](#web-search) for why.
- **No stale context across a route switch:** `retrieved_context` is a plain (non-appending) field in `ChatState`,
  so the router resets it to empty on *every* turn before picking a branch — without this, switching from a RAG
  question to a plain question mid-conversation would otherwise still carry the previous turn's document chunks
  into a prompt that never asked for them, since the RAG retriever simply wouldn't run to overwrite it.
- **Fails closed:** if the classification call itself errors (e.g. rate-limited), the router falls back to
  `normal` rather than guessing `rag` and risking an irrelevant retrieval call.
- **Observability:** the router logs `route=<choice>` on every turn (backend logs only). The frontend also shows
  a small, subtle "Sources" panel on RAG- and web-search-routed replies (document chunks or clickable citation
  links respectively) — transient and session-only (not persisted to Postgres), since it's a nice-to-have, not a
  core feature.
- **Zero changes needed above this layer:** the live chat endpoint (`POST /chats/{id}/messages`) and
  `ChatExecutionService.run_stream()` kept their exact pre-routing method signatures — only what happens *inside*
  the graph changed, so routing is transparent to callers.

## Multi-provider LLM support

Gemini's free tier has a hard daily request quota, which earlier phases' testing ran into directly (a real `429
RESOURCE_EXHAUSTED` blocked live verification mid-session). Rather than wait out a quota reset, the model layer
is now provider-independent, with Groq as an automatic fallback:

- **Same `ModelService` interface, two implementations.** `GeminiService` and `GroqService` (`app/services/`)
  both implement `generate()` / `generate_stream()` / `classify()` — the same three methods the interface already
  had before Groq existed, plus an optional `on_search_result` citation callback added in Phase 14.6 (see
  [Web search](#web-search)) that Gemini simply never calls. `GroqService` uses Groq's OpenAI-compatible API
  (`groq` Python SDK, `AsyncGroq`); which model it talks to is a constructor argument, so the SAME class serves
  two different roles with two different models — `GROQ_MODEL` (`openai/gpt-oss-120b` by default, Groq deprecated
  the Llama 3.1/3.3 models this app could otherwise have defaulted to) for the routing/normal/RAG fallback, and
  `GROQ_COMPOUND_MODEL` (`groq/compound-mini`) for web search. Neither `model_node.py`, `router_node.py`, nor
  `web_search_node.py` — the only callers of `ModelService` anywhere in the app — know or care which provider or
  model they're actually talking to; all three depend purely on the interface.
- **Two separate provider pairings, not one.** `get_model_service()` (routing/normal/RAG) is Gemini-primary,
  Groq-fallback. `get_web_search_model_service()` (`app/api/deps.py`) is the reverse — Groq's `compound-mini`
  primary, Gemini fallback — because for that one route, Groq's search capability is the entire reason to call
  it, not a backup plan. Both are thin `FallbackModelService` wrappers around the same two building blocks; only
  which one is "primary" differs.
- **`FallbackModelService`** (`app/services/fallback_model_service.py`) wraps a primary + fallback `ModelService`
  behind that same interface. This is the *only* place fallback logic lives — not duplicated per-node, per
  section 23 of the Phase 14.5 doc. It only acts on a dedicated `ProviderUnavailableError`, which each provider
  raises for itself after classifying a caught exception (Gemini: `google.genai.errors.APIError` with
  `code in {429, 503}` or `status in {RESOURCE_EXHAUSTED, UNAVAILABLE}`; Groq: `RateLimitError` /
  `InternalServerError` / `APITimeoutError`, which the `groq` SDK already separates as distinct exception types).
  Any other exception — a bug, a malformed prompt, a safety block — propagates from the primary as-is; a wrong
  prompt would fail on Groq too, so falling back for it would only burn quota and hide the real error.
- **Streaming fallback is stream-safe.** `FallbackModelService.generate_stream()` tracks whether the primary has
  already yielded any chunk. A failure *before* the first chunk falls back to Groq transparently — the frontend
  never knows a switch happened. A failure *after* streaming has started does **not** fall back (per the doc's
  explicit "don't stitch together two providers' half-answers" requirement) — the turn fails cleanly instead,
  which the endpoint already turns into the existing generic SSE error + un-sent user message (Phase 5 behavior,
  unchanged).
- **No duplicate calls.** The fallback is a `try`/`except`, not a race or a "call both and pick one" — Groq is
  never called when Gemini succeeds.
- **Configurable, not hardcoded:** `LLM_PROVIDER=gemini` (default) runs Gemini-primary/Groq-fallback;
  `LLM_PROVIDER=groq` is a development-only override to talk to Groq directly (no wrapper) without needing to
  exhaust Gemini's quota first, useful for testing. `LLM_FALLBACK_PROVIDER=none` disables fallback entirely. With
  no `GROQ_API_KEY` set at all, `get_model_service()` (`app/api/deps.py`) returns a bare `GeminiService` — byte-
  for-byte the same behavior as before this phase.
- **Verified live**, not just by code review: direct Gemini (succeeded normally, no Groq call logged), direct
  Groq (`generate`/streaming/`classify` all confirmed working), a real Gemini `429 RESOURCE_EXHAUSTED` error
  object confirmed to classify as `ProviderUnavailableError` while a `400 INVALID_ARGUMENT` correctly does *not*,
  end-to-end fallback through the full LangGraph chat graph for RAG (Groq correctly grounded its answer in the
  retrieved document chunks) and the (now-retired) sports route that existed at the time this fallback layer was
  built, a both-providers-fail case (raises cleanly, no crash/stack trace/corrupted stream), and two-turn
  conversations for both plain chat and RAG with every turn forced through the Groq fallback path — conversation
  memory/checkpointing continuity held up identically to Gemini-only runs (pronoun resolution across turns,
  correct message counts in the checkpoint).
- **This closed a real gap from Phase 14.** Its router test matrix (single-turn normal/RAG, multi-turn pronoun
  resolution, cross-route switching) had been blocked mid-session by Gemini's exhausted daily quota. Re-run after
  this phase's fallback was wired in, it passed fully — the very first case hit a live `429` and transparently
  fell back to Groq (logged), proving the fallback path in the exact real scenario it exists for.
- **Not implemented (per the doc's own scope):** no frontend indicator of which provider answered — optional per
  the doc, and the existing route indicator (see above) already covers the more useful "what capability answered"
  signal; which *provider* handled a turn is logged server-side only (`LLM provider: gemini` / `LLM provider:
  groq`), never the API keys themselves.

## Security notes

- Google's identity is verified server-side on every login; the frontend never trusts a token from Google
  directly.
- Access tokens live in memory only on the client (never `localStorage`); refresh tokens are HTTP-only,
  `SameSite=Lax` cookies that JavaScript can never read.
- Refresh tokens are single-use with rotation, tracked in Redis — a stolen-but-already-used token is rejected,
  and logout actually revokes the session server-side rather than just discarding a token client-side.
- `/auth/google` and `/auth/refresh` are rate-limited per IP.
- All database access goes through the SQLAlchemy ORM (parameterized queries) — no raw string-built SQL.
- Every unhandled backend exception is caught, logged with a request ID for correlation, and returns a generic
  message — internal error details never reach the client.

## Known limitations & suggested next steps

Honest gaps, not silently left undocumented:

- **Chat titles don't auto-generate.** Every new chat starts as "New Chat" until manually renamed — there's no
  equivalent of deriving a title from the first message.
- **Web search only ever runs on explicit user request**, never inferred — a message that would clearly benefit
  from current information gets a plain (possibly outdated-knowledge) answer unless the user notices and toggles
  it on. This was a deliberate tradeoff (see [Web search](#web-search)), not an oversight, but it does mean the
  feature's value depends on user awareness of the toggle.
- **`groq/compound` (the larger, non-mini web search model) is unreliable as of this writing** — it returned a
  live `413 Request Entity Too Large` on ordinary prompts in testing, reproduced twice. `groq/compound-mini` is
  used instead and has been reliable, but this is worth re-checking if `GROQ_COMPOUND_MODEL` is ever changed.
- **No automated test suite.** Every phase of this project was verified manually (including live browser
  testing via Playwright) rather than with a committed test suite — there's nothing to run in CI yet.
- **No Docker / docker-compose setup.** Each service (Postgres, Redis, backend, frontend) is run directly;
  there's no containerized one-command startup.
- **The chat list (sidebar) isn't cached in Redis** — only messages within a chat are. This matches the
  original scope ("active conversation cache"), but is worth knowing if the chat list becomes a bottleneck at
  scale.
- **Rate limiting is IP-based** and assumes the backend is reached directly. A deployment behind a reverse
  proxy would need it to read a trusted `X-Forwarded-For` header instead.
- **No CI/CD pipeline.**
- **Groq's structured-output (`json_schema`) mode is skipped deliberately.** `openai/gpt-oss-120b` (the default
  `GROQ_MODEL`) is reported to silently ignore `json_schema`/`strict` response formatting as of this writing, so
  `GroqService.classify()` uses the more broadly-reliable `json_object` mode plus an explicit instruction-prompt
  schema and post-parse validation instead — functionally equivalent (the return value is still guaranteed to be
  one of the caller's `choices`, or the call raises), just enforced in code rather than by the API itself.
- **Provider choice isn't surfaced to the frontend.** Which provider (Gemini vs. Groq/compound-mini) answered a
  given turn is logged server-side only, not sent to the client — the existing route indicator (normal/RAG/web
  search, see [Intelligent routing](#intelligent-routing)) already covers the more user-relevant signal, and web
  search's citations (see [Web search](#web-search)) already show which sources were actually used.

None of these block running or using the app — they're the natural next phases.
