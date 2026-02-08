from __future__ import annotations

import os
from typing import Tuple


class EmailProvider:
    def send(
        self,
        *,
        template_key: str,
        recipient: str,
        subject: str,
        context: dict,
        correlation_id: str | None,
    ) -> None:
        raise NotImplementedError


class NoopProvider(EmailProvider):
    def send(
        self,
        *,
        template_key: str,
        recipient: str,
        subject: str,
        context: dict,
        correlation_id: str | None,
    ) -> None:
        return None


def get_email_provider() -> Tuple[EmailProvider, bool]:
    provider_name = (
        os.getenv("NOTIFICATIONS_EMAIL_PROVIDER")
        or os.getenv("EMAIL_PROVIDER")
        or ""
    ).strip().lower()
    if not provider_name or provider_name in {"none", "noop", "disabled"}:
        return NoopProvider(), False
    raise ValueError(f"Unsupported email provider: {provider_name}")
