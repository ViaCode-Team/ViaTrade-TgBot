from __future__ import annotations

from typing import Protocol


class NotificationDelivery(Protocol):
	async def send_text(self, chat_id: int, text: str) -> None: ...


class ReminderDeliveryConfirmation(Protocol):
	async def confirm_reminder_delivery(self, user_id: int, reminder_id: int) -> None: ...


class NotificationRejectedError(Exception):
	"""The delivery channel permanently rejected a notification."""
