from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, ErrorEvent, Message

USER_ERROR_MESSAGE = "Что-то пошло не так. Пожалуйста, попробуйте ещё раз позже."

router = Router(name=__name__)
logger = logging.getLogger(__name__)


@router.error(F.update.message.as_("message"))
async def handle_message_error(event: ErrorEvent, message: Message) -> None:
	_log_unhandled_error(event)

	try:
		await message.answer(USER_ERROR_MESSAGE)
	except TelegramAPIError:
		logger.warning(
			"Could not send message error response: chat_id=%s update_id=%s",
			message.chat.id,
			event.update.update_id,
			exc_info=True,
		)


@router.error(F.update.callback_query.as_("callback_query"))
async def handle_callback_query_error(
	event: ErrorEvent, callback_query: CallbackQuery, bot: Bot
) -> None:
	_log_unhandled_error(event)

	try:
		await callback_query.answer(USER_ERROR_MESSAGE, show_alert=True)
	except TelegramAPIError:
		logger.warning(
			"Could not send callback error response: callback_id=%s update_id=%s",
			callback_query.id,
			event.update.update_id,
			exc_info=True,
		)
		await _send_error_message(event, bot)


@router.error()
async def handle_other_error(event: ErrorEvent, bot: Bot) -> None:
	_log_unhandled_error(event)
	await _send_error_message(event, bot)


def _log_unhandled_error(event: ErrorEvent) -> None:
	exception = event.exception
	logger.error(
		"Unhandled bot error: update_id=%s exception_type=%s",
		event.update.update_id,
		type(exception).__name__,
		exc_info=(type(exception), exception, exception.__traceback__),
	)


async def _send_error_message(event: ErrorEvent, bot: Bot) -> None:
	recipient_chat_id = _get_recipient_chat_id(event)
	if recipient_chat_id is None:
		logger.warning("Could not notify user about error: update_id=%s", event.update.update_id)
		return

	try:
		await bot.send_message(chat_id=recipient_chat_id, text=USER_ERROR_MESSAGE)
	except TelegramAPIError:
		logger.warning(
			"Could not send error message: chat_id=%s update_id=%s",
			recipient_chat_id,
			event.update.update_id,
			exc_info=True,
		)


def _get_recipient_chat_id(event: ErrorEvent) -> int | None:
	update_event = event.update.event
	chat = getattr(update_event, "chat", None)
	if chat is not None:
		return chat.id

	message = getattr(update_event, "message", None)
	if message is not None:
		return message.chat.id

	from_user = getattr(update_event, "from_user", None)
	if from_user is not None:
		return from_user.id

	user = getattr(update_event, "user", None)
	if user is not None:
		return user.id

	return None
