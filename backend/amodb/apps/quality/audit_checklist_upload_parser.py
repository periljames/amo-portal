"""Extract editable audit checklist candidates from Word/PDF without issuing a revision.

A deterministic draft parser: no AI-generated questions or inferred compliance.
The reviewer must reconcile question wording, sections and numbering before issue.
"""
from __future__ import annotations

import hashlib
import io
import re
from typing import Any

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_NUMBERED = re.compile(r"^\\s*(\\d{1,4})[.)]\\s+(.+)$")
_HEADING = re.compile(r"^[A-Z][A-Z0-9 /()&,.:\\-]{3,120}$")
_SOURCE_SCHEME = [
    {"value": "S", "label": "S", "canonical_status": "COMPLIANT"},
    {"value": "U", "label": "U", "canonical_status": "NONCOMPLIANT"},
    {"value": "N/C", "label": "N/C", "canonical_status": "NOT_VERIFIED"},
    {"value": "N/A", "label": "N/A", "canonical_status": "NOT_APPLICABLE"},
]


def _draft_item(number: int, section: str, prompt: str) -> dict[str, Any]:
    return {
        "section": section or "Uncategorised",
        "checklist_ref": str(number),
        "requirement_ref": "",
        "prompt": re.sub(r"\\s+", " ", prompt).strip()[:8000],
        "expected_evidence": "",
        "guidance": "",
        "response_type": "CUSTOM",
        "response_options": [dict(row) for row in _SOURCE_SCHEME],
        "notes_required_when": ["NOT_VERIFIED"],
        "na_justification_required": True,
        "applicability": "APPLICABLE",
        "mandatory": True,
    }


def _word_items(data: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    from docx import Document

    doc = Document(io.BytesIO(data))
    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    section = ""
    if doc.tables:
        for table in doc.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                if not cells:
                    continue
                body = cells[1] if len(cells) > 1 else cells[0]
                body = body.strip()
                if not body:
                    continue
                # In tabular controlled checklists, heading rows carry the
                # assessment-column titles. Autonumbered cells can be blank.
                if len(cells) >= 4 and cells[2].strip().upper() in {"S", "YES", "Y"} and cells[3].strip().upper() in {"U", "NO", "N"}:
                    section = re.sub(r"\\s+", " ", body)[:128]
                    continue
                if body.lower().startswith(("remarks:", "auditor's assessment", "auditor’s assessment", "name & signature")):
                    continue
                if not any(cells[2:]) and all(value == body for value in cells[:2]) and "signature" in body.lower():
                    continue
                # Skip non-checklist audit identity metadata tables.
                if len(cells) < 3:
                    continue
                # Headings without response columns and no question mark are
                # ambiguous, so keep them for explicit reviewer correction.
                explicit = _NUMBERED.match(body)
                number = int(explicit.group(1)) if explicit else len(items) + 1
                prompt = explicit.group(2) if explicit else body
                if len(prompt) > 4:
                    items.append(_draft_item(number, section, prompt))
    else:
        warnings.append("No Word table was found; paragraph-number detection may need manual review.")
        section = ""
        for paragraph in doc.paragraphs:
            line = paragraph.text.strip()
            if _HEADING.fullmatch(line):
                section = line[:128]
            elif (match := _NUMBERED.match(line)):
                items.append(_draft_item(int(match.group(1)), section, match.group(2)))
    return items, warnings


def _pdf_items(data: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise ValueError("Password-protected PDFs cannot be imported. Provide an accessible controlled copy.")
    if len(reader.pages) > 120:
        raise ValueError("The PDF has too many pages for checklist drafting.")
    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    section = ""
    for page_number, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        if not text.strip():
            warnings.append(f"Page {page_number}: no selectable text; scanned-page OCR is not performed.")
            continue
        for raw in text.splitlines():
            line = re.sub(r"\\s+", " ", raw).strip()
            if _HEADING.fullmatch(line) and line not in {"S", "U", "N/C", "N/A"}:
                section = line[:128]
                continue
            match = _NUMBERED.match(line)
            if match:
                items.append(_draft_item(int(match.group(1)), section, match.group(2)))
            elif items and line and not line.lower().startswith(("remarks", "page ", "sl/qms/", "revision:", "issued")):
                # Do not invent a new question from an unnumbered PDF line.
                # An auditor must review the source for missed/continuation rows.
                continue
    return items, warnings


def draft_from_upload(data: bytes, filename: str) -> dict[str, Any]:
    name = filename.rsplit("/", 1)[-1].rsplit("\\\\", 1)[-1]
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Choose a nonempty Word or PDF checklist under 10 MB.")
    suffix = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    if suffix == "docx":
        if not data.startswith(b"PK"):
            raise ValueError("This file is not a valid DOCX.")
        items, warnings = _word_items(data)
    elif suffix == "pdf":
        if not data.startswith(b"%PDF"):
            raise ValueError("This file is not a valid PDF.")
        items, warnings = _pdf_items(data)
    else:
        raise ValueError("Only .docx and .pdf checklists are supported.")
    if not items:
        raise ValueError("No checklist questions could be identified. Use a selectable-text PDF or tabular Word checklist, or enter questions manually.")
    if len(items) > 1000:
        raise ValueError("More than 1,000 candidates were found; split or simplify the source and review it before issue.")
    numbers = [item["checklist_ref"] for item in items]
    if len(set(numbers)) != len(numbers):
        warnings.append("Question numbers repeat; review the source numbering before issuing.")
    if any(item["section"] == "Uncategorised" for item in items):
        warnings.append("Some questions have no detected section; assign their correct source heading.")
    warnings.append("Draft only: verify every extracted question, section, number and assessment mapping before committing.")
    warnings.append("N/C is preserved as a source choice and mapped to NOT_VERIFIED; it does not satisfy mandatory fieldwork completion.")
    return {
        "filename": name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "items": items,
        "question_count": len(items),
        "section_count": len({item["section"] for item in items}),
        "warnings": warnings,
    }
