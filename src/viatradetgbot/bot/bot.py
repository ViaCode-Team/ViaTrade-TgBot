from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram import Bot, Dispatcher

from viatradetgbot.bot.handlers import create_handlers_router

if TYPE_CHECKING:
	from viatradetgbot.bot.telegram_links import TelegramAccountLinker


class TelegramBot:
	def __init__(self, token: str, account_linker: TelegramAccountLinker) -> None:
		self._bot = Bot(token=token)
		self._dispatcher = Dispatcher()
		self._account_linker = account_linker

		self._dispatcher.include_router(create_handlers_router())

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
