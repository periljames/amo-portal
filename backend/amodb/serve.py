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


def main() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    reload_enabled = os.getenv("RELOAD", "false").lower() in {"1", "true", "yes", "on"}
    log_level = os.getenv("LOG_LEVEL", "info")
    forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS", "*")

    uvicorn.run(
        "amodb.main:app",
        host=host,
        port=port,
        reload=reload_enabled,
        log_level=log_level,
        proxy_headers=True,
        forwarded_allow_ips=forwarded_allow_ips,
        **_ssl_options(),
    )


if __name__ == "__main__":
    main()
