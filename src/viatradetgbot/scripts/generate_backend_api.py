from collections.abc import Sequence
from pathlib import Path

from openapi_python_client import generate
from openapi_python_client.config import Config, ConfigFile, MetaType
from openapi_python_client.parser.errors import GeneratorError


class OpenApiGenerationError(RuntimeError):
	"""The OpenAPI client generator reported one or more errors."""

	def __init__(self, errors: Sequence[GeneratorError]) -> None:
		message = "\n".join(f"{error.header} {error.detail or ''}".strip() for error in errors)
		super().__init__(message)


def main() -> None:
	config = Config.from_sources(
		config_file=ConfigFile(),
		meta_type=MetaType.NONE,
		document_source=Path("swagger-tgbot.yaml"),
		file_encoding="utf-8",
		overwrite=True,
		output_path=Path("src/viatradetgbot/backend_api/gen"),
	)
	errors = generate(config=config)
	if errors:
		raise OpenApiGenerationError(errors)
