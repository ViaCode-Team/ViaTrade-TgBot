from __future__ import annotations

import ssl
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pydantic import SecretStr, ValidationError

from viatradetgbot.config import Settings
from viatradetgbot.integrations.backend_api import BackendApi


class BackendTlsTests(unittest.TestCase):
	def test_keeps_default_certificate_verification(self) -> None:
		with patch("viatradetgbot.integrations.backend_api.AuthenticatedClient") as client:
			BackendApi(_settings())
		self.assertIs(client.call_args.kwargs["verify_ssl"], expr2=True)

	def test_uses_configured_ca_bundle_with_certificate_verification(self) -> None:
		certificate = ssl.create_default_context().get_ca_certs(binary_form=True)[0]
		with TemporaryDirectory() as directory:
			bundle = Path(directory) / "backend.pem"
			bundle.write_text(ssl.DER_cert_to_PEM_cert(certificate), encoding="ascii")
			settings = _settings(backend_ca_bundle=bundle)
			with patch("viatradetgbot.integrations.backend_api.AuthenticatedClient") as client:
				BackendApi(settings)
			context = client.call_args.kwargs["verify_ssl"]
			self.assertIsInstance(context, ssl.SSLContext)
			self.assertIn(certificate, context.get_ca_certs(binary_form=True))
			self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
			self.assertTrue(context.check_hostname)

	def test_rejects_missing_ca_bundle(self) -> None:
		with TemporaryDirectory() as directory, self.assertRaises(ValidationError):  # noqa: PT027 - unittest suite
			_settings(backend_ca_bundle=Path(directory) / "missing.pem")

	def test_rejects_invalid_ca_bundle(self) -> None:
		with TemporaryDirectory() as directory:
			bundle = Path(directory) / "backend.pem"
			bundle.write_text("invalid certificate", encoding="utf-8")
			with self.assertRaises(ssl.SSLError):  # noqa: PT027 - unittest suite
				BackendApi(_settings(backend_ca_bundle=bundle))


def _settings(**overrides) -> Settings:
	overrides.setdefault("_env_file", None)
	return Settings(
		telegram_bot_token=SecretStr("test-token"),
		backend_service_password=SecretStr("service-password"),
		**overrides,
	)
