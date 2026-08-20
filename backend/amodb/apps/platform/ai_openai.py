from __future__ import annotations

from typing import Any

from . import saas_providers


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


def _response_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if direct:
        return str(direct).strip()
    parts: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                parts.append(str(content["text"]))
    return "\n".join(parts).strip()


def responses_request(
    *,
    secret: dict[str, Any],
    config: dict[str, Any],
    model: str,
    instructions: str,
    prompt: str,
    max_output_tokens: int | None = None,
) -> dict[str, Any]:
    """Call OpenAI Responses with the portal's privacy and accounting contract.

    Managed OpenAI traffic always goes to the official OpenAI API host. Provider
    secrets never leave the backend and cannot be redirected to a configurable
    third-party base URL. ``store`` is always false. The provider-reported model,
    request id and usage are returned unchanged for the AI gateway to validate
    and meter. Paid tools are intentionally not enabled here.

    Network/transport failures are normalized to ``RuntimeError`` so callers can
    apply their documented retry or deterministic-fallback policy without
    depending on urllib/socket exception types.
    """
    api_key = str(secret.get("api_key") or "").strip()
    if not api_key:
        raise ValueError("OpenAI api_key is not configured")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if config.get("project"):
        headers["OpenAI-Project"] = str(config["project"])
    if config.get("organization"):
        headers["OpenAI-Organization"] = str(config["organization"])

    body: dict[str, Any] = {
        "model": model,
        "store": False,
        "instructions": instructions,
        "input": prompt,
    }
    if max_output_tokens is not None:
        body["max_output_tokens"] = max(1, int(max_output_tokens))

    try:
        status, response, elapsed = saas_providers._json_request(
            OPENAI_RESPONSES_URL,
            method="POST",
            headers=headers,
            body=body,
            timeout=20,
        )
    except OSError as exc:
        raise RuntimeError("OpenAI transport request failed") from exc

    if status < 200 or status >= 300 or not isinstance(response, dict):
        raise RuntimeError(f"OpenAI request failed ({status})")

    text = _response_text(response)
    if not text:
        raise RuntimeError("OpenAI returned an empty response")
    usage = response.get("usage")
    if not isinstance(usage, dict):
        raise RuntimeError("OpenAI response did not include usage accounting")
    if "input_tokens" not in usage or "output_tokens" not in usage:
        raise RuntimeError("OpenAI usage accounting is incomplete")

    return {
        "provider": "openai",
        "response_id": response.get("id"),
        "model": response.get("model") or model,
        "text": text,
        "usage": usage,
        "latency_ms": elapsed,
    }
