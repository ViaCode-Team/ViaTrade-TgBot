from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import LinkPreviewOptions

from viatradetgbot.bot.handlers import register_handlers
from viatradetgbot.bot.middlewares import register_middlewares


def create_bot(token: str) -> Bot:
	return Bot(
		token=token,
		default=DefaultBotProperties(
			parse_mode=ParseMode.HTML,
			link_preview=LinkPreviewOptions(is_disabled=True),
		),
	)


def create_dispatcher(message_rate_limit_seconds: float) -> Dispatcher:
	dispatcher = Dispatcher()
	register_middlewares(dispatcher, message_rate_limit_seconds)
	register_handlers(dispatcher)
	return dispatcher
