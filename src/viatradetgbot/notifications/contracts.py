from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

type StreamMessage = tuple[str, dict[str, str]]
type StreamReadResponse = list[tuple[str, list[StreamMessage]]]
type StreamClaimResponse = tuple[str, list[StreamMessage], list[str]]


@dataclass(frozen=True)
class StreamClaimRequest:
	"""Parameters for claiming idle messages from a Redis Stream."""

	stream: str
	consumer_group: str
	consumer_name: str
	min_idle_time_ms: int
	start_id: str
	count: int


class NotificationStoreSettings(Protocol):
	"""Settings required by the Redis-backed notification store."""

	@property
	def notification_stream(self) -> str: ...

	@property
	def notification_consumer_group(self) -> str: ...

	@property
	def notification_consumer_name(self) -> str: ...

	@property
	def notification_read_block_ms(self) -> int: ...

	@property
	def notification_read_count(self) -> int: ...

	@property
	def notification_claim_idle_ms(self) -> int: ...

	@property
	def notification_delivery_lock_ttl_seconds(self) -> int: ...

	@property
	def notification_deduplication_ttl_seconds(self) -> int: ...


class NotificationConsumerSettings(NotificationStoreSettings, Protocol):
	"""Settings required by the notification-consumer control loop."""

	@property
	def notification_recovery_interval_seconds(self) -> int: ...


class RedisNotificationClient(Protocol):
	"""Redis operations used by the notification store."""

	async def xgroup_create(
		self, *, name: str, groupname: str, start_id: str, mkstream: bool
	) -> bool: ...

	async def xreadgroup(
		self,
		*,
		groupname: str,
		consumername: str,
		streams: dict[str, str],
		count: int,
		block: int,
	) -> StreamReadResponse: ...

	async def xautoclaim(self, request: StreamClaimRequest) -> StreamClaimResponse: ...

	async def exists(self, key: str) -> int: ...

	async def set(
		self, key: str, value: str, *, nx: bool = False, ex: int
	) -> bool | None: ...

	async def xadd(self, name: str, fields: Mapping[str, str]) -> str: ...

	async def xack(self, name: str, groupname: str, message_id: str) -> int: ...

	async def eval(self, script: str, numkeys: int, key: str, value: str) -> int: ...


class NotificationStoreProtocol(Protocol):
	"""Store operations used by the notification consumer."""

	async def ensure_consumer_group(self) -> None: ...

	async def read_new_messages(self) -> list[StreamMessage]: ...

	async def claim_pending_messages(self, start_id: str) -> tuple[str, list[StreamMessage]]: ...

	async def is_sent_to_telegram(self, notification_id: str) -> bool: ...

	async def acquire_delivery_lock(self, notification_id: str) -> tuple[str, str] | None: ...

	async def mark_sent_to_telegram(self, notification_id: str) -> None: ...

	async def dead_letter_and_ack(
		self,
		message_id: str,
		fields: Mapping[str, str],
		reason: str,
		exception: Exception | None,
	) -> None: ...

	async def ack(self, message_id: str) -> None: ...

	async def release_delivery_lock(self, lock_key: str, lock_value: str) -> None: ...
