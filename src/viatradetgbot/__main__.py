from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from pydantic import ValidationError

from viatradetgbot.app import App
from viatradetgbot.config import Settings
from viatradetgbot.logging_config import configure_logging


async def run_app(settings: Settings) -> None:
	async with App(settings) as app:
		await app.run()


def main() -> None:
	try:
		settings = Settings()
	except ValidationError:
		logging.basicConfig(level=logging.ERROR)
		logging.getLogger(__name__).exception("Bot configuration is invalid")
		raise SystemExit(2) from None

	configure_logging(settings)
	asyncio.run(run_app(settings))


if __name__ == "__main__":
	with suppress(KeyboardInterrupt):
		main()
