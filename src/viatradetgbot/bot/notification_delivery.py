from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from viatradetgbot.notifications.delivery import NotificationRejectedError

if TYPE_CHECKING:
	from aiogram import Bot


class TelegramNotificationDelivery:
	def __init__(self, bot: Bot) -> None:
		self._bot = bot

	async def send_text(self, chat_id: int, text: str) -> None:
		try:
			await self._bot.send_message(chat_id=chat_id, text=text)
		except (TelegramBadRequest, TelegramForbiddenError) as exception:
			raise NotificationRejectedError from exception
