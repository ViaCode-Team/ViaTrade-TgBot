from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class NotificationEnvelope(BaseModel):
	notification_id: str = Field(min_length=1, max_length=128)
	type: str = Field(min_length=1, max_length=64)
	user_id: int = Field(ge=1)
	chat_id: int
	payload: str = Field(min_length=1)
	created_at: datetime


class ReminderPayload(BaseModel):
	model_config = ConfigDict(alias_generator=to_camel)

	reminder_id: int = Field(ge=1)
	text: str = Field(min_length=1, max_length=1024)
	remind_at: datetime
	instrument_symbol: str | None = Field(default=None, max_length=255)
