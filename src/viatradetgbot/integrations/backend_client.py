from __future__ import annotations

import logging
import ssl
from typing import TYPE_CHECKING

import httpx

from viatradetgbot.bot.telegram_links import TelegramLinkResult

if TYPE_CHECKING:
	from viatradetgbot.config import Settings


class BackendClient:
	def __init__(self, settings: Settings) -> None:
		self._logger = logging.getLogger(self.__class__.__name__)
		self._logger.debug("[FIX] Backend TLS verification uses the system trust store")
		self._client = httpx.AsyncClient(
			base_url=str(settings.backend_base_url).rstrip("/"),
			timeout=httpx.Timeout(10.0),
			verify=ssl.create_default_context(),
			headers={
				"TgBot-Service-Password": settings.backend_service_password.get_secret_value()
			},
		)

	async def link_telegram(self, token: str, telegram_id: str) -> TelegramLinkResult:
		try:
			response = await self._client.post(
				"/api/v1/internal/telegram/links",
				json={"telegramToken": token, "telegramId": telegram_id},
			)
		except httpx.HTTPError:
			self._logger.exception("Backend request for Telegram linking failed")
			return TelegramLinkResult(
				is_linked=False,
				reason="backend_unavailable",
				user_message="Сервис ViaTrade временно недоступен. Попробуйте ещё раз позже.",
			)

		if response.status_code == httpx.codes.ACCEPTED:
			return TelegramLinkResult(is_linked=True, reason="linked", user_message="")

		if response.status_code == httpx.codes.UNAUTHORIZED:
			if self._get_error_code(response) == "invalid_token":
				return TelegramLinkResult(
					is_linked=False,
					reason="invalid_or_expired_token",
					user_message=(
						"Ссылка недействительна или устарела. Сформируйте новую ссылку в ViaTrade."
					),
				)
			self._logger.error("Telegram linking was rejected by backend authentication")
			return TelegramLinkResult(
				is_linked=False,
				reason="backend_unauthorized",
				user_message="Сервис ViaTrade временно недоступен. Попробуйте ещё раз позже.",
			)

		if response.status_code == httpx.codes.CONFLICT:
			return TelegramLinkResult(
				is_linked=False,
				reason="telegram_already_linked",
				user_message="Этот Telegram-аккаунт уже привязан к другому пользователю ViaTrade.",
			)

		self._logger.error("Telegram linking failed with backend status %s", response.status_code)
		return TelegramLinkResult(
			is_linked=False,
			reason="backend_error",
			user_message="Не удалось привязать Telegram-аккаунт. Попробуйте ещё раз позже.",
		)

	async def confirm_reminder_delivery(self, user_id: int, reminder_id: int) -> None:
		self._logger.debug(
			"Confirming Telegram delivery with backend: user_id=%s reminder_id=%s",
			user_id,
			reminder_id,
		)
		try:
			response = await self._client.put(
				f"/api/v1/internal/reminders/{reminder_id}/delivery",
				json={"userId": user_id},
			)
			response.raise_for_status()
		except httpx.HTTPStatusError as exception:
			if exception.response.status_code == httpx.codes.NOT_FOUND:
				self._logger.warning(
					"Reminder was removed before delivery confirmation: user_id=%s reminder_id=%s",
					user_id,
					reminder_id,
				)
				return
			self._logger.exception(
				"Backend rejected Telegram delivery confirmation: user_id=%s reminder_id=%s",
				user_id,
				reminder_id,
			)
			raise
		except httpx.HTTPError:
			self._logger.exception(
				"Backend delivery confirmation request failed: user_id=%s reminder_id=%s",
				user_id,
				reminder_id,
			)
			raise

		self._logger.info(
			"Backend confirmed Telegram delivery: user_id=%s reminder_id=%s",
			user_id,
			reminder_id,
		)

	async def close(self) -> None:
		await self._client.aclose()

	@staticmethod
	def _get_error_code(response: httpx.Response) -> str | None:
		try:
			body = response.json()
		except ValueError:
			return None
		error_code = body.get("code") if isinstance(body, dict) else None
		return error_code if isinstance(error_code, str) else None
