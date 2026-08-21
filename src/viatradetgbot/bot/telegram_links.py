from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class TelegramLinkResult:
	is_linked: bool
	reason: str
	user_message: str


class TelegramAccountLinker(Protocol):
	async def link_telegram(self, token: str, telegram_id: str) -> TelegramLinkResult: ...
