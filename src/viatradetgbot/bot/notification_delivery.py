from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import LinkPreviewOptions, MessageEntity

from viatradetgbot.notifications.delivery import NotificationRejectedError

if TYPE_CHECKING:
	from aiogram import Bot

TELEGRAM_MESSAGE_LIMIT = 4096
REMINDER_TIMEZONE = timezone(timedelta(hours=3), name="МСК")


class EmptyNotificationTextError(ValueError):
	"""A notification adapter cannot send an empty Telegram message."""


class TelegramNotificationDelivery:
	def __init__(self, bot: Bot) -> None:
		self._bot = bot
		self._logger = logging.getLogger(__name__)

	async def send_text(
		self,
		chat_id: str,
		text: str,
		*,
		heading: str | None = None,
		instrument_ticker: str | None = None,
		instrument_url: str | None = None,
		remind_at: datetime | None = None,
	) -> None:
		text, entities = _format_notification_text(
			text, heading, instrument_ticker, instrument_url, remind_at
		)
		chunks = _split_message_text(text)
		preview = LinkPreviewOptions(is_disabled=True) if entities else None
		start = 0
		try:
			for chunk in chunks:
				end = start + _utf16_length(chunk)
				chunk_entities = _chunk_entities(entities, start, end)
				await self._send_chunk(chat_id, chunk, chunk_entities, preview)
				start = end
		except (TelegramBadRequest, TelegramForbiddenError) as exception:
			raise NotificationRejectedError from exception

	async def _send_chunk(
		self,
		chat_id: str,
		text: str,
		entities: list[MessageEntity],
		preview: LinkPreviewOptions | None,
	) -> None:
		try:
			await self._bot.send_message(
				chat_id=chat_id,
				text=text,
				parse_mode=None,
				entities=entities or None,
				link_preview_options=preview,
			)
		except TelegramBadRequest as exception:
			description = exception.message.lower()
			if not any(entity.type == "text_link" for entity in entities) or not (
				"wrong http url" in description
				or (
					"url" in description
					and "can't parse entities" in description
					and ("invalid" in description or "unsupported" in description)
				)
			):
				raise
			self._logger.warning(
				"Telegram rejected instrument link; sending text without link: chat_id=%s", chat_id
			)
			await self._bot.send_message(
				chat_id=chat_id,
				text=text,
				parse_mode=None,
				entities=[entity for entity in entities if entity.type != "text_link"],
				link_preview_options=preview,
			)


def _utf16_length(text: str) -> int:
	return len(text.encode("utf-16-le")) // 2


def _format_notification_text(
	text: str,
	heading: str | None,
	ticker: str | None,
	url: str | None,
	remind_at: datetime | None,
) -> tuple[str, list[MessageEntity]]:
	parts: list[str] = []
	entities: list[MessageEntity] = []
	if heading:
		parts.append(heading)
		entities.append(MessageEntity(type="bold", offset=0, length=_utf16_length(heading)))
	if ticker or url:
		if parts:
			parts.append(": ")
		label = " ".join((ticker or "Инструмент").split()) or "Инструмент"
		offset = _utf16_length("".join(parts))
		parts.append(label)
		entities.append(MessageEntity(type="bold", offset=offset, length=_utf16_length(label)))
		if url:
			entities.append(
				MessageEntity(type="text_link", offset=offset, length=_utf16_length(label), url=url)
			)
	if remind_at is not None:
		if parts:
			parts.append("\n")
		# Legacy timestamps without an offset follow the backend's UTC storage convention.
		if remind_at.tzinfo is None:
			remind_at = remind_at.replace(tzinfo=UTC)
		local_time = remind_at.astimezone(REMINDER_TIMEZONE)
		schedule = f"Запланировано: {local_time:%d.%m.%Y, %H:%M} МСК"
		offset = _utf16_length("".join(parts))
		parts.append(schedule)
		entities.append(MessageEntity(type="italic", offset=offset, length=_utf16_length(schedule)))
	if parts:
		parts.append("\n")
	parts.append(text)
	return "".join(parts), entities


def _chunk_entities(entities: list[MessageEntity], start: int, end: int) -> list[MessageEntity]:
	result: list[MessageEntity] = []
	for entity in entities:
		entity_start = max(start, entity.offset)
		entity_end = min(end, entity.offset + entity.length)
		if entity_start < entity_end:
			result.append(
				entity.model_copy(
					update={"offset": entity_start - start, "length": entity_end - entity_start}
				)
			)
	return result


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
