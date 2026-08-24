from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, ClassVar

from pydantic import ValidationError
from redis.exceptions import RedisError

from viatradetgbot.notifications.contracts import (
	NotificationConsumerSettings,
	NotificationStoreProtocol,
)
from viatradetgbot.notifications.delivery import NotificationRejectedError
from viatradetgbot.notifications.handlers import NotificationHandler, NotificationPayloadError
from viatradetgbot.notifications.models import NotificationEnvelope

if TYPE_CHECKING:
	from collections.abc import Mapping

	from viatradetgbot.notifications.delivery import NotificationDelivery


class InvalidStreamMessageError(ValueError):
	"""A Redis Stream entry does not contain the declared message field."""


class NotificationConsumer:
	RETRY_DELAY_SECONDS: ClassVar[float] = 5

	def __init__(
		self,
		store: NotificationStoreProtocol,
		settings: NotificationConsumerSettings,
		delivery: NotificationDelivery,
		handlers: Mapping[str, NotificationHandler],
	) -> None:
		self._store = store
		self._settings = settings
		self._delivery = delivery
		self._handlers = handlers
		self._logger = logging.getLogger(self.__class__.__name__)
		self._stopping = asyncio.Event()
		self._is_started = False
		self._next_recovery_at = 0.0

	async def start(self) -> None:
		if self._is_started:
			return

		while not self._stopping.is_set():
			try:
				await self._store.ensure_consumer_group()
			except asyncio.CancelledError:
				raise
			except RedisError:
				self._logger.exception("Could not initialize Redis consumer group; retrying")
				await self._wait_before_retry()
			else:
				self._is_started = True
				self._logger.info(
					"Redis consumer initialized: stream=%s group=%s consumer=%s",
					self._settings.notification_stream,
					self._settings.notification_consumer_group,
					self._settings.notification_consumer_name,
				)
				return

	async def run(self) -> None:
		await self.start()

		while not self._stopping.is_set():
			try:
				await self._recover_pending_if_due()
				for message in await self._store.read_new_messages():
					if self._stopping.is_set():
						return
					await self.process_message(*message)
			except asyncio.CancelledError:
				raise
			except RedisError:
				self._logger.exception("Redis notification processing failed; retrying")
				await self._wait_before_retry()
			except Exception:
				self._logger.exception("Unexpected notification consumer error; retrying")
				await self._wait_before_retry()

	async def stop(self) -> None:
		self._stopping.set()

	async def _recover_pending_if_due(self) -> None:
		if time.monotonic() < self._next_recovery_at:
			return

		self._next_recovery_at = (
			time.monotonic() + self._settings.notification_recovery_interval_seconds
		)
		start_id = "0-0"
		while not self._stopping.is_set():
			next_id, messages = await self._store.claim_pending_messages(start_id)
			for message_id, fields in messages:
				self._logger.info("Recovered pending Redis message: message_id=%s", message_id)
				await self.process_message(message_id, fields)
			if next_id == "0-0":
				return
			start_id = next_id

	async def process_message(self, message_id: str, fields: Mapping[str, str]) -> None:
		"""Deliver and acknowledge one notification stream message."""
		try:
			notification = NotificationEnvelope.model_validate_json(
				self._get_notification_message(fields)
			)
		except (ValidationError, ValueError) as exception:
			await self._store.dead_letter_and_ack(message_id, fields, "invalid_envelope", exception)
			return

		lock = await self._store.acquire_delivery_lock(notification.notification_id)
		if lock is None:
			return

		try:
			handler = self._handlers.get(notification.type)
			if handler is None:
				await self._store.dead_letter_and_ack(message_id, fields, "unsupported_type", None)
				return

			if await self._store.is_sent_to_telegram(notification.notification_id):
				self._logger.info(
					"Telegram notification was already sent; retrying backend confirmation: "
					"notification_id=%s message_id=%s",
					notification.notification_id,
					message_id,
				)
			else:
				await handler.deliver(notification, self._delivery)
				await self._store.mark_sent_to_telegram(notification.notification_id)

			await handler.confirm_delivery(notification)
			await self._store.ack(message_id)
			self._logger.info(
				"Confirmed Telegram notification delivery: notification_id=%s message_id=%s",
				notification.notification_id,
				message_id,
			)
		except NotificationPayloadError as exception:
			await self._store.dead_letter_and_ack(message_id, fields, "invalid_payload", exception)
		except NotificationRejectedError as exception:
			await self._store.dead_letter_and_ack(
				message_id, fields, "telegram_rejected", exception
			)
		except asyncio.CancelledError:
			raise
		except Exception:
			self._logger.exception("Notification delivery failed: message_id=%s", message_id)
		finally:
			await self._store.release_delivery_lock(*lock)

	@staticmethod
	def _get_notification_message(fields: Mapping[str, str]) -> str:
		if set(fields) != {"message"}:
			raise InvalidStreamMessageError
		return fields["message"]

	async def _wait_before_retry(self) -> None:
		try:
			await asyncio.wait_for(self._stopping.wait(), timeout=self.RETRY_DELAY_SECONDS)
		except TimeoutError:
			return
