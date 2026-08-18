# Personal AI Tools — MCP Server (Phase 16 + 17)

A standalone [Model Context Protocol](https://modelcontextprotocol.io) server exposing tools an AI
assistant can call: **weather** (Phase 16, Open-Meteo, no key required) and **email** (Phase 17,
Gmail API via OAuth).

## Why this exists / where it fits

The main chatbot (`../backend`, `../frontend`) now calls this server on every "normal"-routed chat
turn, via an MCP client living in `backend/app/mcp/` and a tool-calling LangGraph node
(`backend/app/langgraph/nodes/agent_node.py`):

```
React  →  FastAPI/LangGraph  →  MCP Client (backend/app/mcp/)  →  MCP Server (this project)
                                                                       ├── Weather tools (Phase 16)
                                                                       └── Email tools    (Phase 17)
```

The model itself (Gemini or Groq) decides when a tool is needed, using each provider's native
function-calling — the backend never pattern-matches the user's message to decide "this needs
weather." See the root [`README.md`](../README.md)'s "MCP Integration & Tool-Calling" section for
how the client/agent side works; this file covers the server itself.

## Why a separate project, not part of `backend/`

- **Logically separate concern.** This is a tool provider, not part of the chat request path — it
  has its own lifecycle (can be started/stopped/redeployed independently of the chatbot).
- **Separate dependencies.** It only needs the MCP SDK + an HTTP client, not FastAPI/SQLAlchemy/
  LangGraph/Postgres/Redis — bundling it into `backend/`'s dependency set would mean the chatbot
  process pulls in MCP SDK weight it doesn't use yet (and vice versa).
- **Matches the existing repo convention.** `backend/` and `frontend/` are already independent
  sibling directories, each with their own dependency manager and no shared workspace config — this
  follows the same pattern rather than inventing a new one (e.g. nesting inside `backend/app/`).

## Requirements

- Python 3.12+ and [`uv`](https://docs.astral.sh/uv/)
- No API key needed for weather (see "Weather API" below)
- A Google Cloud OAuth 2.0 Desktop client + one-time browser consent for email (optional — the
  server runs fine without it, just without email tools; see "Email" below)

## Install

```powershell
cd mcp-server
uv sync
```

## Run the server

```powershell
uv run python server.py
```

Serves **Streamable HTTP** at:

```
http://127.0.0.1:8100/mcp
```

(host/port/path are configurable — see `.env.example`; copy it to `.env` if you want to change
them, though the defaults work out of the box with no `.env` file at all).

### Why Streamable HTTP, not stdio

The doc's own end-state (React → FastAPI/LangGraph → MCP Client → MCP Server) requires the chatbot
backend to connect to this server as a *network* client, potentially from a different process or
host — a stdio-only server can only ever be launched and piped to by a single parent process, which
doesn't fit that shape. Streamable HTTP is the current MCP SDK's transport for exactly this case.

## Weather API — Open-Meteo, no key required

Chosen after comparing three current (2026) free options:

| Provider | Free forecast range | Needs a key? | Location input |
|---|---|---|---|
| **Open-Meteo** (used) | 16 days | **No** — free for non-commercial use, no signup | lat/lon only — needs geocoding (see below) |
| WeatherAPI.com | 3 days (free tier cap) | Yes | Plain string, does its own geocoding |
| OpenWeatherMap | 5 days, coarse 3-hour buckets (free tier) | Yes | Name-based lookup is deprecated/unmaintained; pushes you to their geocoding API anyway |

Open-Meteo won on: no account/key to manage (nothing to expire or leak), the longest free forecast
window by far, and all the current-condition fields the doc asks for (temperature, feels-like,
condition, humidity, wind speed/direction, precipitation). Its one gap — no built-in place-name
search on the forecast endpoint — is closed by Open-Meteo's own companion Geocoding API (also free,
also keyless), so the whole thing stays a single-provider integration.

There is deliberately **no `WEATHER_API_KEY`** in `.env.example` — see `app/config.py`'s comment for
why that's a documented decision, not an oversight.

## Location handling

Both weather tools accept a human-readable string ("Multan", "Lahore, Pakistan", "London, UK", "New
York") — never coordinates. `app/weather/geocoding.py` resolves it via Open-Meteo's Geocoding API
first, then calls the Forecast API with the resolved lat/lon.

**Known provider quirk, handled explicitly:** Open-Meteo's geocoder matches place-name tokens
against its own database and does not recognize 2-letter country abbreviations — `"London, UK"`
(the doc's own example) returns zero results, while `"London, United Kingdom"` and plain `"London"`
both work (verified live, not assumed). `resolve_location()` retries with just the text before the
first comma when the full query comes back empty, so `"City, XY"`-style queries succeed. This trades
a small amount of precision (a same-named city elsewhere could in principle outrank the intended one
once the country qualifier is dropped) for actually answering the query shapes the tool descriptions
themselves invite. See `tests/test_client_errors.py::test_geocoding_falls_back_to_text_before_comma`.

## Tools

### `get_current_weather(location: str)`

Current conditions right now: temperature, feels-like temperature, condition, humidity, wind
speed/direction, recent precipitation, day/night, observation time. Fields the provider doesn't
return come back as `null`, never guessed.

### `get_weather_forecast(location: str, date_str: str)`

Forecast for one specific date (`YYYY-MM-DD`), from today through 15 days ahead (Open-Meteo's free
daily-forecast window — see `WEATHER_MAX_FORECAST_DAYS`). A date outside that range returns a clear
error naming the actual supported range instead of guessing or truncating.

Full input/output JSON schemas are declared on each tool (Pydantic-generated) and are visible via
`tools/list` — see below.

## Email — Gmail API via OAuth (Phase 17)

Email tools are **optional** — the server starts fine without them (weather tools still register),
and only registers `send_email`/`list_recent_emails`/`read_email` if all four `GMAIL_*` settings
below are configured. This mirrors the weather tools' own "degrade gracefully, don't crash" pattern.

### Why Gmail API + raw REST, not a heavier alternative

- **Gmail, not a generic transactional-email provider (Resend/SendGrid/etc.)** — the doc's own
  end-to-end demo ("email me tomorrow's weather") reads most naturally as "send FROM my own inbox,"
  which only a real mailbox provider can do; a transactional sender would need a verified custom
  domain and couldn't also support `list_recent_emails`/`read_email` at all.
- **Raw HTTP (`httpx`) + `google-auth`/`google-auth-oauthlib` for token refresh only** — not the full
  `google-api-python-client` — matching this project's existing convention of talking to provider
  REST APIs directly (see how `weather/client.py` calls Open-Meteo, or how the main backend calls
  Gemini/Groq) rather than pulling in a heavyweight provider SDK for a handful of endpoints.
- **A separate OAuth boundary from the chatbot's own Google login.** The main app's `GOOGLE_CLIENT_ID`/
  `GOOGLE_CLIENT_SECRET` (`backend/.env`) authenticate *users signing into the chatbot* — a completely
  different concern from *this server sending/reading mail as one specific Gmail account*. The two
  never share a client ID, secret, or token.

### One-time setup

1. **Google Cloud Console** (same or a different project from the chatbot's own OAuth client — your
   choice): enable the **Gmail API**, then create an OAuth 2.0 **Desktop app** client ID (not "Web
   application" — a desktop client is what supports the local-loopback flow the next step uses).
   Download or copy its Client ID and Client Secret.
2. From `mcp-server/`, run the one-time interactive authorization script:
   ```powershell
   uv run python scripts/gmail_authorize.py
   ```
   It prompts for the Client ID/Secret from step 1, opens a browser for you to sign in and consent
   (scopes: `gmail.send`, `gmail.readonly`) with the **Gmail account you want the assistant to use**,
   then prints `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` / `GMAIL_REFRESH_TOKEN` / `GMAIL_USER_EMAIL`
   lines — paste all four into `mcp-server/.env`.
3. Restart the server. `Email tools registered (Gmail account: ...)` in the startup log confirms it
   picked up the config; `Email tools NOT registered - Gmail is not configured` means one of the four
   is still missing/empty.

The refresh token is long-lived (doesn't expire from normal use) — this is a one-time setup, not a
per-session login.

### `send_email(to: str, subject: str, body: str)`

Sends a plain-text email from the configured Gmail account. `to="me"` is a sentinel that resolves
server-side to `GMAIL_USER_EMAIL` — the intended shape for "email me X" requests, since it means the
chatbot backend never needs to know the user's actual email address at all. The tool's own
description (visible via `tools/list`) explicitly tells the model to confirm the recipient/subject/
body with the user before calling this — the server itself has no confirmation step (it isn't
conversational), so that instruction is the only guardrail; see the root README's tool-calling
section for how `agent_node.py` reinforces it.

### `list_recent_emails(limit: int = 10)`

Metadata only (sender, subject, snippet, date, message id) for the N most recent inbox messages —
never full bodies, and `limit` is capped server-side (`EMAIL_LIST_MAX_RESULTS`, default 25)
regardless of what's requested, so a single tool call can't pull an unbounded amount of mail into the
conversation.

### `read_email(message_id: str)`

Full plain-text body (HTML is stripped) plus headers for one specific message, identified by the id
returned from `list_recent_emails`. Long bodies are truncated (`EMAIL_BODY_MAX_CHARS`, default 4000)
with `truncated: true` on the result rather than silently cutting off without saying so.

### Privacy note

Nothing about *what* an email tool returns is specific to this server — how that result is (or isn't)
retained in conversation memory is entirely the calling backend's responsibility. See the root
README's tool-calling section for why raw tool results (including email bodies) never get written to
LangGraph's checkpointed state.

## Example tool calls (via MCP Inspector CLI)

```powershell
# List all registered tools with their schemas (weather always; email only if configured)
npx @modelcontextprotocol/inspector --cli http://127.0.0.1:8100/mcp --method tools/list

# Current weather
npx @modelcontextprotocol/inspector --cli http://127.0.0.1:8100/mcp `
  --method tools/call --tool-name get_current_weather --tool-arg location="Multan, Pakistan"

# Forecast for a specific date
npx @modelcontextprotocol/inspector --cli http://127.0.0.1:8100/mcp `
  --method tools/call --tool-name get_weather_forecast `
  --tool-arg location="London, UK" --tool-arg date_str="2026-08-22"

# Send yourself an email (requires Gmail configured - see "Email" above)
npx @modelcontextprotocol/inspector --cli http://127.0.0.1:8100/mcp `
  --method tools/call --tool-name send_email `
  --tool-arg to="me" --tool-arg subject="Test" --tool-arg body="Hello from MCP Inspector."

# List recent inbox messages (metadata only)
npx @modelcontextprotocol/inspector --cli http://127.0.0.1:8100/mcp `
  --method tools/call --tool-name list_recent_emails --tool-arg limit=5
```

Example `get_current_weather` result:

```json
{
  "location": "Multan, Punjab, Pakistan",
  "latitude": 30.19679,
  "longitude": 71.47824,
  "temperature_c": 34.5,
  "feels_like_c": 38.7,
  "condition": "Clear sky",
  "humidity_percent": 51,
  "wind_kph": 14.7,
  "wind_direction_deg": 192,
  "precipitation_mm": 0.0,
  "is_day": true,
  "observed_at": "2026-08-17T10:30",
  "timezone": "Asia/Karachi"
}
```

An invalid location or unsupported date returns `isError: true` with a plain-text explanation (no
stack trace) — e.g. `"Error executing tool get_weather_forecast: 2027-01-01 is outside the supported
forecast range (2026-08-17 through 2026-09-01, 16 days including today)."`

## Testing with MCP Inspector

The [official MCP Inspector](https://github.com/modelcontextprotocol/inspector) was used during
development to verify (not just "Python starts without errors"):

1. The server starts and the `/mcp` endpoint is reachable.
2. Both weather tools are advertised with correct input/output schemas.
3. Tools can actually be called and return real, live weather data.
4. Error paths (`get_current_weather` on a nonexistent place, `get_weather_forecast` on an
   out-of-range date) return clean `isError: true` results, not crashes.

With the server running (`uv run python server.py`), either drive it headlessly via the `--cli`
flag (commands above), or launch the interactive web UI:

```powershell
npx @modelcontextprotocol/inspector
```
then connect it to `http://127.0.0.1:8100/mcp` (transport: Streamable HTTP) from the UI.

## Automated tests

```powershell
uv run pytest -v
```

37 tests: weather tool-layer logic (date validation, field mapping, error propagation — HTTP calls
faked via `monkeypatch`), weather HTTP-level error translation (timeout/5xx/429/malformed JSON —
mocked via `pytest-httpx`), email tool-layer logic (recipient validation, `to="me"` resolution,
metadata-only listing, body truncation — all `monkeypatch`-based, no real Gmail account needed),
Gmail HTTP-level error translation (401/403/404/429/5xx/timeout — mocked via `pytest-httpx`), a
Gmail-not-configured auth test, and 3 live tests hitting the real Open-Meteo API (the doc's own
example queries: `get_current_weather("Multan, Pakistan")`, `get_current_weather("London, UK")`, a
supported forecast date). Deselect the network-dependent ones with:

```powershell
uv run pytest -m "not live"
```

## Project layout

```
mcp-server/
  server.py                  Entry point - builds the MCPServer, registers tools, runs it
  scripts/
    gmail_authorize.py         One-time interactive Gmail OAuth script (prints .env values to paste)
  app/
    config.py                 Settings (pydantic-settings, mirrors backend/app/config/settings.py)
    weather/
      geocoding.py             Place name -> lat/lon via Open-Meteo Geocoding API
      client.py                 Thin HTTP client over Open-Meteo's Forecast API
      codes.py                   WMO weather-code -> text description table
      models.py                   Pydantic result shapes (structured tool output)
      errors.py                   WeatherError subclasses -> clean isError:true tool results
      tools.py                     The two @mcp.tool()-registered functions
    email/
      gmail_auth.py             OAuth refresh-token -> access-token exchange (google-auth)
      gmail_client.py            Thin HTTP client over the Gmail REST API + error translation
      mime.py                    RFC2822/base64url message building + MIME body extraction
      models.py                  Pydantic result shapes (structured tool output)
      errors.py                  EmailError subclasses -> clean isError:true tool results
      tools.py                   The three @mcp.tool()-registered functions
  tests/
    test_weather_tools.py       Weather tool-layer unit tests (monkeypatched)
    test_client_errors.py        Weather HTTP-level error-translation tests (pytest-httpx)
    test_live_integration.py      Real-network tests against Open-Meteo
    test_email_tools.py          Email tool-layer unit tests (monkeypatched)
    test_gmail_client_errors.py   Gmail HTTP-level error-translation tests (pytest-httpx)
    test_gmail_auth.py           Gmail auth/not-configured tests
```

## Known limitations

- **Geocoding is single-best-match only.** `resolve_location()` takes the first result Open-Meteo's
  geocoder returns; it doesn't disambiguate between multiple same-named places (e.g. there are
  several "Springfield"s) beyond whatever ranking Open-Meteo's own API applies.
- **No caching.** Every tool call hits Open-Meteo/Gmail fresh. Fine at their free-tier limits for a
  portfolio project; would be worth adding for real traffic.
- **Condition text is a static WMO code lookup**, not provider-supplied prose — Open-Meteo returns a
  numeric code, not a description string, so `app/weather/codes.py` is the source of truth for the
  `condition` field's wording.
- **Email is plain-text only.** `send_email` doesn't support HTML bodies or attachments; `read_email`
  strips HTML down to plain text rather than preserving formatting. Sufficient for the doc's own
  "email me tomorrow's weather" use case, not a general-purpose email client replacement.
- **No email search/filter tools.** `list_recent_emails` is unfiltered (most recent N only) — no
  `search_emails(query)` equivalent to Gmail's own search syntax.
