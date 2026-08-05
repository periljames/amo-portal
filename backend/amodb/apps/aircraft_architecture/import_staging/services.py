from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Callable, Iterable

HEADER_PATTERN = re.compile(r"[^a-z0-9]+")
REQUIRED_ADAPTERS = (
    "CSV", "EXCEL", "WINAIR", "AMOS", "TRAX", "RAMCO", "SPEC2000", "SPEC2300",
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalize_header(value: Any) -> str:
    normalized = HEADER_PATTERN.sub("_", str(value or "").strip().casefold()).strip("_")
    if not normalized:
        raise ValueError("blank import header is not allowed")
    return normalized


def normalize_headers(headers: Iterable[Any]) -> tuple[str, ...]:
    values = tuple(normalize_header(item) for item in headers)
    if len(values) != len(set(values)):
        raise ValueError("headers collide after normalization")
    return values


def header_fingerprint(headers: Iterable[Any]) -> str:
    return sha256_json(sorted(normalize_headers(headers)))


def parse_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("boolean is not a valid fixed-precision number")
    if isinstance(value, float):
        raise ValueError("binary floating-point input is not accepted; provide a string or integer")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid fixed-precision number: {value!r}") from exc
    if not parsed.is_finite():
        raise ValueError("non-finite numbers are not accepted")
    return parsed


@dataclass(frozen=True)
class DatasetInput:
    dataset_kind: str
    adapter_code: str
    file_name: str
    content_hash: str
    headers: tuple[str, ...]
    row_count: int = 0

    def manifest(self) -> dict[str, Any]:
        return {
            "dataset_kind": self.dataset_kind.strip().upper(),
            "adapter_code": self.adapter_code.strip().upper(),
            "file_name": self.file_name,
            "content_hash": self.content_hash.lower(),
            "header_fingerprint": header_fingerprint(self.headers),
            "row_count": self.row_count,
        }


def build_batch_manifest(source_system: str, datasets: Iterable[DatasetInput]) -> dict[str, Any]:
    rows = [dataset.manifest() for dataset in datasets]
    if not rows:
        raise ValueError("at least one dataset is required")
    identities = [(row["dataset_kind"], row["content_hash"]) for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate dataset content in batch")
    return {
        "source_system": source_system.strip().upper(),
        "datasets": sorted(rows, key=lambda row: (row["dataset_kind"], row["file_name"], row["content_hash"])),
    }


def batch_manifest_hash(source_system: str, datasets: Iterable[DatasetInput]) -> str:
    return sha256_json(build_batch_manifest(source_system, datasets))


def row_hash(source_row: dict[str, Any], normalized_row: dict[str, Any]) -> str:
    return sha256_json({"source": source_row, "normalized": normalized_row})


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, Callable[[Any], Any]] = {}

    def register(self, code: str, adapter: Callable[[Any], Any]) -> None:
        key = code.strip().upper()
        if not key:
            raise ValueError("adapter code is required")
        if key in self._adapters:
            raise ValueError(f"adapter already registered: {key}")
        self._adapters[key] = adapter

    def resolve(self, code: str) -> Callable[[Any], Any]:
        key = code.strip().upper()
        try:
            return self._adapters[key]
        except KeyError as exc:
            raise ValueError(f"unsupported aircraft import adapter: {key}") from exc

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))


def default_adapter_registry() -> AdapterRegistry:
    registry = AdapterRegistry()
    for code in REQUIRED_ADAPTERS:
        registry.register(code, lambda payload, adapter_code=code: {"adapter": adapter_code, "payload": payload})
    return registry
