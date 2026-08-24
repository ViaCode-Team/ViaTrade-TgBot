from __future__ import annotations

from aiogram import Dispatcher

from viatradetgbot.bot.middlewares.logging import LoggingMiddleware
from viatradetgbot.bot.middlewares.throttling import ThrottlingMiddleware


def register_middlewares(dispatcher: Dispatcher, message_rate_limit_seconds: float) -> None:
	dispatcher.message.outer_middleware(ThrottlingMiddleware(message_rate_limit_seconds))
	dispatcher.update.outer_middleware(LoggingMiddleware())


__all__ = ["register_middlewares"]
