"""Custom asyncio event loop factory for Uvicorn.

psycopg's async mode (used by the LangGraph Postgres checkpointer) cannot run
under Windows' default ProactorEventLoop - it requires a SelectorEventLoop.
Uvicorn picks ProactorEventLoop on win32 by design (uvicorn/loops/asyncio.py),
since uvloop isn't available there.

Passed to Uvicorn via --loop app.core.event_loop:event_loop_factory, which
Uvicorn imports and calls directly instead of its built-in loop setups. On
non-Windows platforms this defers to uvloop (if installed) or the standard
SelectorEventLoop, matching Uvicorn's own "auto" behavior - the override only
changes anything on Windows.
"""
import asyncio
import sys


def event_loop_factory() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()

    try:
        import uvloop
    except ImportError:
        return asyncio.SelectorEventLoop()
    return uvloop.new_event_loop()
