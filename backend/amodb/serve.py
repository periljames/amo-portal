import os
from typing import Dict, Optional

import uvicorn


def _ssl_options() -> Dict[str, Optional[str]]:
    certfile = os.getenv("SSL_CERTFILE")
    keyfile = os.getenv("SSL_KEYFILE")
    ca_certs = os.getenv("SSL_CA_CERTS")
    keyfile_password = os.getenv("SSL_KEYFILE_PASSWORD")

    if not any([certfile, keyfile, ca_certs, keyfile_password]):
        return {}

    options: Dict[str, Optional[str]] = {}
    if certfile:
        options["ssl_certfile"] = certfile
    if keyfile:
        options["ssl_keyfile"] = keyfile
    if ca_certs:
        options["ssl_ca_certs"] = ca_certs
    if keyfile_password:
        options["ssl_keyfile_password"] = keyfile_password
    return options


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw not in {None, ""} else default
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    return max(minimum, value)


def _uvicorn_options() -> dict:
    reload_enabled = _env_bool("RELOAD", False)
    configured_workers = _env_int(
        "PORTAL_API_PROCESS_COUNT",
        _env_int("WEB_CONCURRENCY", 1),
    )
    options: dict = {
        "host": os.getenv("HOST", "0.0.0.0"),
        "port": _env_int("PORT", 8000),
        "reload": reload_enabled,
        "workers": 1 if reload_enabled else configured_workers,
        "log_level": os.getenv("LOG_LEVEL", "info"),
        "proxy_headers": _env_bool("PROXY_HEADERS_ENABLED", True),
        # Never trust arbitrary Internet clients as forwarding proxies by default.
        # Deployments behind a known proxy/load balancer must set this explicitly.
        "forwarded_allow_ips": os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1"),
        "backlog": _env_int("UVICORN_BACKLOG", 2048),
        "timeout_keep_alive": _env_int("UVICORN_KEEP_ALIVE_SEC", 5),
        "timeout_graceful_shutdown": _env_int("UVICORN_GRACEFUL_SHUTDOWN_SEC", 30),
    }
    limit_concurrency = int(os.getenv("UVICORN_LIMIT_CONCURRENCY", "0") or "0")
    if limit_concurrency > 0:
        options["limit_concurrency"] = limit_concurrency
    options.update(_ssl_options())
    return options


def main() -> None:
    app_path = os.getenv("ASGI_APP", "amodb.production_app:app")
    uvicorn.run(app_path, **_uvicorn_options())


if __name__ == "__main__":
    main()
