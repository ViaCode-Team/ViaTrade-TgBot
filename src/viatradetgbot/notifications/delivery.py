from __future__ import annotations

from datetime import datetime
from typing import Protocol


class NotificationDelivery(Protocol):
	async def send_text(  # noqa: PLR0913 — optional notification presentation fields.
		self,
		chat_id: str,
		text: str,
		*,
		heading: str | None = None,
		instrument_ticker: str | None = None,
		instrument_url: str | None = None,
		remind_at: datetime | None = None,
	) -> None: ...


class ReminderDeliveryConfirmation(Protocol):
	async def confirm_reminder_delivery(self, reminder_id: int, user_id: int) -> None: ...


class NotificationRejectedError(Exception):
	"""Telegram permanently rejected a notification."""
