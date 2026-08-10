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
- **Every chat message passes through a LangGraph graph** (`user_input → model node → response`), not a direct
  Gemini call — the graph is structured so future nodes (memory, RAG, tool calling, ...) can be inserted without
  reworking the entry points that call it.
- **The model provider is abstracted** behind a `ModelService` interface; the current implementation
  (`GeminiService`) is the only thing that knows Gemini exists.

## Tech stack

| | |
|---|---|
| **Backend** | Python, FastAPI, LangGraph, Google Gemini API, PostgreSQL, Redis, SQLAlchemy (async), Alembic, Pydantic, JWT, Google OAuth 2.0 |
| **Frontend** | React 19, TypeScript, Bootstrap 5, React Router, Axios, TanStack Query (React Query) |

## Project structure

```
backend/
  app/
    api/            REST endpoints + dependency-injection utilities (deps.py)
    auth/            JWT encode/decode, Google OAuth verification, get_current_user
    config/          Settings (env vars) and logging setup
    database/        SQLAlchemy engine/session, ORM models, repositories
    langgraph/       Graph state, nodes, graph builder
    middleware/      Request logging, request-ID correlation, security headers
    redis/           Redis client, active-conversation cache
    schemas/         Pydantic request/response models
    services/        Model service abstraction, Gemini implementation, chat execution
    utils/           Rate limiting
    workers/         Background message persistence
  alembic/           Database migrations
frontend/
  src/
    components/      Reusable UI (chat sidebar, message bubbles, modals, error boundary)
    context/         AuthContext (auth state + actions)
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
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | **Yes** | — | From Google Cloud Console |
| `GOOGLE_REDIRECT_URI` | No | `http://localhost:5173/auth/callback` | Must match the frontend and Google Cloud Console exactly |
| `JWT_SECRET` / `JWT_REFRESH_SECRET` | **Yes** | — | Two different random values; app fails to start without them |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `15` | |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | |
| `CORS_ORIGINS` | No | localhost:3000, localhost:5173 | Comma-separated |
| `ENVIRONMENT` | No | `development` | Set to `production` to enable secure cookies + HSTS |

Full list with inline explanations: [`backend/.env.example`](backend/.env.example).

### Frontend (`frontend/.env`)

| Variable | Notes |
|---|---|
| `VITE_API_BASE_URL` | Backend URL including `/api/v1` |
| `VITE_GOOGLE_CLIENT_ID` | Same Client ID as the backend's (public, not a secret) |
| `VITE_GOOGLE_REDIRECT_URI` | Must match the backend's `GOOGLE_REDIRECT_URI` and Google Cloud Console |

Full list: [`frontend/.env.example`](frontend/.env.example).

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

- **No conversation memory.** Each message is sent to Gemini independently; the model doesn't see prior turns
  in the same chat. The LangGraph workflow is deliberately structured so a memory node can be inserted later
  without reworking the surrounding code, but that node doesn't exist yet.
- **Chat titles don't auto-generate.** Every new chat starts as "New Chat" until manually renamed — there's no
  equivalent of deriving a title from the first message.
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

None of these block running or using the app — they're the natural next phases.
