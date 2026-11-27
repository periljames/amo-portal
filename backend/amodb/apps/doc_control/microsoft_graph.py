"""Microsoft Graph delegated-file connector. The provider is never DMS publication authority."""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime
from urllib.parse import quote, urlencode, urlsplit

import httpx
from fastapi import HTTPException

from amodb.apps.platform.saas_secrets import decrypt_secret, encrypt_secret, SecretConfigurationError
from . import microsoft_models as mm

GRAPH = "https://graph.microsoft.com/v1.0"
LOGIN = "https://login.microsoftonline.com/organizations/oauth2/v2.0"
SCOPES = "openid profile offline_access User.Read Files.Read.All"
MAX_FILE_BYTES = 60 * 1024 * 1024


def _configured() -> dict[str, str]:
    settings = {key: str(os.getenv("DMS_MICROSOFT_" + key.upper()) or "").strip()
                for key in ("client_id", "client_secret", "redirect_uri", "frontend_url")}
    if not all(settings.values()):
        raise HTTPException(status_code=503, detail="Microsoft 365 connector is not configured on this deployment")
    if not settings["redirect_uri"].startswith("https://") or not settings["frontend_url"].startswith("https://"):
        raise HTTPException(status_code=503, detail="Microsoft 365 callback and portal URLs must use HTTPS")
    return settings


def configured() -> bool:
    try:
        _configured()
        return True
    except HTTPException:
        return False


def authorization_url(state: str) -> str:
    cfg = _configured()
    return LOGIN + "/authorize?" + urlencode({
        "client_id": cfg["client_id"],
        "response_type": "code",
        "response_mode": "query",
        "redirect_uri": cfg["redirect_uri"],
        "scope": SCOPES,
        "prompt": "select_account",
        "state": state,
    })


def _token_request(payload: dict[str, str]) -> dict:
    cfg = _configured()
    try:
        response = httpx.post(
            LOGIN + "/token",
            data={
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "redirect_uri": cfg["redirect_uri"],
                "scope": SCOPES,
                **payload,
            },
            timeout=25,
        )
        response.raise_for_status()
        result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Microsoft authorization or token refresh failed") from exc
    if not isinstance(result, dict) or not result.get("access_token"):
        raise HTTPException(status_code=502, detail="Microsoft did not return an access token")
    return result


def exchange_code(code: str) -> dict:
    return _token_request({"grant_type": "authorization_code", "code": code})


def _refresh(connection: mm.DocumentMicrosoftConnection) -> str:
    try:
        tokens = decrypt_secret(connection.encrypted_refresh_token)
    except SecretConfigurationError as exc:
        raise HTTPException(status_code=503, detail="Microsoft credential encryption is unavailable") from exc
    refresh = str(tokens.get("refresh_token") or "")
    if not refresh or connection.status != "CONNECTED":
        raise HTTPException(status_code=409, detail="Connect Microsoft 365 in Document Control Administration first")
    result = _token_request({"grant_type": "refresh_token", "refresh_token": refresh})
    rotated = result.get("refresh_token")
    if rotated:
        connection.encrypted_refresh_token = encrypt_secret({"refresh_token": str(rotated)})[0]
    connection.granted_scopes = str(result.get("scope") or connection.granted_scopes or "")
    return str(result["access_token"])


def _graph(connection: mm.DocumentMicrosoftConnection, path: str) -> dict:
    if not path.startswith("/") or "://" in path:
        raise ValueError("Graph path must be API-relative")
    access = _refresh(connection)
    try:
        response = httpx.get(
            GRAPH + path,
            headers={"Authorization": "Bearer " + access, "Accept": "application/json"},
            timeout=30,
            follow_redirects=False,
        )
        response.raise_for_status()
        content = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="The Microsoft file could not be accessed; check its SharePoint permissions") from exc
    if not isinstance(content, dict):
        raise HTTPException(status_code=502, detail="Unexpected Microsoft Graph response")
    return content


def connected_identity(access_token: str) -> dict:
    try:
        response = httpx.get(
            GRAPH + "/me?$select=id,userPrincipalName,displayName",
            headers={"Authorization": "Bearer " + access_token},
            timeout=25,
        )
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Unable to verify the connected Microsoft account") from exc


def tenant_claim(token: str) -> str:
    """Informational tenant identifier. Authorization is based on Graph access, not this claim."""
    try:
        fields = token.split(".")
        raw = fields[1] + "=" * (-len(fields[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(raw))
        return str(claims.get("tid") or "")[:72]
    except (IndexError, ValueError, UnicodeDecodeError):
        return ""


def valid_sharepoint_url(value: str) -> str:
    try:
        url = urlsplit(value.strip())
        host = str(url.hostname or "").lower()
        unsafe_authority = bool(url.username or url.password or url.port)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid SharePoint sharing link") from exc
    if url.scheme != "https" or unsafe_authority or not (
        host.endswith(".sharepoint.com") or host.endswith(".sharepoint-df.com")
    ):
        raise HTTPException(status_code=422, detail="Paste a secure SharePoint/OneDrive for Business sharing link")
    if len(value) > 2048:
        raise HTTPException(status_code=422, detail="Sharing link is too long")
    return value.strip()


def share_item(connection: mm.DocumentMicrosoftConnection, share_url: str) -> dict:
    valid = valid_sharepoint_url(share_url)
    share_id = "u!" + base64.urlsafe_b64encode(valid.encode("utf-8")).decode("ascii").rstrip("=")
    return _validated_item(_graph(connection, "/shares/" + quote(share_id, safe="") + "/driveItem"))


def _validated_item(payload: dict) -> dict:
    drive = str((payload.get("parentReference") or {}).get("driveId") or "")
    item_id = str(payload.get("id") or "")
    name = str(payload.get("name") or "")
    web_url = str(payload.get("webUrl") or "")
    if not drive or not item_id or not name or not valid_sharepoint_url(web_url):
        raise HTTPException(status_code=422, detail="The selected SharePoint item is not a supported file")
    if not name.lower().endswith(".docx") or "file" not in payload:
        raise HTTPException(status_code=422, detail="Select a Word DOCX document (not a folder or Office-native online document)")
    return payload


def current_item(connection: mm.DocumentMicrosoftConnection, link: mm.DocumentMicrosoftFileLink) -> dict:
    path = "/drives/" + quote(link.drive_id, safe="") + "/items/" + quote(link.item_id, safe="")
    return _validated_item(_graph(connection, path))


def _stamp(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def update_link(link: mm.DocumentMicrosoftFileLink, item: dict) -> None:
    link.item_name = str(item["name"])[:255]
    link.web_url = valid_sharepoint_url(str(item["webUrl"]))
    link.observed_etag = str(item.get("eTag") or "")[:255]
    link.observed_modified_at = _stamp(item.get("lastModifiedDateTime"))
    link.observed_size = int(item["size"]) if isinstance(item.get("size"), int) else None


def link_payload(link: mm.DocumentMicrosoftFileLink) -> dict:
    return {
        "manual_id": link.manual_id,
        "item_name": link.item_name,
        "web_url": link.web_url,
        "observed_etag": link.observed_etag,
        "modified_at": link.observed_modified_at.isoformat() if link.observed_modified_at else None,
        "size": link.observed_size,
        "last_imported_etag": link.last_imported_etag,
        "last_imported_revision_id": link.last_imported_revision_id,
        "newer_version_available": bool(link.last_imported_etag and link.observed_etag != link.last_imported_etag),
        "imported": bool(link.last_imported_revision_id),
    }


def download_docx(connection: mm.DocumentMicrosoftConnection, item: dict, *, drive_id: str) -> bytes:
    item_id = str(item["id"])
    max_bytes = min(200 * 1024 * 1024, max(1024, int(os.getenv("DMS_MICROSOFT_MAX_FILE_BYTES", MAX_FILE_BYTES))))
    size = item.get("size")
    if isinstance(size, int) and size > max_bytes:
        raise HTTPException(status_code=413, detail="SharePoint document exceeds the configured DMS import limit")
    # Graph's /content redirect contains a short-lived SharePoint download URL.
    # Do not send our bearer token to the redirected host.
    token = _refresh(connection)
    path = GRAPH + "/drives/" + quote(drive_id, safe="") + "/items/" + quote(item_id, safe="") + "/content"
    def read_stream(stream, data: bytearray) -> None:
        stream.raise_for_status()
        length = stream.headers.get("content-length")
        if length and length.isdecimal() and int(length) > max_bytes:
            raise HTTPException(status_code=413, detail="SharePoint file exceeds the DMS import limit")
        for chunk in stream.iter_bytes():
            data.extend(chunk)
            if len(data) > max_bytes:
                raise HTTPException(status_code=413, detail="SharePoint file exceeds the DMS import limit")

    try:
        data = bytearray()
        with httpx.Client(timeout=90, follow_redirects=False) as client:
            with client.stream("GET", path, headers={"Authorization": "Bearer " + token}) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    download_url = response.headers.get("location", "")
                    valid_sharepoint_url(download_url)
                elif response.status_code == 200:
                    download_url = None
                    read_stream(response, data)
                else:
                    response.raise_for_status()
                    raise HTTPException(status_code=502, detail="Microsoft Graph document download was unsuccessful")
            if download_url:
                # Pre-authenticated URL is issued by Graph; never forward the bearer token.
                with client.stream("GET", download_url) as download:
                    read_stream(download, data)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Unable to download the selected SharePoint document") from exc
    if not bytes(data).startswith(b"PK\x03\x04"):
        raise HTTPException(status_code=422, detail="Microsoft returned a file that is not a valid DOCX package")
    return bytes(data)
