from __future__ import annotations

import asyncio
import json
import unittest
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.methods import SendMessage
from aiogram.types import LinkPreviewOptions, MessageEntity
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from pydantic.alias_generators import to_camel
from redis.exceptions import RedisError

from viatradetgbot.bot.notification_delivery import TelegramNotificationDelivery
from viatradetgbot.notifications.consumer import NotificationConsumer
from viatradetgbot.notifications.contracts import StreamClaimRequest, StreamClaimResponse
from viatradetgbot.notifications.delivery import NotificationRejectedError
from viatradetgbot.notifications.handlers import ReminderNotificationHandler
from viatradetgbot.notifications.store import NotificationStore

type ReadResponse = list[tuple[str, list[tuple[str, dict[str, str]]]]]

TELEGRAM_MESSAGE_LIMIT = 4096
MISSING_PARSE_MODE = object()
LAST_CHUNK_NUMBER = 2


class LegacyReminderPayload(BaseModel):
	"""Reminder payload layout before instrumentId was introduced."""

	model_config = ConfigDict(alias_generator=to_camel)
	reminder_id: int = Field(ge=-(2**31), le=2**31 - 1)
	text: str
	remind_at: datetime
	instrument_ticker: str | None = None


class UnexpectedCallError(AssertionError):
	"""A test double received an operation that the test does not exercise."""


@dataclass(frozen=True)
class NotificationTestSettings:
	notification_stream: str = "telegram:notifications"
	notification_consumer_group: str = "bot"
	notification_consumer_name: str = "worker-1"
	notification_read_count: int = 10
	notification_read_block_ms: int = 5000
	notification_claim_idle_ms: int = 60000
	notification_delivery_lock_ttl_seconds: int = 300
	notification_recovery_interval_seconds: int = 30
	notification_deduplication_ttl_seconds: int = 604800


def _stream_message(**overrides: object) -> dict[str, str]:
	message = {
		"notificationId": "notification-1",
		"userId": 42,
		"chatId": "123",
		"payload": {
			"reminderId": 7,
			"text": "Buy",
			"remindAt": "2026-08-23T00:00:00Z",
		},
		"createdAt": "2026-08-23T00:00:00Z",
		"type": "reminder",
		"schemaVersion": 1,
	}
	message.update(overrides)
	return {"message": json.dumps(message)}


def _backend_stream_message(**overrides: str) -> dict[str, str]:
	fields = {
		"notification_id": "reminder:7",
		"type": "reminder",
		"user_id": "42",
		"chat_id": "123",
		"payload": json.dumps(
			{
				"reminderId": 7,
				"text": "Buy",
				"remindAt": "2026-10-10T14:25:00Z",
				"instrumentTicker": "AAPL",
			}
		),
		"created_at": "2026-10-10T14:25:26.1490000+00:00",
	}
	fields.update(overrides)
	return fields


class FakeRedis:
	def __init__(self) -> None:
		self.xreadgroup_kwargs: dict[str, object] | None = None

	async def xreadgroup(self, **kwargs: object) -> ReadResponse:
		self.xreadgroup_kwargs = kwargs
		return [("telegram:notifications", [("1-0", {"message": "value"})])]

	async def xgroup_create(
		self,
		*,
		name: str,
		groupname: str,
		start_id: str,
		mkstream: bool,
	) -> bool:
		del name, groupname, start_id, mkstream
		raise UnexpectedCallError

	async def xautoclaim(self, request: StreamClaimRequest) -> StreamClaimResponse:
		del request
		raise UnexpectedCallError

	async def exists(self, key: str) -> int:
		del key
		raise UnexpectedCallError

	async def set(self, key: str, value: str, *, nx: bool = False, ex: int) -> bool | None:
		del key, value, nx, ex
		raise UnexpectedCallError

	async def xadd(self, name: str, fields: Mapping[str, str]) -> str:
		del name, fields
		raise UnexpectedCallError

	async def xack(self, name: str, groupname: str, message_id: str) -> int:
		del name, groupname, message_id
		raise UnexpectedCallError

	async def eval(self, script: str, numkeys: int, key: str, value: str) -> int:
		del script, numkeys, key, value
		raise UnexpectedCallError


class FakeStore:
	def __init__(self) -> None:
		self.is_sent = False
		self.events: list[str] = []

	async def acquire_delivery_lock(self, notification_id: str) -> tuple[str, str]:
		self.events.append(f"lock:{notification_id}")
		return "lock-key", "lock-value"

	async def is_sent_to_telegram(self, notification_id: str) -> bool:
		self.events.append(f"dedup:{notification_id}")
		return self.is_sent

	async def mark_sent_to_telegram(self, notification_id: str) -> None:
		self.events.append(f"sent:{notification_id}")
		self.is_sent = True

	async def ack(self, message_id: str) -> None:
		self.events.append(f"ack:{message_id}")

	async def release_delivery_lock(self, lock_key: str, lock_value: str) -> None:
		self.events.append(f"unlock:{lock_key}:{lock_value}")

	async def ensure_consumer_group(self) -> None:
		raise UnexpectedCallError

	async def read_new_messages(self) -> list[tuple[str, dict[str, str]]]:
		raise UnexpectedCallError

	async def claim_pending_messages(
		self, start_id: str
	) -> tuple[str, list[tuple[str, dict[str, str]]]]:
		del start_id
		raise UnexpectedCallError

	async def dead_letter_and_ack(
		self,
		message_id: str,
		fields: Mapping[str, str],
		reason: str,
		exception: Exception | None,
	) -> None:
		del fields, exception
		self.events.append(f"dead-letter:{message_id}:{reason}")


class FlakyStartupStore(FakeStore):
	def __init__(self) -> None:
		super().__init__()
		self.initialize_attempts = 0

	async def ensure_consumer_group(self) -> None:
		self.initialize_attempts += 1
		if self.initialize_attempts == 1:
			raise RedisError


class FakeDelivery:
	def __init__(self, events: list[str]) -> None:
		self._events = events
		self.instrument_urls: list[str | None] = []
		self.headings: list[str | None] = []
		self.instrument_tickers: list[str | None] = []
		self.reminder_times: list[datetime | None] = []

	async def send_text(  # noqa: PLR0913 — mirrors the notification delivery contract.
		self,
		chat_id: str,
		text: str,
		*,
		heading: str | None = None,
		instrument_ticker: str | None = None,
		instrument_url: str | None = None,
		remind_at: datetime | None = None,
	) -> None:
		self._events.append(f"telegram:{chat_id}:{text}")
		self.instrument_urls.append(instrument_url)
		self.headings.append(heading)
		self.instrument_tickers.append(instrument_ticker)
		self.reminder_times.append(remind_at)


class RejectingDelivery:
	async def send_text(  # noqa: PLR0913 — mirrors the notification delivery contract.
		self,
		chat_id: str,
		text: str,
		*,
		heading: str | None = None,
		instrument_ticker: str | None = None,
		instrument_url: str | None = None,
		remind_at: datetime | None = None,
	) -> None:
		del chat_id, text, heading, instrument_ticker, instrument_url, remind_at
		raise NotificationRejectedError


class RecordingBot:
	def __init__(self, events: list[str] | None = None) -> None:
		self.messages: list[tuple[str, str, object]] = []
		self.markups: list[object] = []
		self.entities: list[list[MessageEntity]] = []
		self.previews: list[LinkPreviewOptions | None] = []
		self._events = events

	async def send_message(  # noqa: PLR0913 — mirrors the Telegram API arguments under test.
		self,
		*,
		chat_id: str,
		text: str,
		parse_mode: object = MISSING_PARSE_MODE,
		reply_markup: object = None,
		entities: list[MessageEntity] | None = None,
		link_preview_options: LinkPreviewOptions | None = None,
	) -> None:
		self.messages.append((chat_id, text, parse_mode))
		self.markups.append(reply_markup)
		self.entities.append(entities or [])
		self.previews.append(link_preview_options)
		if self._events is not None:
			has_link = any(entity.type == "text_link" for entity in entities or [])
			self._events.append(f"telegram-chunk:{len(self.messages)}:{has_link}")


class FakeConfirmation:
	def __init__(self, events: list[str]) -> None:
		self._events = events

	async def confirm_reminder_delivery(self, reminder_id: int, user_id: int) -> None:
		self._events.append(f"confirm:{reminder_id}:{user_id}")


class NotificationStoreTests(unittest.IsolatedAsyncioTestCase):
	async def test_reads_new_messages_with_blocking_consumer_group(self) -> None:
		redis = FakeRedis()
		settings = NotificationTestSettings()
		store = NotificationStore(redis, settings)

		messages = await store.read_new_messages()

		self.assertEqual(messages, [("1-0", {"message": "value"})])
		self.assertEqual(
			redis.xreadgroup_kwargs,
			{
				"groupname": "bot",
				"consumername": "worker-1",
				"streams": {"telegram:notifications": ">"},
				"count": 10,
				"block": 5000,
			},
		)


class TelegramNotificationDeliveryTests(unittest.IsolatedAsyncioTestCase):
	async def test_sends_arbitrary_text_without_html_parsing(self) -> None:
		bot = RecordingBot()
		delivery = TelegramNotificationDelivery(bot)  # type: ignore[arg-type]

		await delivery.send_text("123", "Цена < 100 & растёт")

		self.assertEqual(bot.messages, [("123", "Цена < 100 & растёт", None)])
		self.assertEqual(bot.markups, [None])

	async def test_splits_long_text_without_losing_characters(self) -> None:
		bot = RecordingBot()
		delivery = TelegramNotificationDelivery(bot)  # type: ignore[arg-type]
		text = "A" * (TELEGRAM_MESSAGE_LIMIT * 2 + 1)

		await delivery.send_text("123", text)

		self.assertEqual("".join(message[1] for message in bot.messages), text)
		self.assertTrue(all(len(message[1]) <= TELEGRAM_MESSAGE_LIMIT for message in bot.messages))
		self.assertTrue(all(message[2] is None for message in bot.messages))
		self.assertTrue(all(markup is None for markup in bot.markups))

	async def test_links_only_ticker_and_formats_reminder_without_parsing_body(self) -> None:
		for text in (
			"Цена < 100 & растёт",
			"Цена < 100 & растёт\n" * 600,
			"  Купить\r\n\n\tпри   цене < 100  ",
			"A" * 8193,
		):
			with self.subTest(length=len(text)):
				bot = RecordingBot()
				delivery = TelegramNotificationDelivery(bot)  # type: ignore[arg-type]
				await delivery.send_text(
					"123",
					text,
					heading="Напоминание",
					instrument_ticker="AAPL<&",
					instrument_url="https://example.test/viatrade/stocks/123",
				)
				self.assertEqual(
					"".join(message[1] for message in bot.messages),
					f"Напоминание: AAPL<&\n{text}",
				)
				self.assertTrue(all(0 < len(m[1]) <= TELEGRAM_MESSAGE_LIMIT for m in bot.messages))
				self.assertTrue(all(m[2] is None for m in bot.messages))
				self.assertTrue(all(markup is None for markup in bot.markups))
				self.assertEqual(
					[e.model_dump(exclude_none=True) for e in bot.entities[0]],
					[
						{"type": "bold", "offset": 0, "length": 11},
						{"type": "bold", "offset": 13, "length": 6},
						{
							"type": "text_link",
							"offset": 13,
							"length": 6,
							"url": "https://example.test/viatrade/stocks/123",
						},
					],
				)
				self.assertTrue(all(not entities for entities in bot.entities[1:]))
				self.assertTrue(all(p is not None and p.is_disabled for p in bot.previews))

	async def test_preserves_formatting_without_link_or_ticker(self) -> None:
		for ticker, url, label in (
			("AAPL", None, "AAPL"),
			(None, "https://example.test/stocks/123", "Инструмент"),
			(None, None, None),
		):
			with self.subTest(ticker=ticker, url=url):
				bot = RecordingBot()
				await TelegramNotificationDelivery(bot).send_text(  # type: ignore[arg-type]
					"123",
					"Buy < 100 & hold",
					heading="Напоминание",
					instrument_ticker=ticker,
					instrument_url=url,
				)
				prefix = f"Напоминание: {label}\n" if label else "Напоминание\n"
				self.assertEqual(bot.messages[0][1], f"{prefix}Buy < 100 & hold")
				self.assertEqual(
					sum(e.type == "text_link" for e in bot.entities[0]), int(url is not None)
				)
				self.assertTrue(all(markup is None for markup in bot.markups))

	async def test_entity_offsets_use_utf16_and_survive_chunk_boundaries(self) -> None:
		for ticker in ("𐐀ABC", "𐐀" * 4200):
			with self.subTest(length=len(ticker)):
				bot = RecordingBot()
				await TelegramNotificationDelivery(bot).send_text(  # type: ignore[arg-type]
					"123",
					"Body < &",
					heading="Напоминание",
					instrument_ticker=ticker,
					instrument_url="https://example.test/stocks/123",
				)
				linked_parts = []
				for message, entities in zip(bot.messages, bot.entities, strict=True):
					encoded = message[1].encode("utf-16-le")
					for entity in entities:
						self.assertLessEqual((entity.offset + entity.length) * 2, len(encoded))
						if entity.type == "text_link":
							linked_parts.append(
								encoded[
									entity.offset * 2 : (entity.offset + entity.length) * 2
								].decode("utf-16-le")
							)
				self.assertEqual("".join(linked_parts), ticker)
				self.assertEqual(
					"".join(m[1] for m in bot.messages), f"Напоминание: {ticker}\nBody < &"
				)

	async def test_displays_scheduled_time_in_moscow_without_changing_body(self) -> None:
		for timestamp, expected in (
			("2026-10-11T12:00:00Z", "11.10.2026, 15:00"),
			("2026-10-11T15:00:00+03:00", "11.10.2026, 15:00"),
			("2026-10-11T09:00:00-03:00", "11.10.2026, 15:00"),
			("2026-12-31T22:45:00Z", "01.01.2027, 01:45"),
			("2026-10-11T12:00:00", "11.10.2026, 15:00"),
		):
			for ticker in ("𐐀ABC", None):
				with self.subTest(timestamp=timestamp, ticker=ticker):
					bot = RecordingBot()
					body = "Купить < 100 & держать\n  Второй пункт"
					await TelegramNotificationDelivery(bot).send_text(  # type: ignore[arg-type]
						"123",
						body,
						heading="Напоминание",
						instrument_ticker=ticker,
						instrument_url="https://example.test/stocks/123" if ticker else None,
						remind_at=datetime.fromisoformat(timestamp),
					)
					schedule = f"Запланировано: {expected} МСК"
					heading = f"Напоминание: {ticker}" if ticker else "Напоминание"
					self.assertEqual(bot.messages[0][1], f"{heading}\n{schedule}\n{body}")
					italic = [e for e in bot.entities[0] if e.type == "italic"]
					self.assertEqual(len(italic), 1)
					encoded = bot.messages[0][1].encode("utf-16-le")
					entity = italic[0]
					self.assertEqual(
						encoded[entity.offset * 2 : (entity.offset + entity.length) * 2].decode(
							"utf-16-le"
						),
						schedule,
					)


class FailingLastChunkBot(RecordingBot):
	def __init__(self, exception: BaseException) -> None:
		super().__init__()
		self._exception = exception

	async def send_message(self, **kwargs) -> None:
		await super().send_message(**kwargs)
		if len(self.messages) == LAST_CHUNK_NUMBER:
			raise self._exception


class InvalidInstrumentLinkBot(RecordingBot):
	def __init__(
		self,
		events: list[str],
		fallback_error: BaseException | None = None,
		*,
		message: str = "Bad Request: can't parse entities: Wrong HTTP URL",
	) -> None:
		super().__init__(events)
		self.attempts: list[tuple[str, list[MessageEntity]]] = []
		self._fallback_error = fallback_error
		self._message = message

	async def send_message(self, **kwargs) -> None:
		entities = kwargs.get("entities") or []
		self.attempts.append((kwargs["text"], entities))
		if any(entity.type == "text_link" for entity in entities):
			raise TelegramBadRequest(
				method=SendMessage(**kwargs),
				message=self._message,
			)
		if self._fallback_error is not None and any(
			entity.type == "text_link" for _, attempted in self.attempts for entity in attempted
		):
			raise self._fallback_error
		await super().send_message(**kwargs)


class FlakyConfirmation(FakeConfirmation):
	def __init__(self, events: list[str]) -> None:
		super().__init__(events)
		self.attempts = 0

	async def confirm_reminder_delivery(self, reminder_id: int, user_id: int) -> None:
		await super().confirm_reminder_delivery(reminder_id, user_id)
		self.attempts += 1
		if self.attempts == 1:
			raise ConnectionError


class ReminderLinkTests(unittest.IsolatedAsyncioTestCase):
	async def test_only_url_rejection_retries_linked_fragment(self) -> None:
		for message, retries in (
			("Bad Request: can't parse entities: Wrong HTTP URL", True),
			("Bad Request: can't parse entities: invalid URL", True),
			("Bad Request: can't parse entities: unsupported URL protocol", True),
			("Bad Request: chat not found", False),
			("Bad Request: can't parse entities: invalid offset", False),
		):
			with self.subTest(message=message):
				bot = InvalidInstrumentLinkBot([], message=message)
				delivery = TelegramNotificationDelivery(bot)  # type: ignore[arg-type]
				if retries:
					with self.assertLogs(
						"viatradetgbot.bot.notification_delivery", level="WARNING"
					):
						await delivery.send_text(
							"123",
							"Buy",
							instrument_ticker="AAPL",
							instrument_url="https://example.test/stocks/123",
						)
					self.assertEqual(len(bot.attempts), 2)
					self.assertEqual([e.type for e in bot.entities[0]], ["bold"])
				else:
					with self.assertRaises(NotificationRejectedError):  # noqa: PT027
						await delivery.send_text(
							"123",
							"Buy",
							instrument_ticker="AAPL",
							instrument_url="https://example.test/stocks/123",
						)
					self.assertEqual(len(bot.attempts), 1)
					self.assertFalse(bot.messages)

	async def test_invalid_instrument_link_delivers_text_instead_of_dead_lettering(self) -> None:
		for text in ("Цена < 100 & растёт", "A" * TELEGRAM_MESSAGE_LIMIT):
			with self.subTest(length=len(text)):
				store = FakeStore()
				bot = InvalidInstrumentLinkBot(store.events)
				consumer = NotificationConsumer(
					store,
					NotificationTestSettings(),
					TelegramNotificationDelivery(bot),  # type: ignore[arg-type]
					{
						"reminder": ReminderNotificationHandler(
							FakeConfirmation(store.events),
							web_base_url=HttpUrl("http://localhost:5173"),
						)
					},
				)
				with self.assertLogs(
					"viatradetgbot.bot.notification_delivery", level="WARNING"
				) as logs:
					await consumer.process_message(
						"1-0",
						_stream_message(
							payload={
								"reminderId": 7,
								"text": text,
								"remindAt": "2026-10-11T12:00:00Z",
								"instrumentId": 1,
							}
						),
					)
				self.assertEqual(len(logs.output), 1)
				self.assertNotIn("localhost", logs.output[0])
				self.assertNotIn(text, logs.output[0])
				self.assertEqual(
					"".join(message[1] for message in bot.messages),
					f"Напоминание: Инструмент\nЗапланировано: 11.10.2026, 15:00 МСК\n{text}",
				)
				self.assertTrue(all(message[2] is None for message in bot.messages))
				self.assertTrue(all(markup is None for markup in bot.markups))
				self.assertEqual(len(bot.attempts), len(bot.messages) + 1)
				self.assertEqual(bot.attempts[0][0], bot.attempts[1][0])
				self.assertEqual(
					store.events[-4:],
					[
						"sent:notification-1",
						"confirm:7:42",
						"ack:1-0",
						"unlock:lock-key:lock-value",
					],
				)

	async def test_failed_text_fallback_preserves_error_classification(self) -> None:
		method = SendMessage(chat_id="123", text="last chunk")
		for exception, permanent in (
			(ConnectionError(), False),
			(TelegramBadRequest(method=method, message="chat not found"), True),
			(TelegramForbiddenError(method=method, message="blocked"), True),
			(asyncio.CancelledError(), False),
		):
			with self.subTest(exception=type(exception)):
				store = FakeStore()
				bot = InvalidInstrumentLinkBot(store.events, exception)
				consumer = NotificationConsumer(
					store,
					NotificationTestSettings(),
					TelegramNotificationDelivery(bot),  # type: ignore[arg-type]
					{
						"reminder": ReminderNotificationHandler(
							FakeConfirmation(store.events),
							web_base_url=HttpUrl("http://localhost:5173"),
						)
					},
				)
				fields = _stream_message(
					payload={
						"reminderId": 7,
						"text": "A" * TELEGRAM_MESSAGE_LIMIT,
						"remindAt": "2026-10-11T12:00:00Z",
						"instrumentId": 1,
					}
				)
				with self.assertLogs(level="WARNING"):
					if isinstance(exception, asyncio.CancelledError):
						with self.assertRaises(asyncio.CancelledError):  # noqa: PT027
							await consumer.process_message("1-0", fields)
					else:
						await consumer.process_message("1-0", fields)
				self.assertFalse(store.is_sent)
				self.assertEqual(len(bot.messages), 0)
				self.assertEqual(len(bot.attempts), 2)
				self.assertEqual(
					store.events,
					[
						"lock:notification-1",
						"dedup:notification-1",
						*(["dead-letter:1-0:telegram_rejected"] if permanent else []),
						"unlock:lock-key:lock-value",
					],
				)

	async def test_builds_links_and_preserves_fallback_and_arbitrary_text(self) -> None:
		for base, payload_fields, expected in (
			("https://example.test", {"instrumentId": 123}, "https://example.test/stocks/123"),
			("https://example.test/", {"instrumentId": 123}, "https://example.test/stocks/123"),
			(
				"https://example.test/viatrade/",
				{"instrumentId": 123},
				"https://example.test/viatrade/stocks/123",
			),
			("http://localhost:5173", {"instrumentId": 123}, "http://localhost:5173/stocks/123"),
			(
				"https://example.test",
				{"instrumentId": 2147483647},
				"https://example.test/stocks/2147483647",
			),
			(None, {"instrumentId": 123}, None),
			("https://example.test", {}, None),
			("https://example.test", {"instrumentId": None}, None),
		):
			for ticker in (None, "https://evil.test/?x=<html>&"):
				with self.subTest(base=base, payload=payload_fields, ticker=ticker):
					store = FakeStore()
					delivery = FakeDelivery(store.events)
					handler = ReminderNotificationHandler(
						FakeConfirmation(store.events), web_base_url=HttpUrl(base) if base else None
					)
					consumer = NotificationConsumer(
						store, NotificationTestSettings(), delivery, {"reminder": handler}
					)
					payload = {
						"reminderId": 42,
						"text": "Цена < 100 & https://evil.test/\nBuy",
						"remindAt": "2026-10-11T12:00:00Z",
						"instrumentTicker": ticker,
						**payload_fields,
					}
					await consumer.process_message(
						"1-0", _stream_message(userId=7, payload=payload)
					)
					self.assertEqual(delivery.instrument_urls, [expected])
					self.assertEqual(delivery.headings, ["Напоминание"])
					self.assertEqual(delivery.instrument_tickers, [ticker])
					self.assertEqual(
						delivery.reminder_times, [datetime.fromisoformat("2026-10-11T12:00:00Z")]
					)
					self.assertEqual(
						store.events,
						[
							"lock:notification-1",
							"dedup:notification-1",
							f"telegram:123:{payload['text']}",
							"sent:notification-1",
							"confirm:42:7",
							"ack:1-0",
							"unlock:lock-key:lock-value",
						],
					)

	async def test_invalid_instrument_ids_use_existing_dlq_policy(self) -> None:
		for instrument_id in (0, -1, 2**31, True, False, "123", 123.0, 1.5, [], {}):
			for stream_format in ("backend", "envelope"):
				with self.subTest(instrument_id=instrument_id, stream_format=stream_format):
					store = FakeStore()
					consumer = NotificationConsumer(
						store,
						NotificationTestSettings(),
						FakeDelivery(store.events),
						{"reminder": ReminderNotificationHandler(FakeConfirmation(store.events))},
					)
					payload = json.loads(_backend_stream_message()["payload"])
					payload["instrumentId"] = instrument_id
					fields = (
						_backend_stream_message(payload=json.dumps(payload))
						if stream_format == "backend"
						else _stream_message(payload=payload)
					)
					await consumer.process_message("1-0", fields)
					notification_id = (
						"reminder:7" if stream_format == "backend" else "notification-1"
					)
					self.assertEqual(
						store.events[1:],
						[
							f"dedup:{notification_id}",
							"dead-letter:1-0:invalid_payload",
							"unlock:lock-key:lock-value",
						],
					)

	async def test_last_chunk_errors_do_not_mark_sent_confirm_or_ack(self) -> None:
		method = SendMessage(chat_id="123", text="last chunk")
		for exception, permanent in (
			(ConnectionError(), False),
			(TelegramBadRequest(method=method, message="rejected"), True),
			(TelegramForbiddenError(method=method, message="blocked"), True),
			(asyncio.CancelledError(), False),
		):
			with self.subTest(exception=type(exception)):
				store = FakeStore()
				bot = FailingLastChunkBot(exception)
				consumer = NotificationConsumer(
					store,
					NotificationTestSettings(),
					TelegramNotificationDelivery(bot),  # type: ignore[arg-type]
					{
						"reminder": ReminderNotificationHandler(
							FakeConfirmation(store.events),
							web_base_url=HttpUrl("https://example.test"),
						)
					},
				)
				fields = _stream_message(
					payload={
						"reminderId": 7,
						"text": "A" * 4096,
						"remindAt": "2026-10-11T12:00:00Z",
						"instrumentId": 123,
					}
				)
				if isinstance(exception, asyncio.CancelledError):
					with self.assertRaises(asyncio.CancelledError):  # noqa: PT027
						await consumer.process_message("1-0", fields)
				elif permanent:
					await consumer.process_message("1-0", fields)
				else:
					with self.assertLogs("NotificationConsumer", level="ERROR"):
						await consumer.process_message("1-0", fields)
				self.assertEqual(
					store.events,
					[
						"lock:notification-1",
						"dedup:notification-1",
						*(["dead-letter:1-0:telegram_rejected"] if permanent else []),
						"unlock:lock-key:lock-value",
					],
				)
				self.assertFalse(store.is_sent)
				self.assertTrue(any(e.type == "text_link" for e in bot.entities[0]))
				self.assertFalse(bot.entities[1])

	async def test_backend_confirmation_retry_does_not_resend_link(self) -> None:
		store = FakeStore()
		bot = RecordingBot(store.events)
		confirmation = FlakyConfirmation(store.events)
		consumer = NotificationConsumer(
			store,
			NotificationTestSettings(),
			TelegramNotificationDelivery(bot),  # type: ignore[arg-type]
			{
				"reminder": ReminderNotificationHandler(
					confirmation, web_base_url=HttpUrl("https://example.test")
				)
			},
		)
		fields = _stream_message(
			payload={
				"reminderId": 42,
				"text": "A" * 4096,
				"remindAt": "2026-10-11T12:00:00Z",
				"instrumentId": 123,
			}
		)
		with self.assertLogs("NotificationConsumer", level="ERROR"):
			await consumer.process_message("1-0", fields)
		self.assertEqual(
			store.events,
			[
				"lock:notification-1",
				"dedup:notification-1",
				"telegram-chunk:1:True",
				"telegram-chunk:2:False",
				"sent:notification-1",
				"confirm:42:42",
				"unlock:lock-key:lock-value",
			],
		)
		await consumer.process_message("1-0", fields)
		self.assertEqual(len(bot.messages), 2)
		self.assertEqual(
			sum(e.type == "text_link" for entities in bot.entities for e in entities), 1
		)
		self.assertEqual(
			store.events[7:],
			[
				"lock:notification-1",
				"dedup:notification-1",
				"confirm:42:42",
				"ack:1-0",
				"unlock:lock-key:lock-value",
			],
		)

	async def test_accepts_actual_csharp_publisher_output_and_legacy_reader(self) -> None:
		fixture = Path(__file__).parent / "fixtures/reminder-stream-entry.json"
		fields = json.loads(fixture.read_text(encoding="utf-8"))
		store = FakeStore()
		bot = RecordingBot()
		consumer = NotificationConsumer(
			store,
			NotificationTestSettings(),
			TelegramNotificationDelivery(bot),  # type: ignore[arg-type]
			{
				"reminder": ReminderNotificationHandler(
					FakeConfirmation(store.events), web_base_url=HttpUrl("https://example.test")
				)
			},
		)
		await consumer.process_message("1-0", fields)
		self.assertEqual(
			bot.messages,
			[
				(
					"987654321",
					"Напоминание: AAPL\nЗапланировано: 11.10.2026, 15:00 МСК\nBuy < 100 & hold",
					None,
				)
			],
		)
		self.assertIn("confirm:42:7", store.events)
		self.assertIn("ack:1-0", store.events)
		links = [e for e in bot.entities[0] if e.type == "text_link"]
		self.assertEqual(len(links), 1)
		self.assertEqual(links[0].url, "https://example.test/stocks/123")
		self.assertEqual(bot.markups, [None])
		legacy = LegacyReminderPayload.model_validate_json(fields["payload"])
		self.assertEqual(legacy.reminder_id, 42)
		self.assertNotIn("instrumentId", legacy.model_dump(by_alias=True))


class NotificationConsumerTests(unittest.IsolatedAsyncioTestCase):
	async def test_delivers_stream_fields_published_by_backend(self) -> None:
		store = FakeStore()
		consumer = NotificationConsumer(
			store=store,
			settings=NotificationTestSettings(),
			delivery=FakeDelivery(store.events),
			handlers={"reminder": ReminderNotificationHandler(FakeConfirmation(store.events))},
		)
		await consumer.process_message("1-0", _backend_stream_message())

		self.assertEqual(
			store.events,
			[
				"lock:reminder:7",
				"dedup:reminder:7",
				"telegram:123:Buy",
				"sent:reminder:7",
				"confirm:7:42",
				"ack:1-0",
				"unlock:lock-key:lock-value",
			],
		)

	async def test_dead_letters_invalid_backend_stream_fields(self) -> None:
		missing_field = _backend_stream_message()
		del missing_field["chat_id"]
		cases = [
			missing_field,
			_backend_stream_message(message=_stream_message()["message"]),
			_backend_stream_message(schema_version="2"),
			_backend_stream_message(payload="not JSON"),
			_backend_stream_message(payload="[]"),
			_backend_stream_message(user_id="invalid"),
			_backend_stream_message(user_id=str(2**31)),
			_backend_stream_message(created_at="invalid"),
			_backend_stream_message(type="unknown"),
		]
		for fields in cases:
			with self.subTest(fields=fields):
				store = FakeStore()
				consumer = NotificationConsumer(
					store=store,
					settings=NotificationTestSettings(),
					delivery=FakeDelivery(store.events),
					handlers={
						"reminder": ReminderNotificationHandler(FakeConfirmation(store.events))
					},
				)

				await consumer.process_message("1-0", fields)

				self.assertEqual(store.events, ["dead-letter:1-0:invalid_envelope"])

	async def test_backend_reminder_validates_payload_and_instrument_ticker(self) -> None:
		cases = [
			({"instrumentTicker": "AAPL"}, "telegram:123:Buy"),
			({"instrumentTicker": None}, "telegram:123:Buy"),
			({}, "telegram:123:Buy"),
			({"reminderId": "invalid"}, "dead-letter:1-0:invalid_payload"),
			({"instrumentTicker": 123}, "dead-letter:1-0:invalid_payload"),
		]
		for overrides, expected_event in cases:
			with self.subTest(overrides=overrides):
				store = FakeStore()
				consumer = NotificationConsumer(
					store=store,
					settings=NotificationTestSettings(),
					delivery=FakeDelivery(store.events),
					handlers={
						"reminder": ReminderNotificationHandler(FakeConfirmation(store.events))
					},
				)
				payload = json.loads(_backend_stream_message()["payload"])
				del payload["instrumentTicker"]
				payload.update(overrides)

				await consumer.process_message(
					"1-0", _backend_stream_message(payload=json.dumps(payload))
				)

				self.assertIn(expected_event, store.events)
				self.assertEqual(store.events[-1], "unlock:lock-key:lock-value")
				if expected_event.startswith("dead-letter:"):
					self.assertFalse(any(event.startswith("telegram:") for event in store.events))
					self.assertNotIn("ack:1-0", store.events)
				else:
					self.assertIn("confirm:7:42", store.events)
					self.assertIn("ack:1-0", store.events)

	async def test_retries_consumer_group_initialization_after_redis_error(self) -> None:
		store = FlakyStartupStore()
		consumer = NotificationConsumer(
			store=store,
			settings=NotificationTestSettings(),
			delivery=FakeDelivery(store.events),
			handlers={},
		)
		original_retry_delay = NotificationConsumer.RETRY_DELAY_SECONDS
		NotificationConsumer.RETRY_DELAY_SECONDS = 0
		try:
			await consumer.start()
		finally:
			NotificationConsumer.RETRY_DELAY_SECONDS = original_retry_delay

		self.assertEqual(store.initialize_attempts, 2)

	async def test_sends_confirms_and_acknowledges_reminder_in_order(self) -> None:
		store = FakeStore()
		confirmation = FakeConfirmation(store.events)
		consumer = NotificationConsumer(
			store=store,
			settings=NotificationTestSettings(),
			delivery=FakeDelivery(store.events),
			handlers={"reminder": ReminderNotificationHandler(confirmation)},
		)

		await consumer.process_message("1-0", _stream_message())

		self.assertEqual(
			store.events,
			[
				"lock:notification-1",
				"dedup:notification-1",
				"telegram:123:Buy",
				"sent:notification-1",
				"confirm:7:42",
				"ack:1-0",
				"unlock:lock-key:lock-value",
			],
		)

	async def test_dead_letters_message_rejected_permanently_by_telegram(self) -> None:
		store = FakeStore()
		consumer = NotificationConsumer(
			store=store,
			settings=NotificationTestSettings(),
			delivery=RejectingDelivery(),
			handlers={"reminder": ReminderNotificationHandler(FakeConfirmation(store.events))},
		)

		await consumer.process_message("1-0", _stream_message())

		self.assertEqual(
			store.events,
			[
				"lock:notification-1",
				"dedup:notification-1",
				"dead-letter:1-0:telegram_rejected",
				"unlock:lock-key:lock-value",
			],
		)

	async def test_dead_letters_nonconforming_stream_entry(self) -> None:
		store = FakeStore()
		consumer = NotificationConsumer(
			store=store,
			settings=NotificationTestSettings(),
			delivery=FakeDelivery(store.events),
			handlers={"reminder": ReminderNotificationHandler(FakeConfirmation(store.events))},
		)

		await consumer.process_message("1-0", {"notificationId": "notification-1"})

		self.assertEqual(store.events, ["dead-letter:1-0:invalid_envelope"])

	async def test_dead_letters_unsupported_schema_version(self) -> None:
		store = FakeStore()
		consumer = NotificationConsumer(
			store=store,
			settings=NotificationTestSettings(),
			delivery=FakeDelivery(store.events),
			handlers={"reminder": ReminderNotificationHandler(FakeConfirmation(store.events))},
		)

		await consumer.process_message("1-0", _stream_message(schemaVersion=2))

		self.assertEqual(store.events, ["dead-letter:1-0:invalid_envelope"])
