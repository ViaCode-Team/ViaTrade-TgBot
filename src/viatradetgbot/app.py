from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import TYPE_CHECKING, cast

from redis.asyncio import Redis

from viatradetgbot.bot.bot import TelegramBot
from viatradetgbot.bot.notification_delivery import TelegramNotificationDelivery
from viatradetgbot.integrations.backend_client import BackendClient
from viatradetgbot.notifications.consumer import NotificationConsumer
from viatradetgbot.notifications.handlers import ReminderNotificationHandler

if TYPE_CHECKING:
	from collections.abc import Awaitable
	from types import TracebackType
	from typing import Self

	from viatradetgbot.config import Settings


class ApplicationNotStartedError(RuntimeError):
	def __init__(self) -> None:
		super().__init__("App must be started with 'async with'.")


class App:
	def __init__(self, settings: Settings) -> None:
		self._logger = logging.getLogger(self.__class__.__name__)
		self._redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
		self._backend_client = BackendClient(settings)
		self._telegram_bot = TelegramBot(
			token=settings.telegram_bot_token.get_secret_value(),
			account_linker=self._backend_client,
		)
		delivery = TelegramNotificationDelivery(self._telegram_bot.bot)
		self._notification_consumer = NotificationConsumer(
			redis_client=self._redis,
			settings=settings,
			delivery=delivery,
			handlers={"reminder": ReminderNotificationHandler(self._backend_client)},
		)
		self._consumer_task: asyncio.Task[None] | None = None
		self._is_closed = False

	async def __aenter__(self) -> Self:
		try:
			await cast("Awaitable[bool]", self._redis.ping())
			self._logger.info("Connected to Redis notification stream")
			self._consumer_task = asyncio.create_task(
				self._notification_consumer.run(),
				name="redis-notification-consumer",
			)
		except BaseException:
			await self._close_resources()
			raise

		return self

	async def __aexit__(
		self,
		exception_type: type[BaseException] | None,
		exception: BaseException | None,
		traceback: TracebackType | None,
	) -> None:
		await self._shutdown()

	async def run(self) -> None:
		if self._consumer_task is None:
			raise ApplicationNotStartedError
		await self._telegram_bot.run()

	async def _shutdown(self) -> None:
		try:
			await self._stop_consumer()
		finally:
			await self._close_resources()
			self._logger.info("Telegram bot stopped")

	async def _stop_consumer(self) -> None:
		if self._consumer_task is None:
			return

		try:
			await self._notification_consumer.stop()
		finally:
			self._consumer_task.cancel()
			with suppress(asyncio.CancelledError):
				await self._consumer_task
			self._consumer_task = None

	async def _close_resources(self) -> None:
		if self._is_closed:
			return

		try:
			try:
				await self._backend_client.close()
			finally:
				await self._redis.aclose()
		finally:
			await self._telegram_bot.close()
			self._is_closed = True
