from __future__ import annotations

from typing import Protocol


class NotificationDelivery(Protocol):
	async def send_text(self, chat_id: str, text: str) -> None: ...


class ReminderDeliveryConfirmation(Protocol):
	async def confirm_reminder_delivery(self, reminder_id: int, user_id: int) -> None: ...


class NotificationRejectedError(Exception):
	"""Telegram permanently rejected a notification."""
