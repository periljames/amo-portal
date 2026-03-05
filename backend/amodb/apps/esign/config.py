from __future__ import annotations

import os
from dataclasses import dataclass

_TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ESignConfig:
    webauthn_rp_id: str
    webauthn_expected_origins: list[str]
    webauthn_require_uv: bool
    challenge_ttl_seconds: int
    signing_intent_ttl_seconds: int
    verify_token_bytes: int
    provider_mode: str
    external_sign_url: str | None
    external_validate_url: str | None
    external_timeout_seconds: int
    external_auth_mode: str
    external_bearer_token: str | None
    signing_reason_default: str
    signing_location_default: str
    enable_timestamping: bool
    require_crypto_provider_for_finalization: bool
    provider_healthcheck_on_startup: bool
    allow_crypto_fallback_to_appearance: bool
    public_verify_base_url: str
    public_verify_path_template: str


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE


def load_config() -> ESignConfig:
    rp_id = (os.getenv("ESIGN_WEBAUTHN_RP_ID") or "localhost").strip()
    origins_raw = (os.getenv("ESIGN_WEBAUTHN_EXPECTED_ORIGINS") or "http://localhost:5173").strip()
    origins = [x.strip() for x in origins_raw.split(",") if x.strip()]
    cfg = ESignConfig(
        webauthn_rp_id=rp_id,
        webauthn_expected_origins=origins,
        webauthn_require_uv=_bool_env("ESIGN_WEBAUTHN_REQUIRE_UV", True),
        challenge_ttl_seconds=int(os.getenv("ESIGN_CHALLENGE_TTL_SECONDS", "300") or "300"),
        signing_intent_ttl_seconds=int(os.getenv("ESIGN_SIGNING_INTENT_TTL_SECONDS", "900") or "900"),
        verify_token_bytes=int(os.getenv("ESIGN_VERIFY_TOKEN_BYTES", "32") or "32"),
        provider_mode=(os.getenv("ESIGN_PROVIDER_MODE") or "appearance").strip().lower(),
        external_sign_url=(os.getenv("ESIGN_EXTERNAL_SIGN_URL") or "").strip() or None,
        external_validate_url=(os.getenv("ESIGN_EXTERNAL_VALIDATE_URL") or "").strip() or None,
        external_timeout_seconds=int(os.getenv("ESIGN_EXTERNAL_TIMEOUT_SECONDS", "30") or "30"),
        external_auth_mode=(os.getenv("ESIGN_EXTERNAL_AUTH_MODE") or "none").strip().lower(),
        external_bearer_token=(os.getenv("ESIGN_EXTERNAL_BEARER_TOKEN") or "").strip() or None,
        signing_reason_default=(os.getenv("ESIGN_SIGNING_REASON_DEFAULT") or "Approved by signer").strip(),
        signing_location_default=(os.getenv("ESIGN_SIGNING_LOCATION_DEFAULT") or "AMO Portal").strip(),
        enable_timestamping=_bool_env("ESIGN_ENABLE_TIMESTAMPING", True),
        require_crypto_provider_for_finalization=_bool_env("ESIGN_REQUIRE_CRYPTO_PROVIDER_FOR_FINALIZATION", False),
        provider_healthcheck_on_startup=_bool_env("ESIGN_PROVIDER_HEALTHCHECK_ON_STARTUP", False),
        allow_crypto_fallback_to_appearance=_bool_env("ESIGN_ALLOW_CRYPTO_FALLBACK_TO_APPEARANCE", False),
        public_verify_base_url=(os.getenv("ESIGN_PUBLIC_VERIFY_BASE_URL") or "http://localhost:5173").strip(),
        public_verify_path_template=(os.getenv("ESIGN_PUBLIC_VERIFY_PATH_TEMPLATE") or "/verify/{token}").strip(),
    )
    validate_config(cfg)
    return cfg


def validate_config(cfg: ESignConfig) -> None:
    if not cfg.webauthn_rp_id:
        raise RuntimeError("ESIGN_WEBAUTHN_RP_ID must not be empty")
    if not cfg.webauthn_expected_origins:
        raise RuntimeError("ESIGN_WEBAUTHN_EXPECTED_ORIGINS must include at least one origin")
    if cfg.challenge_ttl_seconds <= 0:
        raise RuntimeError("ESIGN_CHALLENGE_TTL_SECONDS must be > 0")
    if cfg.signing_intent_ttl_seconds <= 0:
        raise RuntimeError("ESIGN_SIGNING_INTENT_TTL_SECONDS must be > 0")
    if cfg.verify_token_bytes < 16:
        raise RuntimeError("ESIGN_VERIFY_TOKEN_BYTES must be >= 16")
    if cfg.provider_mode not in {"appearance", "external_pades"}:
        raise RuntimeError("ESIGN_PROVIDER_MODE must be one of: appearance, external_pades")
    if cfg.external_auth_mode not in {"none", "bearer", "mtls"}:
        raise RuntimeError("ESIGN_EXTERNAL_AUTH_MODE must be one of: none, bearer, mtls")
    if cfg.provider_mode == "external_pades":
        if not cfg.external_sign_url or not cfg.external_validate_url:
            raise RuntimeError("ESIGN_EXTERNAL_SIGN_URL and ESIGN_EXTERNAL_VALIDATE_URL are required for external_pades mode")
        if cfg.external_auth_mode == "bearer" and not cfg.external_bearer_token:
            raise RuntimeError("ESIGN_EXTERNAL_BEARER_TOKEN is required when ESIGN_EXTERNAL_AUTH_MODE=bearer")
    if cfg.external_timeout_seconds <= 0:
        raise RuntimeError("ESIGN_EXTERNAL_TIMEOUT_SECONDS must be > 0")
    if not cfg.public_verify_base_url:
        raise RuntimeError("ESIGN_PUBLIC_VERIFY_BASE_URL must not be empty")
    if "{token}" not in cfg.public_verify_path_template:
        raise RuntimeError("ESIGN_PUBLIC_VERIFY_PATH_TEMPLATE must include '{token}'")
