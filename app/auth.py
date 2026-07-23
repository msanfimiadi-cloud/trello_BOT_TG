from __future__ import annotations

from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar

from telegram import Update
from telegram.ext import ContextTypes


Handler = TypeVar("Handler", bound=Callable[..., Awaitable[None]])


def access_required(handler: Handler) -> Handler:
    """Protect a handler with the database-backed access check."""
    @wraps(handler)
    async def wrapped(self: Any, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self.require_allowed(update):
            await handler(self, update, context)
    return wrapped  # type: ignore[return-value]


def admin_required(handler: Handler) -> Handler:
    """Protect a handler with the database-backed administrator check."""
    @wraps(handler)
    async def wrapped(self: Any, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self.require_admin(update):
            await handler(self, update, context)
    return wrapped  # type: ignore[return-value]
