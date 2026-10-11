from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dishka import make_async_container
from dishka.integrations.aiogram import setup_dishka
from pydantic import HttpUrl, SecretStr

from viatradetgbot.bot.notification_delivery import TelegramNotificationDelivery
from viatradetgbot.bot.telegram_links import TelegramAccountLinker
from viatradetgbot.config import Settings
from viatradetgbot.integrations.backend_api import BackendApi
from viatradetgbot.notifications.delivery import NotificationDelivery
from viatradetgbot.notifications.handlers import ReminderNotificationHandler
from viatradetgbot.notifications.models import NotificationEnvelope
from viatradetgbot.providers import AppProvider

TEST_BOT_TOKEN = SecretStr(
	"123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-"
)
TEST_SERVICE_PASSWORD = SecretStr("service-password")


class SchedulerProviderTests(unittest.IsolatedAsyncioTestCase):
	async def test_resolves_reminder_link_setting_and_telegram_delivery(self) -> None:
		settings = _settings()
		settings.viatrade_web_base_url = HttpUrl("https://example.test/app/")
		container = make_async_container(AppProvider(settings))
		try:
			handler = await container.get(ReminderNotificationHandler)
			adapter = await container.get(NotificationDelivery)
			delivery = AsyncMock(spec=NotificationDelivery)
			notification = NotificationEnvelope.model_validate(
				{
					"notificationId": "reminder:42",
					"type": "reminder",
					"schemaVersion": 1,
					"userId": 7,
					"chatId": "123",
					"createdAt": "2026-10-11T12:00:00Z",
					"payload": {
						"reminderId": 42,
						"text": "Buy",
						"remindAt": "2026-10-11T12:00:00Z",
						"instrumentId": 123,
					},
				}
			)
			await handler.deliver(notification, delivery)
			self.assertIsInstance(adapter, TelegramNotificationDelivery)
			delivery.send_text.assert_awaited_once_with(
				"123",
				"Buy",
				heading="Напоминание",
				instrument_ticker=None,
				instrument_url="https://example.test/app/stocks/123",
				remind_at=datetime(2026, 10, 11, 12, tzinfo=UTC),
			)
		finally:
			await container.close()

	async def test_resolves_handler_annotations_during_dispatcher_startup(self) -> None:
		container = make_async_container(AppProvider(_settings()))
		try:
			dispatcher = await container.get(Dispatcher)
			bot = await container.get(Bot)
			setup_dishka(container, dispatcher, auto_inject=True)
			await dispatcher.emit_startup(bot=bot)
		finally:
			await container.close()

	async def test_configures_single_non_overlapping_pending_recovery_job(self) -> None:
		settings = _settings(notification_recovery_interval_seconds=42)
		container = make_async_container(AppProvider(settings))
		try:
			scheduler = await container.get(AsyncIOScheduler)
			account_linker = await container.get(TelegramAccountLinker)
			backend_api = await container.get(BackendApi)
			jobs = scheduler.get_jobs()
		finally:
			await container.close()

		self.assertEqual(len(jobs), 1)
		job = jobs[0]
		self.assertEqual(job.id, "recover-pending-notifications")
		self.assertEqual(job.max_instances, 1)
		self.assertTrue(job.coalesce)
		self.assertEqual(job.trigger.interval.total_seconds(), 42)
		self.assertIs(account_linker, backend_api)


def _settings(notification_recovery_interval_seconds: int = 30) -> Settings:
	return Settings(
		_env_file=None,  # type: ignore[call-arg]
		telegram_bot_token=TEST_BOT_TOKEN,
		backend_service_password=TEST_SERVICE_PASSWORD,
		viatrade_web_base_url=None,
		notification_recovery_interval_seconds=notification_recovery_interval_seconds,
	)
