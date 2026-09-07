from __future__ import annotations

import time
from typing import Any, Mapping

from amodb.apps.platform.saas_provider_network import json_request

from ..contracts import (
    AIProvider,
    CompletionRequest,
    CompletionResult,
    EmbeddingRequest,
    EmbeddingResult,
)
from ..errors import AIConfigurationError, AIProviderError


_RETRYABLE_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504})


def _response_text(payload: Mapping[str, Any]) -> str:
    direct = payload.get("output_text")
    if direct:
        return str(direct).strip()
    parts: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, Mapping):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, Mapping):
                continue
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                parts.append(str(content["text"]))
    return "\n".join(parts).strip()


def _usage(payload: Mapping[str, Any]) -> tuple[int, int]:
    usage = payload.get("usage") or {}
    if not isinstance(usage, Mapping):
        return 0, 0
    try:
        return int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)
    except (TypeError, ValueError) as exc:
        raise AIProviderError(
            "AI_PROVIDER_INVALID_RESPONSE",
            "OpenAI returned invalid token usage metadata.",
            retryable=False,
        ) from exc


class OpenAIProvider(AIProvider):
    code = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        api_base_url: str,
        project: str | None = None,
        organization: str | None = None,
        timeout_seconds: float = 15.0,
        max_retries: int = 2,
        retry_base_ms: int = 250,
    ) -> None:
        if not str(api_key or "").strip():
            raise AIConfigurationError("The OpenAI API key is not configured.")
        self._api_key = str(api_key).strip()
        self._api_base_url = str(api_base_url or "https://api.openai.com").strip().rstrip("/")
        self._project = str(project or "").strip() or None
        self._organization = str(organization or "").strip() or None
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._retry_base_ms = retry_base_ms

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if self._project:
            headers["OpenAI-Project"] = self._project
        if self._organization:
            headers["OpenAI-Organization"] = self._organization
        return headers

    def _post(self, path: str, body: dict[str, Any]) -> tuple[dict[str, Any], float]:
        last_status = 0
        started = time.perf_counter()
        deadline = started + self._timeout_seconds
        for attempt in range(self._max_retries + 1):
            remaining_seconds = deadline - time.perf_counter()
            if remaining_seconds < 1:
                break
            attempts_left = self._max_retries - attempt + 1
            attempt_timeout = max(1.0, remaining_seconds / attempts_left)
            try:
                status, payload, _latency_ms = json_request(
                    f"{self._api_base_url}{path}",
                    method="POST",
                    headers=self._headers(),
                    body=body,
                    timeout=attempt_timeout,
                )
            except ValueError as exc:
                raise AIConfigurationError(
                    "The configured OpenAI endpoint is not a permitted public HTTPS URL.",
                    code="AI_PROVIDER_ENDPOINT_INVALID",
                ) from exc
            except (OSError, TimeoutError, ConnectionError) as exc:
                if attempt < self._max_retries:
                    backoff = min((self._retry_base_ms / 1000) * (2**attempt), max(0, deadline - time.perf_counter()))
                    if backoff:
                        time.sleep(backoff)
                    continue
                raise AIProviderError(
                    "AI_PROVIDER_UNAVAILABLE",
                    "OpenAI could not be reached. Try again after checking provider connectivity.",
                    retryable=True,
                ) from exc

            last_status = int(status)
            if 200 <= last_status < 300 and isinstance(payload, dict):
                return payload, round((time.perf_counter() - started) * 1000, 2)
            if last_status in _RETRYABLE_STATUSES and attempt < self._max_retries:
                backoff = min((self._retry_base_ms / 1000) * (2**attempt), max(0, deadline - time.perf_counter()))
                if backoff:
                    time.sleep(backoff)
                continue
            if last_status in {401, 403}:
                raise AIProviderError(
                    "AI_PROVIDER_AUTHENTICATION_FAILED",
                    "OpenAI rejected the configured credential.",
                    retryable=False,
                    status_code=503,
                )
            if last_status == 429:
                raise AIProviderError(
                    "AI_PROVIDER_RATE_LIMITED",
                    "OpenAI temporarily rate-limited the request.",
                    retryable=True,
                    status_code=503,
                )
            raise AIProviderError(
                "AI_PROVIDER_REQUEST_FAILED",
                f"OpenAI returned an unsuccessful status ({last_status}).",
                retryable=last_status >= 500,
            )
        raise AIProviderError(
            "AI_PROVIDER_UNAVAILABLE",
            f"OpenAI request failed ({last_status}).",
            retryable=True,
        )

    def complete(self, request: CompletionRequest) -> CompletionResult:
        body: dict[str, Any] = {
            "model": request.model,
            "store": False,
            "instructions": request.instructions,
            "input": request.input_text,
        }
        if request.max_output_tokens is not None:
            body["max_output_tokens"] = int(request.max_output_tokens)
        if request.response_format:
            body["text"] = {"format": dict(request.response_format)}
        payload, latency_ms = self._post("/v1/responses", body)
        text = _response_text(payload)
        if not text:
            raise AIProviderError(
                "AI_PROVIDER_EMPTY_RESPONSE",
                "OpenAI returned no usable response.",
                retryable=False,
            )
        input_tokens, output_tokens = _usage(payload)
        return CompletionResult(
            provider=self.code,
            model=str(payload.get("model") or request.model),
            text=text,
            response_id=str(payload.get("id")) if payload.get("id") else None,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        payload, latency_ms = self._post(
            "/v1/embeddings",
            {"model": request.model, "input": list(request.input_texts)},
        )
        data = payload.get("data") or []
        if not isinstance(data, list):
            raise AIProviderError(
                "AI_PROVIDER_INVALID_RESPONSE",
                "OpenAI returned an invalid embedding response.",
                retryable=False,
            )
        try:
            ordered = sorted(
                (item for item in data if isinstance(item, Mapping)),
                key=lambda item: int(item.get("index") or 0),
            )
            embeddings = tuple(
                tuple(float(value) for value in item.get("embedding") or [])
                for item in ordered
            )
        except (TypeError, ValueError) as exc:
            raise AIProviderError(
                "AI_PROVIDER_INVALID_RESPONSE",
                "OpenAI returned invalid embedding data.",
                retryable=False,
            ) from exc
        if len(embeddings) != len(request.input_texts) or any(not vector for vector in embeddings):
            raise AIProviderError(
                "AI_PROVIDER_INVALID_RESPONSE",
                "OpenAI returned an incomplete embedding response.",
                retryable=False,
            )
        input_tokens, _ = _usage(payload)
        return EmbeddingResult(
            provider=self.code,
            model=str(payload.get("model") or request.model),
            embeddings=embeddings,
            response_id=str(payload.get("id")) if payload.get("id") else None,
            input_tokens=input_tokens,
            latency_ms=latency_ms,
        )
