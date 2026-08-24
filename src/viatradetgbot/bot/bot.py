from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import LinkPreviewOptions

from viatradetgbot.bot.handlers import register_handlers
from viatradetgbot.bot.middlewares import register_middlewares

if TYPE_CHECKING:
	from viatradetgbot.bot.telegram_links import TelegramAccountLinker


class TelegramBot:
	def __init__(
		self,
		token: str,
		account_linker: TelegramAccountLinker,
		message_rate_limit_seconds: float,
	) -> None:
		self._bot = Bot(
			token=token,
			default=DefaultBotProperties(
				parse_mode=ParseMode.HTML,
				link_preview=LinkPreviewOptions(is_disabled=True),
			),
		)
		self._dispatcher = Dispatcher()
		register_middlewares(self._dispatcher, message_rate_limit_seconds)
		self._account_linker = account_linker

		register_handlers(self._dispatcher)

	@property
	def bot(self) -> Bot:
		return self._bot

	async def run(self) -> None:
		await self._dispatcher.start_polling(
			self._bot,
			close_bot_session=False,
			account_linker=self._account_linker,
		)

	async def close(self) -> None:
		await self._bot.session.close()
