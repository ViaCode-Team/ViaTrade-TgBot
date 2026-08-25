from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime

from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dishka import Provider, Scope, alias, provide
from redis.asyncio import Redis

from viatradetgbot.bot.bot import create_bot, create_dispatcher
from viatradetgbot.bot.notification_delivery import TelegramNotificationDelivery
from viatradetgbot.bot.telegram_links import TelegramAccountLinker
from viatradetgbot.config import Settings
from viatradetgbot.integrations.backend_api import BackendApi
from viatradetgbot.notifications.consumer import NotificationConsumer
from viatradetgbot.notifications.delivery import NotificationDelivery
from viatradetgbot.notifications.handlers import NotificationHandler, ReminderNotificationHandler
from viatradetgbot.notifications.redis_client import RedisNotificationClientAdapter
from viatradetgbot.notifications.store import NotificationStore


class AppProvider(Provider):
	scope = Scope.APP
	account_linker = alias(BackendApi, provides=TelegramAccountLinker)

	def __init__(self, settings: Settings) -> None:
		super().__init__()
		self._settings = settings

	@provide
	def settings(self) -> Settings:
		return self._settings

	@provide
	async def redis(self, settings: Settings) -> AsyncIterator[Redis]:
		redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
		try:
			yield redis
		finally:
			await redis.aclose()

	@provide
	async def backend_api(self, settings: Settings) -> AsyncIterator[BackendApi]:
		backend_api = BackendApi(settings)
		try:
			yield backend_api
		finally:
			await backend_api.close()

	@provide
	async def bot(self, settings: Settings) -> AsyncIterator[Bot]:
		bot = create_bot(settings.telegram_bot_token.get_secret_value())
		try:
			yield bot
		finally:
			await bot.session.close()

	@provide
	def dispatcher(self, settings: Settings) -> Dispatcher:
		return create_dispatcher(settings.telegram_message_rate_limit_seconds)

	@provide(provides=NotificationDelivery)
	def notification_delivery(self, bot: Bot) -> NotificationDelivery:
		return TelegramNotificationDelivery(bot)

	@provide
	def notification_store(self, redis: Redis, settings: Settings) -> NotificationStore:
		return NotificationStore(RedisNotificationClientAdapter(redis), settings)

	@provide
	def reminder_handler(self, backend_api: BackendApi) -> ReminderNotificationHandler:
		return ReminderNotificationHandler(backend_api)

	@provide
	def notification_handlers(
		self, reminder_handler: ReminderNotificationHandler
	) -> Mapping[str, NotificationHandler]:
		return {"reminder": reminder_handler}

	@provide
	def notification_consumer(
		self,
		store: NotificationStore,
		settings: Settings,
		delivery: NotificationDelivery,
		handlers: Mapping[str, NotificationHandler],
	) -> NotificationConsumer:
		return NotificationConsumer(store, settings, delivery, handlers)

	@provide
	def scheduler(self, settings: Settings, consumer: NotificationConsumer) -> AsyncIOScheduler:
		scheduler = AsyncIOScheduler()
		scheduler.add_job(
			consumer.recover_pending_messages,
			"interval",
			seconds=settings.notification_recovery_interval_seconds,
			id="recover-pending-notifications",
			name="recover pending notification messages",
			next_run_time=datetime.now(UTC),
			coalesce=True,
			max_instances=1,
		)
		return scheduler
