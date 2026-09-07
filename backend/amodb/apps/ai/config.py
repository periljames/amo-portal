from __future__ import annotations

import json
import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping


def _clean(value: str | None, default: str = "") -> str:
    return str(value or default).strip()


def _positive_float(name: str, default: float, *, maximum: float) -> float:
    raw = _clean(os.getenv(name))
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if value <= 0 or value > maximum:
        raise ValueError(f"{name} must be greater than zero and at most {maximum:g}")
    return value


def _bounded_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = _clean(os.getenv(name))
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _nonnegative_int(name: str, default: int = 0) -> int:
    raw = _clean(os.getenv(name))
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 0:
        raise ValueError(f"{name} cannot be negative")
    return value


def _csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = _clean(os.getenv(name))
    values = tuple(dict.fromkeys(item.strip() for item in raw.split(",") if item.strip())) if raw else default
    if not values:
        raise ValueError(f"{name} must contain at least one model")
    return values


def _pricing() -> Mapping[str, tuple[Decimal, Decimal]]:
    raw = _clean(os.getenv("AI_MODEL_PRICING_USD_PER_MILLION_JSON"), "{}")
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("AI_MODEL_PRICING_USD_PER_MILLION_JSON must be valid JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError("AI_MODEL_PRICING_USD_PER_MILLION_JSON must be a JSON object")
    result: dict[str, tuple[Decimal, Decimal]] = {}
    for model, prices in decoded.items():
        if not isinstance(prices, dict):
            raise ValueError(f"Pricing for {model} must be an object")
        try:
            input_price = Decimal(str(prices.get("input", "0")))
            output_price = Decimal(str(prices.get("output", "0")))
        except InvalidOperation as exc:
            raise ValueError(f"Pricing for {model} must contain numeric input/output values") from exc
        if input_price < 0 or output_price < 0:
            raise ValueError(f"Pricing for {model} cannot be negative")
        result[str(model)] = (input_price, output_price)
    return result


@dataclass(frozen=True)
class ModelDefinition:
    model: str
    purpose: str
    premium: bool = False


@dataclass(frozen=True)
class AIConfiguration:
    openai_api_key: str
    openai_api_base_url: str
    default_model: str
    lightweight_model: str
    embedding_model: str
    premium_model: str
    allowed_chat_models: tuple[str, ...]
    allowed_embedding_models: tuple[str, ...]
    timeout_seconds: float
    max_retries: int
    retry_base_ms: int
    default_plan_type: str
    default_monthly_token_allowance: int
    default_monthly_request_allowance: int
    default_max_input_tokens_per_request: int
    default_max_output_tokens_per_request: int
    pricing_usd_per_million: Mapping[str, tuple[Decimal, Decimal]]

    @property
    def model_registry(self) -> tuple[ModelDefinition, ...]:
        definitions: list[ModelDefinition] = []
        for model in self.allowed_chat_models:
            purpose = "primary"
            if model == self.lightweight_model:
                purpose = "lightweight"
            if model == self.premium_model:
                purpose = "premium"
            definitions.append(ModelDefinition(model=model, purpose=purpose, premium=purpose == "premium"))
        definitions.extend(
            ModelDefinition(model=model, purpose="embedding")
            for model in self.allowed_embedding_models
        )
        return tuple(definitions)

    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> Decimal:
        input_price, output_price = self.pricing_usd_per_million.get(model, (Decimal("0"), Decimal("0")))
        cost = (
            (input_price * Decimal(max(0, input_tokens)))
            + (output_price * Decimal(max(0, output_tokens)))
        ) / Decimal(1_000_000)
        return cost.quantize(Decimal("0.00000001"))


def get_ai_configuration() -> AIConfiguration:
    default_model = _clean(os.getenv("OPENAI_DEFAULT_MODEL"), "gpt-5-mini")
    lightweight_model = _clean(os.getenv("OPENAI_LIGHTWEIGHT_MODEL"), "gpt-5-nano")
    embedding_model = _clean(os.getenv("OPENAI_EMBEDDING_MODEL"), "text-embedding-3-small")
    premium_model = _clean(os.getenv("OPENAI_PREMIUM_MODEL"), "gpt-5")
    allowed_chat = _csv(
        "AI_ALLOWED_CHAT_MODELS",
        (default_model, lightweight_model, premium_model),
    )
    allowed_embeddings = _csv("AI_ALLOWED_EMBEDDING_MODELS", (embedding_model,))
    if default_model not in allowed_chat:
        raise ValueError("OPENAI_DEFAULT_MODEL must be present in AI_ALLOWED_CHAT_MODELS")
    if lightweight_model not in allowed_chat:
        raise ValueError("OPENAI_LIGHTWEIGHT_MODEL must be present in AI_ALLOWED_CHAT_MODELS")
    if premium_model not in allowed_chat:
        raise ValueError("OPENAI_PREMIUM_MODEL must be present in AI_ALLOWED_CHAT_MODELS")
    if embedding_model not in allowed_embeddings:
        raise ValueError("OPENAI_EMBEDDING_MODEL must be present in AI_ALLOWED_EMBEDDING_MODELS")
    return AIConfiguration(
        openai_api_key=_clean(os.getenv("OPENAI_API_KEY")),
        openai_api_base_url=_clean(os.getenv("OPENAI_API_BASE_URL"), "https://api.openai.com"),
        default_model=default_model,
        lightweight_model=lightweight_model,
        embedding_model=embedding_model,
        premium_model=premium_model,
        allowed_chat_models=allowed_chat,
        allowed_embedding_models=allowed_embeddings,
        timeout_seconds=_positive_float("AI_PROVIDER_TIMEOUT_SECONDS", 15.0, maximum=20.0),
        max_retries=_bounded_int("AI_PROVIDER_MAX_RETRIES", 2, minimum=0, maximum=5),
        retry_base_ms=_bounded_int("AI_PROVIDER_RETRY_BASE_MS", 250, minimum=25, maximum=5_000),
        default_plan_type=_clean(os.getenv("AI_DEFAULT_PLAN_TYPE"), "DEVELOPMENT").upper(),
        default_monthly_token_allowance=_nonnegative_int("AI_DEFAULT_MONTHLY_TOKEN_ALLOWANCE"),
        default_monthly_request_allowance=_nonnegative_int("AI_DEFAULT_MONTHLY_REQUEST_ALLOWANCE"),
        default_max_input_tokens_per_request=_nonnegative_int("AI_DEFAULT_MAX_INPUT_TOKENS_PER_REQUEST"),
        default_max_output_tokens_per_request=_nonnegative_int("AI_DEFAULT_MAX_OUTPUT_TOKENS_PER_REQUEST"),
        pricing_usd_per_million=_pricing(),
    )
