from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiogram import Router
from aiogram.filters import CommandStart

if TYPE_CHECKING:
	from aiogram.filters.command import CommandObject
	from aiogram.types import Message

	from viatradetgbot.bot.telegram_links import TelegramAccountLinker

router = Router(name=__name__)
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def handle_start_command(
	message: Message,
	command: CommandObject,
	account_linker: TelegramAccountLinker,
) -> None:
	if message.from_user is None:
		await message.answer("Привязка доступна только в личном чате с ботом.")
		return

	if message.chat.id != message.from_user.id:
		await message.answer("Не удалось подтвердить личный Telegram-чат.")
		return

	if not command.args:
		await message.answer("Откройте бота по ссылке из ViaTrade для привязки аккаунта.")
		return

	result = await account_linker.link_telegram(
		token=command.args,
		telegram_id=str(message.chat.id),
	)
	if result.is_linked:
		logger.info("Telegram account linked: chat_id=%s", message.chat.id)
		await message.answer("Telegram-аккаунт успешно привязан к ViaTrade.")
		return

	logger.warning("Telegram link rejected: chat_id=%s reason=%s", message.chat.id, result.reason)
	await message.answer(result.user_message)
