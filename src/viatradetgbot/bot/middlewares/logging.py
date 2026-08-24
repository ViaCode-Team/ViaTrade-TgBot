from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from aiogram import BaseMiddleware
from aiogram.types import Update

if TYPE_CHECKING:
	from collections.abc import Awaitable, Callable

	from aiogram.types import (
		CallbackQuery,
		ChatMemberUpdated,
		InlineQuery,
		Message,
		PreCheckoutQuery,
		TelegramObject,
	)

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
	async def __call__(
		self,
		handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
		event: TelegramObject,
		data: dict[str, Any],
	) -> Any:
		if not isinstance(event, Update):
			return await handler(event, data)

		logger.info(
			"Received Telegram update: update_id=%s event_type=%s attributes=%s",
			event.update_id,
			event.event_type,
			self._get_event_attributes(event),
		)
		return await handler(event, data)

	def _get_event_attributes(self, update: Update) -> dict[str, object]:
		if update.message is not None:
			attributes = self._get_message_attributes(update.message)
		elif update.callback_query is not None:
			attributes = self._get_callback_query_attributes(update.callback_query)
		elif update.inline_query is not None:
			attributes = self._get_inline_query_attributes(update.inline_query)
		elif update.pre_checkout_query is not None:
			attributes = self._get_pre_checkout_query_attributes(update.pre_checkout_query)
		elif update.my_chat_member is not None:
			attributes = self._get_chat_member_attributes(update.my_chat_member)
		elif update.chat_member is not None:
			attributes = self._get_chat_member_attributes(update.chat_member)
		else:
			attributes = {}
		return attributes

	@staticmethod
	def _get_message_attributes(message: Message) -> dict[str, object]:
		return {
			"chat_id": message.chat.id,
			"chat_type": message.chat.type,
			"message_id": message.message_id,
			"user_id": message.from_user.id if message.from_user is not None else None,
			"content_type": message.content_type,
			"is_command": bool(message.text and message.text.startswith("/")),
		}

	@staticmethod
	def _get_callback_query_attributes(callback_query: CallbackQuery) -> dict[str, object]:
		attributes: dict[str, object] = {
			"callback_id": callback_query.id,
			"user_id": callback_query.from_user.id,
			"has_data": callback_query.data is not None,
		}
		if callback_query.message is not None:
			attributes["chat_id"] = callback_query.message.chat.id
			attributes["message_id"] = callback_query.message.message_id
		return attributes

	@staticmethod
	def _get_inline_query_attributes(inline_query: InlineQuery) -> dict[str, object]:
		return {
			"query_id": inline_query.id,
			"user_id": inline_query.from_user.id,
			"chat_type": inline_query.chat_type,
			"query_length": len(inline_query.query),
		}

	@staticmethod
	def _get_pre_checkout_query_attributes(
		pre_checkout_query: PreCheckoutQuery,
	) -> dict[str, object]:
		return {
			"query_id": pre_checkout_query.id,
			"user_id": pre_checkout_query.from_user.id,
			"currency": pre_checkout_query.currency,
			"amount": pre_checkout_query.total_amount,
		}

	@staticmethod
	def _get_chat_member_attributes(chat_member: ChatMemberUpdated) -> dict[str, object]:
		return {
			"chat_id": chat_member.chat.id,
			"user_id": chat_member.from_user.id,
			"old_status": chat_member.old_chat_member.status,
			"new_status": chat_member.new_chat_member.status,
		}
