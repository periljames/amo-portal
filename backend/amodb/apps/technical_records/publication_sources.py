from __future__ import annotations

from datetime import date
from typing import Any


class PublicationSourceAdapter:
    source_name: str = "internal"

    def fetch(self, criteria: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError


class DeterministicPublicationSource(PublicationSourceAdapter):
    source_name = "deterministic"

    def fetch(self, criteria: dict[str, Any]) -> list[dict[str, Any]]:
        rows = [
            {"source": "FAA", "authority": "FAA", "document_type": "AD", "doc_number": "AD-2026-001", "title": "Fuel pump wiring inspection", "ata_chapter": "28", "effectivity_summary": "B737-800 fleet", "keywords": ["fuel", "wiring"], "published_date": date.today()},
            {"source": "EASA", "authority": "EASA", "document_type": "SB", "doc_number": "SB-A320-57-1245", "title": "Wing rib fastener replacement", "ata_chapter": "57", "effectivity_summary": "A320ceo", "keywords": ["wing", "fastener"], "published_date": date.today()},
        ]
        return rows


def get_publication_adapters() -> list[PublicationSourceAdapter]:
    return [DeterministicPublicationSource()]
