from __future__ import annotations

from aiogram import Router

from viatradetgbot.bot.handlers.error import router as error_router
from viatradetgbot.bot.handlers.start import router as start_command_router


def create_handlers_router() -> Router:
	router = Router(name=__name__)

	router.include_routers(start_command_router, error_router)

	return router
