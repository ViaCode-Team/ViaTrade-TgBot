from __future__ import annotations

import logging
from http import HTTPStatus
from typing import TYPE_CHECKING, Self, cast

import httpx

from viatradetgbot.backend_api.gen.api.reminders import confirm_delivery
from viatradetgbot.backend_api.gen.api.telegram import link
from viatradetgbot.backend_api.gen.client import AuthenticatedClient
from viatradetgbot.backend_api.gen.models import (
	ConfirmReminderDeliveryRequest,
	LinkTelegramRequest,
	ProblemDetails,
)
from viatradetgbot.bot.telegram_links import TelegramLinkResult

if TYPE_CHECKING:
	from viatradetgbot.config import Settings


class BackendApiError(RuntimeError):
	"""The backend API request could not be completed successfully."""

	@classmethod
	def delivery_confirmation_failed(
		cls,
		reminder_id: int,
		status: HTTPStatus | None = None,
		error_code: str | None = None,
	) -> Self:
		if status is None:
			return cls(f"Could not confirm reminder delivery: reminder_id={reminder_id}.")
		return cls(
			f"Could not confirm reminder delivery: reminder_id={reminder_id} "
			f"status={status} code={error_code}."
		)


class BackendApi:
	def __init__(self, settings: Settings) -> None:
		self._logger = logging.getLogger(self.__class__.__name__)
		self._client = AuthenticatedClient(
			base_url=str(settings.backend_base_url),
			token=settings.backend_service_password.get_secret_value(),
			prefix="",
			auth_header_name="Service-Password",
			timeout=httpx.Timeout(settings.backend_request_timeout_seconds),
		)

	async def link_telegram(self, token: str, telegram_id: str) -> TelegramLinkResult:
		try:
			response = await link.asyncio_detailed(
				client=self._client,
				body=LinkTelegramRequest(telegram_token=token, telegram_id=telegram_id),
			)
		except httpx.HTTPError:
			self._logger.exception("Telegram linking request failed")
			return TelegramLinkResult(
				is_linked=False,
				reason="backend_unavailable",
				user_message="Сервис ViaTrade временно недоступен. Попробуйте ещё раз позже.",
			)

		if response.status_code is HTTPStatus.ACCEPTED:
			return TelegramLinkResult(is_linked=True, reason="linked", user_message="")

		error_code = _get_problem_code(response.parsed)
		if (
			response.status_code is HTTPStatus.BAD_REQUEST
			and error_code == "telegram_token_invalid"
		):
			return TelegramLinkResult(
				is_linked=False,
				reason=error_code,
				user_message=(
					"Ссылка недействительна или устарела. Сформируйте новую ссылку в ViaTrade."
				),
			)
		if response.status_code is HTTPStatus.CONFLICT:
			return TelegramLinkResult(
				is_linked=False,
				reason="telegram_already_linked",
				user_message="Этот Telegram-аккаунт уже привязан к другому пользователю ViaTrade.",
			)

		self._logger.warning(
			"Telegram linking rejected by backend: status=%s code=%s",
			response.status_code,
			error_code,
		)
		return TelegramLinkResult(
			is_linked=False,
			reason=error_code or "backend_error",
			user_message="Не удалось привязать Telegram-аккаунт. Попробуйте ещё раз позже.",
		)

	async def confirm_reminder_delivery(self, reminder_id: int, user_id: int) -> None:
		try:
			response = await confirm_delivery.asyncio_detailed(
				reminder_id,
				client=self._client,
				body=ConfirmReminderDeliveryRequest(user_id=user_id),
			)
		except httpx.HTTPError as exception:
			raise BackendApiError.delivery_confirmation_failed(reminder_id) from exception

		if response.status_code is HTTPStatus.NO_CONTENT:
			return
		if response.status_code is HTTPStatus.NOT_FOUND:
			self._logger.info("Reminder no longer exists: reminder_id=%s", reminder_id)
			return

		raise BackendApiError.delivery_confirmation_failed(
			reminder_id, response.status_code, _get_problem_code(response.parsed)
		)

	async def close(self) -> None:
		await self._client.get_async_httpx_client().aclose()


def _get_problem_code(response: object) -> str | None:
	if isinstance(response, ProblemDetails):
		return cast("str", response.code)
	return None
