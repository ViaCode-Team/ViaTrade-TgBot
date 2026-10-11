from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from pydantic import HttpUrl, ValidationError

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
	"""The stream message payload does not match the declared notification type."""


class ReminderNotificationHandler:
	def __init__(
		self,
		confirmation: ReminderDeliveryConfirmation,
		*,
		web_base_url: HttpUrl | None = None,
	) -> None:
		self._confirmation = confirmation
		self._web_base_url = web_base_url

	async def deliver(
		self, notification: NotificationEnvelope, delivery: NotificationDelivery
	) -> None:
		payload = self._parse_payload(notification)
		instrument_url = None
		if self._web_base_url is not None and payload.instrument_id is not None:
			instrument_url = f"{str(self._web_base_url).rstrip('/')}/stocks/{payload.instrument_id}"
		await delivery.send_text(
			notification.chat_id,
			payload.text,
			heading="Напоминание",
			instrument_ticker=payload.instrument_ticker,
			instrument_url=instrument_url,
			remind_at=payload.remind_at,
		)

	async def confirm_delivery(self, notification: NotificationEnvelope) -> None:
		payload = self._parse_payload(notification)
		await self._confirmation.confirm_reminder_delivery(
			payload.reminder_id, notification.user_id
		)

	@staticmethod
	def _parse_payload(notification: NotificationEnvelope) -> ReminderPayload:
		try:
			return ReminderPayload.model_validate(notification.payload)
		except ValidationError as exception:
			raise NotificationPayloadError from exception
