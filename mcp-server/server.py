"""Entry point for the standalone "Personal AI Tools" MCP server
(Phase 16: weather, Phase 17: + email).

Run with:
    uv run python server.py

Serves Streamable HTTP at http://{MCP_HOST}:{MCP_PORT}{MCP_STREAMABLE_HTTP_PATH}
(default: http://127.0.0.1:8100/mcp) - see README.md for how the FastAPI/
LangGraph backend connects to this as an MCP client, and app/config.py for
how host/port/path are configured.

This process is intentionally separate from the main chatbot backend
(backend/) - a different Python project, different .venv, different
lifecycle. See the repo root README for the placement rationale.
"""
import logging

from mcp.server import MCPServer

from app.config import get_settings
from app.email.tools import register_email_tools
from app.weather.tools import register_weather_tools

settings = get_settings()

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

mcp = MCPServer(
    name=settings.MCP_SERVER_NAME,
    instructions=(
        "Tools for personal AI assistants: current weather and weather forecasts for any "
        "human-readable location (via Open-Meteo), and email - sending and reading - for this "
        "server's configured personal Gmail account. Location strings are geocoded "
        "automatically - never pass raw coordinates. Sending email is irreversible - only do it "
        "with the user's clear intent."
    ),
)

register_weather_tools(mcp)

# Email tools are only registered when Gmail is actually configured - a
# server with no GMAIL_* env vars set still starts fine and serves weather
# tools normally, it just doesn't advertise send_email/list_recent_emails/
# read_email at all (rather than registering them and having every call
# fail with an auth error) - see scripts/gmail_authorize.py for setup.
if settings.email_configured:
    register_email_tools(mcp)
    logger.info("Email tools registered (Gmail account: %s)", settings.GMAIL_USER_EMAIL)
else:
    logger.warning(
        "Email tools NOT registered - Gmail is not configured "
        "(GMAIL_CLIENT_ID/GMAIL_CLIENT_SECRET/GMAIL_REFRESH_TOKEN/GMAIL_USER_EMAIL). "
        "See README.md's Email section and scripts/gmail_authorize.py."
    )


if __name__ == "__main__":
    logger.info(
        "Starting %s - Streamable HTTP on http://%s:%s%s",
        settings.MCP_SERVER_NAME,
        settings.MCP_HOST,
        settings.MCP_PORT,
        settings.MCP_STREAMABLE_HTTP_PATH,
    )
    mcp.run(
        transport="streamable-http",
        host=settings.MCP_HOST,
        port=settings.MCP_PORT,
        streamable_http_path=settings.MCP_STREAMABLE_HTTP_PATH,
    )
