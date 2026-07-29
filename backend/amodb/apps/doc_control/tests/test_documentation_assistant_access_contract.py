from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from amodb.apps.doc_control.workspace_access import enforce_workspace_access


def _request(method: str, path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "raw_path": path.encode("ascii"),
            "root_path": "",
            "scheme": "https",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 443),
        }
    )


def _reader():
    return SimpleNamespace(
        id="reader-1",
        role="TECHNICIAN",
        is_superuser=False,
        is_amo_admin=False,
    )


def test_assisted_search_route_is_available_to_active_publication_readers() -> None:
    enforce_workspace_access(
        _request("POST", "/doc-control/workspace/t/safarilink/knowledge/assist"),
        current_user=_reader(),
    )


def test_controller_routes_remain_closed_to_publication_readers() -> None:
    with pytest.raises(HTTPException) as caught:
        enforce_workspace_access(
            _request("POST", "/doc-control/workspace/t/safarilink/knowledge/reindex/revision-1"),
            current_user=_reader(),
        )
    assert caught.value.status_code == 403


def test_assisted_search_requires_exact_route_and_post_method() -> None:
    with pytest.raises(HTTPException):
        enforce_workspace_access(
            _request("GET", "/doc-control/workspace/t/safarilink/knowledge/assist"),
            current_user=_reader(),
        )
    with pytest.raises(HTTPException):
        enforce_workspace_access(
            _request("POST", "/doc-control/workspace/t/safarilink/knowledge/assist/admin"),
            current_user=_reader(),
        )
