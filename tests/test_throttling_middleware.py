from __future__ import annotations

import unittest
from datetime import UTC, datetime
from typing import Any

from aiogram.types import Chat, Message

from viatradetgbot.bot.middlewares.throttling import ThrottlingMiddleware


class ThrottlingMiddlewareTests(unittest.IsolatedAsyncioTestCase):
	async def test_blocks_repeated_message_from_same_chat(self) -> None:
		middleware = ThrottlingMiddleware(rate_limit_seconds=1)
		message = Message(
			message_id=456,
			date=datetime.now(UTC),
			chat=Chat(id=789, type="private"),
			text="Hello",
		)
		handled_events: list[object] = []

		async def handler(event: object, _data: dict[str, Any]) -> str:
			handled_events.append(event)
			return "handled"

		first_result = await middleware(handler, message, {})
		second_result = await middleware(handler, message, {})

		self.assertEqual(first_result, "handled")
		self.assertIsNone(second_result)
		self.assertEqual(handled_events, [message])
