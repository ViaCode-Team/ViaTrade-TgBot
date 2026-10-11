from __future__ import annotations

import unittest
from unittest.mock import patch

from pydantic import SecretStr, ValidationError

from viatradetgbot.config import Settings


def _settings(**overrides) -> Settings:
	overrides.setdefault("_env_file", None)
	return Settings(
		telegram_bot_token=SecretStr("test-token"),
		backend_service_password=SecretStr("service-password"),
		**overrides,
	)


class WebBaseUrlSettingsTests(unittest.TestCase):
	def test_accepts_optional_url_and_http_with_port_and_path(self) -> None:
		for url in (
			None,
			"",
			"https://example.test",
			"https://example.test/viatrade/",
			"http://localhost:5173",
			"http://[::1]:5173/app",
		):
			with self.subTest(url=url):
				settings = _settings(viatrade_web_base_url=url)
				if url:
					self.assertTrue(str(settings.viatrade_web_base_url).startswith(url))
				else:
					self.assertIsNone(settings.viatrade_web_base_url)

	def test_loads_environment_setting(self) -> None:
		with patch.dict("os.environ", {"VIATRADE_WEB_BASE_URL": "https://example.test/app"}):
			self.assertEqual(str(_settings().viatrade_web_base_url), "https://example.test/app")

	def test_rejects_invalid_base_urls_before_processing(self) -> None:
		for url in (
			"javascript:alert(1)",
			"data:text/plain,x",
			"tg://resolve",
			"//example.test",
			"/stocks",
			"https://",
			"https:///path",
			"https:example.test",
			"https://?x=1",
			"https://user:private-password@example.test",
			"https://@example.test",
			"https://example.test/?x=1",
			"https://example.test/?",
			"https://example.test/#x",
			"https://example.test/#",
			"https://example.test:bad",
			"https://example.test:70000",
			" https://example.test",
			"https://exam\tple.test",
			"https://example.test\\path",
		):
			with self.subTest(url=url), self.assertRaises(ValidationError) as error:  # noqa: PT027
				_settings(viatrade_web_base_url=url)
			self.assertIn("viatrade_web_base_url", str(error.exception))
			self.assertNotIn("private-password", str(error.exception))
