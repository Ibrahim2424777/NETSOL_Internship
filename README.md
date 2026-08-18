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
  path first, then the graph conditionally branches: `messages → [router] → ([retriever (RAG)] → [model] |
  [web_search] | [agent]) → END`, backed by a Postgres-persisted LangGraph checkpointer — `chat_id` doubles as the
  LangGraph `thread_id`, so conversation memory survives page refreshes *and* backend restarts, not just
  in-process state. See [Intelligent routing](#intelligent-routing) below for how normal/RAG are chosen, and
  [Web search](#web-search) for why that third route is a user toggle, not something the router infers.
- **The "normal" route can call real tools.** `[agent]` (`app/langgraph/nodes/agent_node.py`) gives the model
  access to weather and (if configured) email tools exposed by a standalone MCP server — the model itself decides
  when a tool is needed via native function-calling, never a hardcoded keyword match. See
  [MCP Integration & Tool-Calling](#mcp-integration--tool-calling) below.
- **The model provider is abstracted** behind a `ModelService` interface, and is itself fallback-capable: Gemini
  is primary for routing/normal/RAG, and a transient Gemini failure (rate limit/quota/service-unavailable)
  automatically retries the same request on Groq before the user ever sees an error. See
  [Multi-provider LLM support](#multi-provider-llm-support) below.

## Tech stack

| | |
|---|---|
| **Backend** | Python, FastAPI, LangGraph (+ Postgres checkpointer), Google Gemini API, Groq API (fallback), Tavily (web search retrieval), PostgreSQL, Redis, LanceDB (vector store), fastembed, SQLAlchemy (async), Alembic, Pydantic, JWT, Google OAuth 2.0 |
| **Frontend** | React 19, TypeScript, Bootstrap 5 (custom dark theme), React Router, Axios, TanStack Query (React Query) |
| **MCP Server** | Python, official MCP SDK (`mcp`), Streamable HTTP, Open-Meteo (weather), Gmail API (email) — a standalone project the chatbot backend calls as an MCP client; see [MCP Integration & Tool-Calling](#mcp-integration--tool-calling) below |

## Project structure

```
backend/
  app/
    api/            REST endpoints + dependency-injection utilities (deps.py)
    auth/            JWT encode/decode, Google OAuth verification, get_current_user
    config/          Settings (env vars) and logging setup
    core/            Windows event-loop fix for the Postgres checkpointer driver
    database/        SQLAlchemy engine/session, ORM models, repositories
    langgraph/       Graph state, nodes (router/retriever/web_search/web_search_answer/model/agent), the unified chat graph builder
    mcp/             MCP client (app/mcp/client.py) - discovers/calls tools on the standalone MCP server
    middleware/      Request logging, request-ID correlation, security headers
    rag/             Document ingestion pipeline + reusable RAG retriever
    redis/           Redis client, active-conversation cache
    schemas/         Pydantic request/response models
    services/        Model/embedding/vector-store service abstractions + implementations (Gemini, Groq, fallback, Tavily)
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
mcp-server/          Standalone MCP server (weather + email tools) - separate project, own deps/venv.
  app/               config.py + weather/ (Open-Meteo) + email/ (Gmail API) - see mcp-server/README.md
  scripts/           gmail_authorize.py - one-time interactive Gmail OAuth setup
  server.py          Entry point (Streamable HTTP)
  tests/             Unit + HTTP-error + live-network tests
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
| `TAVILY_API_KEY` | No | *(empty)* | Free key from [tavily.com](https://tavily.com) — without it, web search still works, it just answers ungrounded with a disclaimer, see [Web search](#web-search) |
| `WEB_SEARCH_MAX_RESULTS` | No | `5` | Capped, not "retrieve dozens of pages" per the Phase 18 doc |
| `WEB_SEARCH_TIMEOUT_SECONDS` | No | `15` | Per-request Tavily timeout |
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
| `MCP_SERVER_URL` | No | `http://127.0.0.1:8100/mcp` | The standalone MCP server's Streamable HTTP endpoint (separate process, `mcp-server/`) — see [MCP Integration & Tool-Calling](#mcp-integration--tool-calling) |
| `MCP_REQUEST_TIMEOUT_SECONDS` | No | `15` | Timeout for MCP tool discovery/calls; not required for the app to start — if unreachable, the "normal" route degrades to tool-free chat |

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

A user-toggled **web search** capability, retrieval via [Tavily](https://tavily.com), answers generated by the same
Gemini/Groq `ModelService` pairing every other route uses.

This replaced an earlier (Phase 14.6) implementation that used Groq's `groq/compound-mini` — a model with its own
built-in autonomous search and browsing. Compound-mini did its own search AND wrote the final answer in one model
call; the problem was that it could (and reproducibly did, live) attempt to retrieve too many or too-large pages
for an entirely ordinary query and fail the whole turn with a `413 Request Entity Too Large`, with no fix available
from this app's side — Groq's compound API has no parameter to cap search result count or page size (confirmed by
reading their docs directly), and restricting which of compound's tools were enabled didn't help either. Phase 18
(see [`phase_18.md`](phase_18.md)) replaced retrieval outright with Tavily, a plain search API that returns a
bounded number of already-fetched snippets and never browses pages on its own — there's no equivalent failure mode
to reproduce.

- **It's a toggle, not something the router infers.** A small "Web search" button in the composer
  (`MessageComposer.tsx`) marks the *next* message only (it resets after sending, not a sticky per-chat mode).
  When on, the graph routes straight to the web_search branch, skipping the normal/RAG classifier call entirely —
  see [Intelligent routing](#intelligent-routing) for why this, unlike RAG, was made explicit rather than inferred.
  Unchanged from Phase 14.6 — Phase 18 only touched backend retrieval.
- **Retrieve, then generate — the same split RAG uses, kept as its own system.** `web_search_node.py` calls Tavily
  (`search_depth="basic"`, capped at `WEB_SEARCH_MAX_RESULTS`, default 5 — deliberately small, not "retrieve dozens
  of pages") and writes the results to `ChatState`; `web_search_answer_node.py` grounds a reply in them through
  `ModelService.generate_stream()` — real, token-by-token streaming again, unlike compound-mini's single non-streamed
  call. Kept as its own node pair rather than reusing RAG's `retriever_node.py`/`model_node.py` on purpose (Phase 18
  doc section 12): RAG is the app's private/document knowledge, web search is the public web via Tavily — different
  content, different citation shape, different failure modes, and merging them would blur that distinction for no
  benefit.
- **Citations are structural, not parsed from a model's tool-use output.** Tavily returns title + URL directly at
  retrieval time, before generation even starts, so `web_search_node.py` maps them straight into the same
  `WebSearchSource`/`MessageSource` shape RAG's citations already use — shown in the same "Sources" panel, as
  clickable links. (Phase 14.6's citation mechanism — a callback threaded through `ModelService.generate()`/
  `generate_stream()` to capture a Groq tool-call's search results — is gone along with compound-mini; nothing else
  in the app ever used it.)
- **One provider pairing for the whole app now.** Phase 14.6 gave web search its own reversed pairing
  (`groq/compound-mini` primary, Gemini fallback) because the search capability itself was the reason to call Groq.
  Tavily does retrieval now, so that reason is gone — web search generation uses the exact same
  `get_model_service()` (Gemini primary, Groq fallback) as routing/normal/RAG. See
  [Multi-provider LLM support](#multi-provider-llm-support).
- **Tavily failures degrade gracefully, they don't fail the turn.** A missing/invalid key, rate limit, timeout, or
  empty result set all collapse to the same signal (`TavilyUnavailableError`/`TavilyNotConfiguredError`, see
  `app/services/tavily_service.py`): `web_search_node.py` catches it, results end up empty, and
  `web_search_answer_node.py` explicitly instructs the model to say it has no live data rather than silently
  answering as if it had searched — satisfying the doc's "do not silently fabricate an answer" requirement the same
  way whether Tavily is simply unconfigured or a live call actually failed.
- **Verified live:** current-events queries (current PM of Pakistan, latest Pakistan cricket news) correctly
  grounded in real, dated results with clickable sources; a specific-source query surfaced the expected official
  page (GitHub's own releases listing) among its citations; an invalid Tavily API key, tested both directly and
  through the full chat graph, degraded cleanly with zero sources and an honest "I can't pull real-time data"
  answer instead of a crash; a multi-turn conversation (web search turn, then a plain follow-up with the toggle
  off) confirmed the toggle doesn't leak into the next turn *and* conversation memory/context still resolves
  correctly across the boundary.

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
- **The graph:** `messages → [router] →` a conditional edge to `[retriever]`, `[web_search]`, or `[agent]`
  (normal). `rag` converges on the shared, tool-free `[model]` node (`[retriever] → [model] → END`); `web_search`
  and `normal` each go straight to `END` from their own node — see [Web search](#web-search) and
  [MCP Integration & Tool-Calling](#mcp-integration--tool-calling) for why `normal`'s node (`[agent]`) can call
  tools while `rag`'s can't.
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
  both implement `generate()` / `generate_stream()` / `classify()` / `generate_with_tools()` — the same interface
  every caller depends on. `GroqService` uses Groq's OpenAI-compatible API (`groq` Python SDK, `AsyncGroq`);
  `GROQ_MODEL` (`openai/gpt-oss-120b` by default, Groq deprecated the Llama 3.1/3.3 models this app could otherwise
  have defaulted to) is its one and only model as of Phase 18 — the separate `groq/compound-mini` web-search model
  is gone along with the citation-callback plumbing (`on_search_result`) that only it ever used (see
  [Web search](#web-search)). Neither `model_node.py`, `router_node.py`, `web_search_answer_node.py`, nor
  `agent_node.py` — the only callers of `ModelService` anywhere in the app — know or care which provider they're
  actually talking to; all four depend purely on the interface.
- **One provider pairing for the whole app.** Before Phase 18, web search had its own reversed pairing
  (`groq/compound-mini` primary, Gemini fallback) because Groq's search capability was the entire reason to route
  there. Now that Tavily does retrieval (see [Web search](#web-search)) and web search generation is a plain
  grounded-answer call like RAG's, there's no reason for it to use a different provider pairing than everything
  else — `get_model_service()` (Gemini-primary, Groq-fallback) is the one and only `ModelService` the whole graph
  uses.
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

## MCP Integration & Tool-Calling

A **standalone** [Model Context Protocol](https://modelcontextprotocol.io) server lives at
[`mcp-server/`](mcp-server/) — its own project, own dependencies, own `.venv` — exposing weather and
email tools. The chatbot backend connects to it as an MCP client and gives the model itself the
ability to decide, mid-conversation, when calling one of those tools would produce a better answer:

```
Browser (React)          FastAPI/LangGraph                        MCP Server (mcp-server/,
                                                                     separate process)
                          [router] → normal → [agent]
                                                 │
                                                 ├─ 1. list available tools ────────▶ tools/list
                                                 │
                                                 ├─ 2. ask Gemini/Groq: "given the
                                                 │      conversation + these tool
                                                 │      schemas, respond or call
                                                 │      a tool?"
                                                 │
                                                 ├─ 3. IF the model requests a
                                                 │      tool call: execute it ─────▶ tools/call
                                                 │      (weather: Open-Meteo,
                                                 │       email: Gmail API)         ◀── result
                                                 │      feed the result back to
                                                 │      the model, repeat from 2
                                                 │      (up to 5 rounds)
                                                 │
                          ◀── final natural-language reply, "typed" in via SSE ────┘
```

### Architecture

- **`app/mcp/client.py`** (`MCPClientService`) wraps the official `mcp` Python SDK's
  `ClientSession` over Streamable HTTP — `list_tools()` (cached after the first call) and
  `call_tool(name, arguments)`. It's the only place in the backend that knows the MCP server exists;
  everything else depends on plain Python types (`ToolSpec`/`ToolCall`/`ToolExchange` in
  `app/services/model_service.py`), not the MCP SDK's own shapes.
- **`app/langgraph/nodes/agent_node.py`** replaces `model_node.py` for the "normal" route only (RAG
  still uses `model_node.py`, deliberately tool-free; web search uses its own retrieve-then-generate
  node pair, unrelated to MCP - see [Web search](#web-search)). It runs the request → execute →
  respond loop above, capped at 5 round-trips as a safety limit against a runaway tool-calling
  conversation.
- **The model decides, not the code.** `agent_node.py` never inspects the user's message for
  keywords like "weather" or "email" — it hands the model the tool schemas MCP itself advertises and
  lets Gemini's/Groq's own native function-calling decide whether and which tool to call. A plain
  "hi, how are you?" gets a normal, tool-free reply on the first round-trip, same as before this
  phase.
- **Both providers, via the same interface.** `ModelService.generate_with_tools()` is a new
  provider-agnostic method (alongside the existing `generate()`/`generate_stream()`/`classify()`)
  implemented natively by both `GeminiService` (Google's function-calling) and `GroqService`
  (OpenAI-compatible tool-calling) — `FallbackModelService` wraps it exactly like the other methods,
  so a mid-tool-call Gemini quota/rate-limit failure transparently falls back to Groq, verified live.
- **Deliberately non-streaming.** Whether a given model turn is "call a tool" or "here's my answer"
  can't be known until the model finishes deciding, so `generate_with_tools()` is a single blocking
  call rather than a token stream. Once a final answer is reached, its complete text is re-chunked
  into small word-batches with a short delay between them (`agent_node.py`'s `_fake_stream()`) so the
  frontend still gets the same typing-effect UI as a real stream. This is the one place in the graph
  that still needs this trick — RAG's `model_node.py` and web search's `web_search_answer_node.py`
  (see [Web search](#web-search)) both stream for real.
- **A real Gemini quirk found and fixed:** `gemini-3.5-flash` is a "thinking" model that requires its
  own `thought_signature` (an opaque reasoning-trace token attached to each function-call response
  part) to be captured and replayed on the *next* call when a turn involves more than one tool
  round-trip — omitting it works for a single exchange but fails a real 2-tool-offered conversation
  with `400 INVALID_ARGUMENT: Function call is missing a thought_signature`. Fixed by threading it
  through as opaque `ToolCall.provider_data` (`GroqService` never sets or reads this field — the
  difference is isolated inside Gemini's own implementation, not leaked into `agent_node.py`).
  Verified live: a real 2-round-trip weather exchange through the full chat graph, no fallback
  needed, completed correctly after the fix.
- **Graceful degradation if the MCP server is down.** `agent_node.py` catches connection failures
  from `list_tools()` and falls back to `tools=[]`, which routes to plain `generate_stream()` — real
  token streaming resumes and normal chat keeps working, the model just can't use tools that turn.
  Verified live (pointed the client at an unreachable port): the model gives an honest "I don't have
  access to real-time information" answer instead of erroring.

### Available tools

| Tool | What it does | Backing provider |
|---|---|---|
| `get_current_weather(location)` | Current conditions (temperature, feels-like, condition, humidity, wind, precipitation) | Open-Meteo (no API key) |
| `get_weather_forecast(location, date_str)` | Forecast for one specific date, up to 15 days out | Open-Meteo (no API key) |
| `send_email(to, subject, body)` | Sends a plain-text email from a configured Gmail account (`to="me"` resolves to the account owner) | Gmail API (OAuth) |
| `list_recent_emails(limit)` | Metadata only (sender/subject/snippet/date) for recent inbox messages | Gmail API (OAuth) |
| `read_email(message_id)` | Full plain-text body + headers for one message | Gmail API (OAuth) |

Email tools are optional — the server (and this integration) work fine with weather only if Gmail
isn't configured. Full tool descriptions, Gmail OAuth setup (a one-time `scripts/gmail_authorize.py`
run, separate from the chatbot's own Google login), and example calls: [`mcp-server/README.md`](mcp-server/README.md).

### Example interaction

```
User:      "Email me tomorrow's weather in Multan."
Assistant: [calls get_weather_forecast(location="Multan", date_str="2026-08-18")]
           [describes the draft: recipient "you", subject, and a body summarizing the forecast,
            and asks the user to confirm before sending — send_email's own tool description
            instructs the model to get confirmation first, since the server has no UI of its own
            to do this]
User:      "Yes, send it."
Assistant: [calls send_email(to="me", subject="...", body="...")]
           "Sent! ..."
```

### Privacy: tool results never become long-term memory

An email's contents, or a `send_email` confirmation exchange, live only in `agent_node.py`'s local
`exchanges` list for the duration of that one turn — never written to `ChatState`, never checkpointed
by LangGraph's Postgres saver. Only the user's original message (already in state before the node
runs) and the model's *final* natural-language reply are persisted — whatever the model chooses to
restate in that reply is far more minimal than a raw tool result, and the system instructions nudge
it to stay that way. This falls out of the loop's structure rather than needing per-message redaction
logic: nothing about how a turn is checkpointed changed, tool exchanges simply never enter that path.

### Frontend indicator

A small pill next to the "Assistant" label (e.g. "☁ Checked the weather") appears on replies where
`agent_node.py` actually called a tool — `tools_used` travels on the `done` SSE event
(`app/api/v1/endpoints/messages.py`) exactly like the existing route indicator, and is never
persisted (a page refresh loses it, same as route).

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

- **RAG wasn't re-verified live after the Phase 17 graph restructuring** (the "normal" route moved
  from `model_node.py` to the new `agent_node.py`) — low risk since `retriever_node.py`/
  `model_node.py` and the RAG conditional edge are byte-for-byte unchanged, but it's a code-review
  conclusion, not a live-tested one for that specific restructuring (it was, however, re-verified
  live as a regression check after the separate Phase 18 web-search refactor).
- **Chat titles don't auto-generate.** Every new chat starts as "New Chat" until manually renamed — there's no
  equivalent of deriving a title from the first message.
- **Web search only ever runs on explicit user request**, never inferred — a message that would clearly benefit
  from current information gets a plain (possibly outdated-knowledge) answer unless the user notices and toggles
  it on. This was a deliberate tradeoff (see [Web search](#web-search)), not an oversight, but it does mean the
  feature's value depends on user awareness of the toggle.
- **Tavily's free tier has its own monthly credit limit.** Once exhausted, web search degrades the same way an
  unconfigured key does (see [Web search](#web-search)) — an honest, ungrounded answer, not a crash — but it's
  worth knowing that isn't a bug if it happens.
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
- **Provider choice isn't surfaced to the frontend.** Which provider (Gemini vs. Groq) answered a given turn is
  logged server-side only, not sent to the client — the existing route indicator (normal/RAG/web search, see
  [Intelligent routing](#intelligent-routing)) already covers the more user-relevant signal, and web search's
  citations (see [Web search](#web-search)) already show which sources were actually used.

None of these block running or using the app — they're the natural next phases.
