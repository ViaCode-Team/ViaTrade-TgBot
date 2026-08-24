from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Final
from uuid import uuid4

from redis.exceptions import ResponseError

from viatradetgbot.notifications.contracts import (
	NotificationStoreSettings,
	RedisNotificationClient,
	StreamClaimRequest,
	StreamMessage,
)

DELIVERED_KEY_PREFIX: Final = "telegram:notifications:delivered:"
LOCK_KEY_PREFIX: Final = "telegram:notifications:delivery-lock:"
DEAD_LETTER_SUFFIX: Final = ":dead-letter"
RELEASE_LOCK_SCRIPT: Final = """
if redis.call('get', KEYS[1]) == ARGV[1] then
	return redis.call('del', KEYS[1])
end
return 0
"""

class NotificationStore:
	def __init__(
		self, redis_client: RedisNotificationClient, settings: NotificationStoreSettings
	) -> None:
		self._redis = redis_client
		self._settings = settings
		self._logger = logging.getLogger(self.__class__.__name__)

	async def ensure_consumer_group(self) -> None:
		try:
			await self._redis.xgroup_create(
				name=self._settings.notification_stream,
				groupname=self._settings.notification_consumer_group,
				start_id="0-0",
				mkstream=True,
			)
		except ResponseError as exception:
			if "BUSYGROUP" not in str(exception):
				raise

	async def read_new_messages(self) -> list[StreamMessage]:
		response = await self._redis.xreadgroup(
			groupname=self._settings.notification_consumer_group,
			consumername=self._settings.notification_consumer_name,
			streams={self._settings.notification_stream: ">"},
			count=self._settings.notification_read_count,
			block=self._settings.notification_read_block_ms,
		)
		return [message for _, messages in response for message in messages]

	async def claim_pending_messages(self, start_id: str) -> tuple[str, list[StreamMessage]]:
		next_id, messages, deleted_ids = await self._redis.xautoclaim(
			StreamClaimRequest(
				stream=self._settings.notification_stream,
				consumer_group=self._settings.notification_consumer_group,
				consumer_name=self._settings.notification_consumer_name,
				min_idle_time_ms=self._settings.notification_claim_idle_ms,
				start_id=start_id,
				count=self._settings.notification_read_count,
			)
		)
		for message_id in deleted_ids:
			self._logger.warning("Removed trimmed pending Redis message: message_id=%s", message_id)
		return next_id, messages

	async def is_sent_to_telegram(self, notification_id: str) -> bool:
		return bool(await self._redis.exists(f"{DELIVERED_KEY_PREFIX}{notification_id}"))

	async def acquire_delivery_lock(self, notification_id: str) -> tuple[str, str] | None:
		lock_key = f"{LOCK_KEY_PREFIX}{notification_id}"
		lock_value = str(uuid4())
		is_locked = await self._redis.set(
			lock_key,
			lock_value,
			nx=True,
			ex=self._settings.notification_delivery_lock_ttl_seconds,
		)
		if not is_locked:
			return None
		return lock_key, lock_value

	async def mark_sent_to_telegram(self, notification_id: str) -> None:
		await self._redis.set(
			f"{DELIVERED_KEY_PREFIX}{notification_id}",
			"1",
			ex=self._settings.notification_deduplication_ttl_seconds,
		)

	async def dead_letter_and_ack(
		self,
		message_id: str,
		fields: Mapping[str, str],
		reason: str,
		exception: Exception | None,
	) -> None:
		self._logger.error(
			"Discarding Redis notification: message_id=%s reason=%s",
			message_id,
			reason,
			exc_info=exception,
		)
		await self._redis.xadd(
			f"{self._settings.notification_stream}{DEAD_LETTER_SUFFIX}",
			{
				**fields,
				"original_message_id": message_id,
				"failure_reason": reason,
			},
		)
		await self.ack(message_id)

	async def ack(self, message_id: str) -> None:
		await self._redis.xack(
			self._settings.notification_stream,
			self._settings.notification_consumer_group,
			message_id,
		)

	async def release_delivery_lock(self, lock_key: str, lock_value: str) -> None:
		await self._redis.eval(RELEASE_LOCK_SCRIPT, 1, lock_key, lock_value)
