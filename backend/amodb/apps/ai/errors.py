from __future__ import annotations

from typing import Any


class AIServiceError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 503,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.status_code = status_code
        self.retryable = retryable

    def detail(self, *, request_id: str) -> dict[str, Any]:
        return {
            "message": self.safe_message,
            "error_code": self.code,
            "retryable": self.retryable,
            "request_id": request_id,
        }


class AIConfigurationError(AIServiceError):
    def __init__(self, message: str, *, code: str = "AI_NOT_CONFIGURED") -> None:
        super().__init__(code, message, status_code=503, retryable=False)


class AIPermissionError(AIServiceError):
    def __init__(self, message: str = "AI access is not permitted for this tenant or feature.") -> None:
        super().__init__("AI_PERMISSION_DENIED", message, status_code=403, retryable=False)


class AIQuotaError(AIServiceError):
    def __init__(self, message: str) -> None:
        super().__init__("AI_USAGE_LIMIT_REACHED", message, status_code=429, retryable=False)


class AIProviderError(AIServiceError):
    def __init__(self, code: str, message: str, *, retryable: bool, status_code: int = 503) -> None:
        super().__init__(code, message, status_code=status_code, retryable=retryable)
