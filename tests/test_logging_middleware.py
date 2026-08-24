from __future__ import annotations

import unittest
from datetime import UTC, datetime
from typing import Any

from aiogram.types import Chat, Message, Update, User

from viatradetgbot.bot.middlewares.logging import LoggingMiddleware


class LoggingMiddlewareTests(unittest.IsolatedAsyncioTestCase):
	async def test_logs_message_metadata_without_start_token(self) -> None:
		middleware = LoggingMiddleware()
		update = Update(
			update_id=123,
			message=Message(
				message_id=456,
				date=datetime.now(UTC),
				chat=Chat(id=789, type="private"),
				from_user=User(id=321, is_bot=False, first_name="Test"),
				text="/start secret-link-token",
			),
		)

		async def handler(event: object, data: dict[str, Any]) -> str:
			self.assertIs(event, update)
			self.assertEqual(data, {})
			return "handled"

		with self.assertLogs("viatradetgbot.bot.middlewares.logging", level="INFO") as logs:
			result = await middleware(handler, update, {})

		self.assertEqual(result, "handled")
		log_message = logs.output[0]
		self.assertIn("update_id=123", log_message)
		self.assertIn("'is_command': True", log_message)
		self.assertNotIn("secret-link-token", log_message)
