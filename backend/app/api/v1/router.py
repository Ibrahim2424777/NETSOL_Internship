"""Aggregates every v1 endpoint router into one.

Future phases add their routers here (users) — this stays the single include
point mounted onto the app in app/main.py.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import auth, chats, health, messages

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(chats.router)
api_router.include_router(messages.router)
