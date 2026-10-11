from __future__ import annotations

import socket
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, FilePath, HttpUrl, RedisDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WebBaseUrlError(ValueError):
	def __init__(self) -> None:
		super().__init__(
			"VIATRADE_WEB_BASE_URL must be an absolute HTTP(S) URL "
			"without userinfo, query or fragment"
		)


class Settings(BaseSettings):
	model_config = SettingsConfigDict(
		env_file=".env",
		env_file_encoding="utf-8",
		extra="ignore",
		hide_input_in_errors=True,
	)

	telegram_bot_token: SecretStr = Field(
		default_factory=lambda: SecretStr(""),
		min_length=1,
		validate_default=True,
	)
	backend_base_url: HttpUrl = HttpUrl("http://127.0.0.1:8080")
	viatrade_web_base_url: HttpUrl | None = None
	backend_service_password: SecretStr = Field(
		default_factory=lambda: SecretStr(""),
		min_length=1,
		validate_default=True,
	)

	backend_request_timeout_seconds: int = Field(default=15, ge=1, le=60)
	backend_ca_bundle: FilePath | None = None
	telegram_message_rate_limit_seconds: float = Field(default=1, gt=0, le=60)
	redis_url: RedisDsn = RedisDsn("redis://127.0.0.1:6379/1")
	notification_stream: str = Field(default="telegram:notifications", min_length=1)
	notification_consumer_group: str = Field(default="viatrade-telegram-bot", min_length=1)
	notification_consumer_name: str = Field(default_factory=socket.gethostname, min_length=1)
	notification_read_block_ms: int = Field(default=5000, ge=1000, le=60000)
	notification_read_count: int = Field(default=10, ge=1, le=100)
	notification_claim_idle_ms: int = Field(default=60000, ge=1000)
	notification_delivery_lock_ttl_seconds: int = Field(default=300, ge=60)
	notification_recovery_interval_seconds: int = Field(default=30, ge=1)
	notification_deduplication_ttl_seconds: int = Field(default=604800, ge=60)
	notification_shutdown_grace_seconds: int = Field(default=90, ge=10, le=600)
	log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

	@field_validator("viatrade_web_base_url", mode="before")
	@classmethod
	def validate_web_base_url(cls, value: object) -> object:
		if value == "":
			return None
		if isinstance(value, (str, HttpUrl)):
			raw_url = str(value)
			parts = urlsplit(raw_url)
			if (
				not raw_url.lower().startswith(("http://", "https://"))
				or not parts.hostname
				or "@" in parts.netloc
				or "?" in raw_url
				or "#" in raw_url
				or "\\" in raw_url
				or any(character.isspace() for character in raw_url)
			):
				raise WebBaseUrlError
		return value
