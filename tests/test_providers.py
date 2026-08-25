from __future__ import annotations

import unittest

from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dishka import make_async_container
from dishka.integrations.aiogram import setup_dishka
from pydantic import SecretStr

from viatradetgbot.bot.telegram_links import TelegramAccountLinker
from viatradetgbot.config import Settings
from viatradetgbot.integrations.backend_api import BackendApi
from viatradetgbot.providers import AppProvider

TEST_BOT_TOKEN = SecretStr(
	"123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-"
)
TEST_SERVICE_PASSWORD = SecretStr("service-password")


class SchedulerProviderTests(unittest.IsolatedAsyncioTestCase):
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
		telegram_bot_token=TEST_BOT_TOKEN,
		backend_service_password=TEST_SERVICE_PASSWORD,
		notification_recovery_interval_seconds=notification_recovery_interval_seconds,
	)
