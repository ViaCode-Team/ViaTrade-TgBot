from __future__ import annotations

from collections.abc import Awaitable, Mapping
from typing import Any, cast

from redis.asyncio import Redis

from viatradetgbot.notifications.contracts import (
	StreamClaimRequest,
	StreamClaimResponse,
	StreamReadResponse,
)


class RedisNotificationClientAdapter:
	"""Adapts Redis-py's generic async return annotations to notification types."""

	def __init__(self, redis_client: Redis) -> None:
		self._redis = redis_client

	async def xgroup_create(
		self, *, name: str, groupname: str, start_id: str, mkstream: bool
	) -> bool:
		return await cast(
			"Awaitable[bool]",
			self._redis.xgroup_create(
				name=name, groupname=groupname, id=start_id, mkstream=mkstream
			),
		)

	async def xreadgroup(
		self,
		*,
		groupname: str,
		consumername: str,
		streams: dict[str, str],
		count: int,
		block: int,
	) -> StreamReadResponse:
		return await cast(
			"Awaitable[StreamReadResponse]",
			self._redis.xreadgroup(
				groupname=groupname,
				consumername=consumername,
				streams=cast("Any", streams),
				count=count,
				block=block,
			),
		)

	async def xautoclaim(self, request: StreamClaimRequest) -> StreamClaimResponse:
		return await cast(
			"Awaitable[StreamClaimResponse]",
			self._redis.xautoclaim(
				name=request.stream,
				groupname=request.consumer_group,
				consumername=request.consumer_name,
				min_idle_time=request.min_idle_time_ms,
				start_id=request.start_id,
				count=request.count,
			),
		)

	async def exists(self, key: str) -> int:
		return await cast("Awaitable[int]", self._redis.exists(key))

	async def set(self, key: str, value: str, *, nx: bool = False, ex: int) -> bool | None:
		return await cast(
			"Awaitable[bool | None]", self._redis.set(key, value, nx=nx, ex=ex)
		)

	async def xadd(self, name: str, fields: Mapping[str, str]) -> str:
		return await cast("Awaitable[str]", self._redis.xadd(name, cast("Any", dict(fields))))

	async def xack(self, name: str, groupname: str, message_id: str) -> int:
		return await cast("Awaitable[int]", self._redis.xack(name, groupname, message_id))

	async def eval(self, script: str, numkeys: int, key: str, value: str) -> int:
		return await cast(
			"Awaitable[int]", self._redis.eval(script, numkeys, key, value)
		)
