from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from viatradetgbot.notifications.delivery import NotificationRejectedError

if TYPE_CHECKING:
	from aiogram import Bot

TELEGRAM_MESSAGE_LIMIT = 4096


class EmptyNotificationTextError(ValueError):
	"""A notification adapter cannot send an empty Telegram message."""


class TelegramNotificationDelivery:
	def __init__(self, bot: Bot) -> None:
		self._bot = bot

	async def send_text(self, chat_id: str, text: str) -> None:
		chunks = _split_message_text(text)
		try:
			for chunk in chunks:
				await self._bot.send_message(chat_id=chat_id, text=chunk, parse_mode=None)
		except (TelegramBadRequest, TelegramForbiddenError) as exception:
			raise NotificationRejectedError from exception


def _split_message_text(text: str) -> tuple[str, ...]:
	if not text:
		raise EmptyNotificationTextError

	chunks: list[str] = []
	remaining_text = text
	while len(remaining_text) > TELEGRAM_MESSAGE_LIMIT:
		last_separator = max(
			remaining_text.rfind("\n", 0, TELEGRAM_MESSAGE_LIMIT),
			remaining_text.rfind(" ", 0, TELEGRAM_MESSAGE_LIMIT),
		)
		chunk_end = last_separator + 1 if last_separator > 0 else TELEGRAM_MESSAGE_LIMIT
		chunks.append(remaining_text[:chunk_end])
		remaining_text = remaining_text[chunk_end:]

	chunks.append(remaining_text)
	return tuple(chunks)
