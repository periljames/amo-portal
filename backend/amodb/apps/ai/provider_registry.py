from __future__ import annotations

from collections.abc import Callable

from .config import AIConfiguration
from .contracts import AIProvider
from .errors import AIConfigurationError
from .providers import OpenAIProvider


ProviderBuilder = Callable[[dict[str, object], dict[str, object], AIConfiguration], AIProvider]


class AIProviderRegistry:
    def __init__(self) -> None:
        self._builders: dict[str, ProviderBuilder] = {}

    def register(self, code: str, builder: ProviderBuilder) -> None:
        self._builders[str(code).strip().lower()] = builder

    def create(
        self,
        code: str,
        *,
        secret: dict[str, object],
        provider_config: dict[str, object],
        application_config: AIConfiguration,
    ) -> AIProvider:
        normalized = str(code or "").strip().lower()
        builder = self._builders.get(normalized)
        if builder is None:
            raise AIConfigurationError(
                f"AI provider '{normalized or 'unknown'}' is not installed.",
                code="AI_PROVIDER_NOT_INSTALLED",
            )
        return builder(secret, provider_config, application_config)

    def installed(self) -> tuple[str, ...]:
        return tuple(sorted(self._builders))


def _openai_builder(
    secret: dict[str, object],
    provider_config: dict[str, object],
    application_config: AIConfiguration,
) -> AIProvider:
    return OpenAIProvider(
        api_key=str(secret.get("api_key") or ""),
        api_base_url=str(provider_config.get("api_base_url") or application_config.openai_api_base_url),
        project=str(provider_config.get("project") or "") or None,
        organization=str(provider_config.get("organization") or "") or None,
        timeout_seconds=application_config.timeout_seconds,
        max_retries=application_config.max_retries,
        retry_base_ms=application_config.retry_base_ms,
    )


provider_registry = AIProviderRegistry()
provider_registry.register("openai", _openai_builder)
