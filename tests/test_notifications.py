from __future__ import annotations

import json
import unittest
from collections.abc import Mapping
from dataclasses import dataclass

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

	async def send_text(self, chat_id: str, text: str) -> None:
		self._events.append(f"telegram:{chat_id}:{text}")


class RejectingDelivery:
	async def send_text(self, chat_id: str, text: str) -> None:
		del chat_id, text
		raise NotificationRejectedError


class RecordingBot:
	def __init__(self) -> None:
		self.messages: list[tuple[str, str, object]] = []

	async def send_message(
		self, *, chat_id: str, text: str, parse_mode: object = MISSING_PARSE_MODE
	) -> None:
		self.messages.append((chat_id, text, parse_mode))


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

	async def test_splits_long_text_without_losing_characters(self) -> None:
		bot = RecordingBot()
		delivery = TelegramNotificationDelivery(bot)  # type: ignore[arg-type]
		text = "A" * (TELEGRAM_MESSAGE_LIMIT * 2 + 1)

		await delivery.send_text("123", text)

		self.assertEqual("".join(message[1] for message in bot.messages), text)
		self.assertTrue(all(len(message[1]) <= TELEGRAM_MESSAGE_LIMIT for message in bot.messages))
		self.assertTrue(all(message[2] is None for message in bot.messages))


class NotificationConsumerTests(unittest.IsolatedAsyncioTestCase):
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
				"telegram:123:Напоминание:\nBuy",
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
