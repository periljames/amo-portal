from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class AIRequestContext:
    tenant_id: str
    user_id: str
    document_context: Mapping[str, str | int | bool | None] = field(default_factory=dict)
    workflow_context: Mapping[str, str | int | bool | None] = field(default_factory=dict)


@dataclass(frozen=True)
class CompletionRequest:
    feature: str
    instructions: str
    input_text: str
    model: str
    max_output_tokens: int | None = None
    response_format: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class CompletionResult:
    provider: str
    model: str
    text: str
    response_id: str | None
    input_tokens: int
    output_tokens: int
    latency_ms: float


@dataclass(frozen=True)
class EmbeddingRequest:
    feature: str
    input_texts: tuple[str, ...]
    model: str


@dataclass(frozen=True)
class EmbeddingResult:
    provider: str
    model: str
    embeddings: tuple[tuple[float, ...], ...]
    response_id: str | None
    input_tokens: int
    latency_ms: float


class AIProvider(ABC):
    code: str

    @abstractmethod
    def complete(self, request: CompletionRequest) -> CompletionResult:
        raise NotImplementedError

    @abstractmethod
    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        raise NotImplementedError
