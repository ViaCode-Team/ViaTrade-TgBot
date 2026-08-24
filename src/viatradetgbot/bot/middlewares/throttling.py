from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from aiogram import BaseMiddleware

if TYPE_CHECKING:
	from collections.abc import Awaitable, Callable

	from aiogram.types import TelegramObject

MAX_TRACKED_CHATS = 10_000

logger = logging.getLogger(__name__)


class ThrottlingMiddleware(BaseMiddleware):
	def __init__(self, rate_limit_seconds: float) -> None:
		self._rate_limit_seconds = rate_limit_seconds
		self._blocked_until_by_chat_id: dict[int, float] = {}

	async def __call__(
		self,
		handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
		event: TelegramObject,
		data: dict[str, Any],
	) -> Any:
		chat = getattr(event, "chat", None)
		if chat is None:
			return await handler(event, data)

		now = time.monotonic()
		blocked_until = self._blocked_until_by_chat_id.get(chat.id)
		if blocked_until is not None and blocked_until > now:
			logger.warning(
				"Telegram message throttled: chat_id=%s retry_after_seconds=%.2f",
				chat.id,
				blocked_until - now,
			)
			return None

		self._remember_chat(chat.id, now)
		return await handler(event, data)

	def _remember_chat(self, chat_id: int, now: float) -> None:
		if len(self._blocked_until_by_chat_id) >= MAX_TRACKED_CHATS:
			self._discard_expired_chats(now)
		if len(self._blocked_until_by_chat_id) >= MAX_TRACKED_CHATS:
			self._blocked_until_by_chat_id.pop(next(iter(self._blocked_until_by_chat_id)))
		self._blocked_until_by_chat_id[chat_id] = now + self._rate_limit_seconds

	def _discard_expired_chats(self, now: float) -> None:
		expired_chat_ids = [
			chat_id
			for chat_id, blocked_until in self._blocked_until_by_chat_id.items()
			if blocked_until <= now
		]
		for chat_id in expired_chat_ids:
			del self._blocked_until_by_chat_id[chat_id]
