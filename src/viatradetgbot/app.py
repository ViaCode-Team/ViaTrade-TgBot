from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dishka import AsyncContainer, make_async_container
from dishka.integrations.aiogram import setup_dishka
from redis.asyncio import Redis

from viatradetgbot.notifications.consumer import NotificationConsumer
from viatradetgbot.providers import AppProvider

if TYPE_CHECKING:
	from collections.abc import Awaitable
	from types import TracebackType
	from typing import Self

	from viatradetgbot.config import Settings


class ApplicationNotStartedError(RuntimeError):
	def __init__(self) -> None:
		super().__init__("App must be started with 'async with'.")


@dataclass(slots=True)
class _RunningApp:
	container: AsyncContainer
	bot: Bot
	dispatcher: Dispatcher
	consumer: NotificationConsumer
	scheduler: AsyncIOScheduler
	consumer_task: asyncio.Task[None]


async def wait_for_consumer_shutdown(
	consumer_task: asyncio.Task[None], grace_seconds: float, logger: logging.Logger
) -> None:
	try:
		await asyncio.wait_for(asyncio.shield(consumer_task), timeout=grace_seconds)
	except TimeoutError:
		if consumer_task.done():
			await consumer_task
			return

		logger.warning(
			"Consumer exceeded graceful shutdown timeout; cancelling: grace_seconds=%s",
			grace_seconds,
		)

		consumer_task.cancel()
		with suppress(asyncio.CancelledError):
			await consumer_task


class App:
	def __init__(self, settings: Settings) -> None:
		self._settings = settings
		self._logger = logging.getLogger(self.__class__.__name__)
		self._runtime: _RunningApp | None = None

	async def __aenter__(self) -> Self:
		self._runtime = await self._start()
		return self

	async def __aexit__(
		self,
		exception_type: type[BaseException] | None,
		exception: BaseException | None,
		traceback: TracebackType | None,
	) -> None:
		runtime, self._runtime = self._runtime, None
		if runtime is not None:
			await self._stop(runtime)

	async def run(self) -> None:
		runtime = self._require_runtime()
		await runtime.dispatcher.start_polling(runtime.bot, close_bot_session=False)

	async def _start(self) -> _RunningApp:
		container = make_async_container(AppProvider(self._settings))
		consumer: NotificationConsumer | None = None
		scheduler: AsyncIOScheduler | None = None

		try:
			await self._connect_to_redis(container)
			consumer = await container.get(NotificationConsumer)
			dispatcher = await container.get(Dispatcher)
			bot = await container.get(Bot)
			setup_dishka(container, dispatcher, auto_inject=True)

			await consumer.start()
			scheduler = await container.get(AsyncIOScheduler)
			scheduler.start()
			consumer_task = asyncio.create_task(
				consumer.run(),
				name="redis-notification-consumer",
			)

		except BaseException:
			await self._abort_startup(container, consumer, scheduler)
			raise

		return _RunningApp(container, bot, dispatcher, consumer, scheduler, consumer_task)

	async def _connect_to_redis(self, container: AsyncContainer) -> None:
		redis = await container.get(Redis)
		await cast("Awaitable[bool]", redis.ping())
		self._logger.info("Connected to Redis notification stream")

	async def _abort_startup(
		self,
		container: AsyncContainer,
		consumer: NotificationConsumer | None,
		scheduler: AsyncIOScheduler | None,
	) -> None:
		if consumer is not None:
			await consumer.stop()
		if scheduler is not None and scheduler.running:
			scheduler.shutdown(wait=False)
		await container.close()

	async def _stop(self, runtime: _RunningApp) -> None:
		await runtime.consumer.stop()
		if runtime.scheduler.running:
			runtime.scheduler.shutdown(wait=False)

		try:
			await wait_for_consumer_shutdown(
				runtime.consumer_task,
				self._settings.notification_shutdown_grace_seconds,
				self._logger,
			)
		except asyncio.CancelledError:
			runtime.consumer_task.cancel()
			with suppress(asyncio.CancelledError):
				await runtime.consumer_task
			raise
		finally:
			await runtime.container.close()
			self._logger.info("Telegram bot stopped")

	def _require_runtime(self) -> _RunningApp:
		if self._runtime is None:
			raise ApplicationNotStartedError
		return self._runtime
