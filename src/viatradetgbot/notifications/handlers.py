from __future__ import annotations

import json
from typing import TYPE_CHECKING, Protocol

from pydantic import ValidationError

from viatradetgbot.notifications.models import NotificationEnvelope, ReminderPayload

if TYPE_CHECKING:
	from viatradetgbot.notifications.delivery import (
		NotificationDelivery,
		ReminderDeliveryConfirmation,
	)


class NotificationHandler(Protocol):
	async def deliver(
		self, notification: NotificationEnvelope, delivery: NotificationDelivery
	) -> None: ...

	async def confirm_delivery(self, notification: NotificationEnvelope) -> None: ...


class NotificationPayloadError(ValueError):
	def __init__(self) -> None:
		super().__init__("Notification payload is invalid.")


class ReminderNotificationHandler:
	def __init__(self, confirmation: ReminderDeliveryConfirmation) -> None:
		self._confirmation = confirmation

	async def deliver(
		self, notification: NotificationEnvelope, delivery: NotificationDelivery
	) -> None:
		payload = self._parse_payload(notification)

		instrument = f" ({payload.instrument_symbol})" if payload.instrument_symbol else ""
		await delivery.send_text(notification.chat_id, f"Напоминание{instrument}:\n{payload.text}")

	async def confirm_delivery(self, notification: NotificationEnvelope) -> None:
		payload = self._parse_payload(notification)
		await self._confirmation.confirm_reminder_delivery(
			notification.user_id, payload.reminder_id
		)

	@staticmethod
	def _parse_payload(notification: NotificationEnvelope) -> ReminderPayload:
		try:
			return ReminderPayload.model_validate_json(notification.payload)
		except (ValidationError, json.JSONDecodeError) as exception:
			raise NotificationPayloadError from exception
