from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

INT32_MIN = -(2**31)
INT32_MAX = 2**31 - 1


class NotificationEnvelope(BaseModel):
	model_config = ConfigDict(alias_generator=to_camel)

	notification_id: str
	user_id: int = Field(ge=INT32_MIN, le=INT32_MAX)
	chat_id: str
	payload: dict[str, object]
	created_at: datetime
	type: Literal["reminder"]
	schema_version: Literal[1]


class ReminderPayload(BaseModel):
	model_config = ConfigDict(alias_generator=to_camel)

	reminder_id: int = Field(ge=INT32_MIN, le=INT32_MAX)
	text: str
	remind_at: datetime
	instrument_symbol: str | None = None
