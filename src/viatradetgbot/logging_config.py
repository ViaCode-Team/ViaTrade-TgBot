from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from viatradetgbot.config import Settings


def configure_logging(settings: Settings) -> None:
	logging.basicConfig(
		level=settings.log_level,
		format="%(asctime)s %(levelname)s %(name)s: %(message)s",
	)
