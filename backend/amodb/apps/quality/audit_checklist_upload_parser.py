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
CHECKLIST_PARSER_VERSION = "SOURCE_TABLE_V2"
_NUMBERED = re.compile(r"^\s*(\d{1,4})[.)]\s+(.+)$")
_HEADING = re.compile(r"^[A-Z][A-Z0-9 /()&,.:\\-]{3,120}$")
_SOURCE_SCHEME = [
    {"value": "S", "label": "S", "canonical_status": "COMPLIANT"},
    {"value": "U", "label": "U", "canonical_status": "NONCOMPLIANT"},
    {"value": "N/C", "label": "N/C", "canonical_status": "NOT_VERIFIED"},
    {"value": "N/A", "label": "N/A", "canonical_status": "NOT_APPLICABLE"},
]


def is_checklist_form_metadata(text: str) -> bool:
    """Identify form furniture, without excluding questions mentioning dates."""
    value = re.sub(r"\s+", " ", text).strip().lower().replace("\ufffd", "'")
    return bool(re.match(
        r"^(?:date\s+of\s+audit|audit\s+date|name\s+of\s+operator|auditor(?:\(s\)|s)?|location|title|assessment\s+code|name\s*(?:&|and)\s*signature|remarks|auditor.?s\s+assessment(?:\s*&\s*recommendations)?|if\s+applicable)\s*(?::|$)",
        value,
    ))


def _draft_item(number: int, section: str, prompt: str, *, paper_scheme: bool = False) -> dict[str, Any]:
    return {
        "section": section or "Uncategorised",
        "checklist_ref": str(number),
        "requirement_ref": "",
        "prompt": "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in prompt.splitlines() if line.strip())[:8000],
        "expected_evidence": "",
        "guidance": "",
        "response_type": "CUSTOM" if paper_scheme else "COMPLIANCE",
        "response_options": [dict(row) for row in _SOURCE_SCHEME] if paper_scheme else [],
        "notes_required_when": ["NOT_VERIFIED"] if paper_scheme else [],
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
    paper_scheme = False
    if doc.tables:
        for table in doc.tables:
            section = ""
            subsection = ""
            source_options: list[dict[str, str]] = []
            for row in table.rows:
                # python-docx repeats a horizontally merged cell for each grid
                # position. Use physical cells, as the Word table displays them.
                physical_cells = []
                for cell in row.cells:
                    if not physical_cells or cell._tc is not physical_cells[-1]._tc:
                        physical_cells.append(cell)
                cells = [cell.text.strip() for cell in physical_cells]
                if not cells:
                    continue
                compact = lambda text: re.sub(r"\s+", "", text).upper()
                statuses = {"YES": "COMPLIANT", "Y": "COMPLIANT", "S": "COMPLIANT",
                    "NO": "NONCOMPLIANT", "N": "NONCOMPLIANT", "U": "NONCOMPLIANT",
                    "N/A": "NOT_APPLICABLE", "N/C": "NOT_VERIFIED"}
                labels = [compact(value) for value in cells[2:] if value.strip()]
                if len(cells) >= 4 and len(labels) >= 2 and all(label in statuses for label in labels):
                    section = re.sub(r"\s+", " ", cells[1])[:128]
                    subsection = ""
                    source_options = [{"value": label, "label": label, "canonical_status": statuses[label]} for label in labels]
                    paper_scheme = labels == ["S", "U", "N/C", "N/A"]
                    continue
                unique_cells = {id(cell._tc) for cell in row.cells}
                if not section or len(unique_cells) < 3:
                    continue
                if cells[0] and not any(cells[1:]) and not is_checklist_form_metadata(cells[0]):
                    subsection = cells[0]
                    continue
                body = cells[1] if len(cells) > 1 else cells[0]
                body = body.strip()
                if not body:
                    continue
                if is_checklist_form_metadata(body):
                    continue
                if not any(cells[2:]) and all(value == body for value in cells[:2]) and "signature" in body.lower():
                    continue
                # Skip non-checklist audit identity metadata tables.
                if len(cells) < 3:
                    continue
                # python-docx repeats merged cells across their grid span. A
                # full-width footer/signature box is not six answer columns.
                if len({id(cell._tc) for cell in row.cells}) < 3:
                    continue
                # Headings without response columns and no question mark are
                # ambiguous, so keep them for explicit reviewer correction.
                explicit = _NUMBERED.match(body)
                source_number = re.fullmatch(r"(\d{1,4}(?:\.\d+)*)(?:[.)])?", compact(cells[0]))
                if not source_number and not explicit and (cells[0] or not paper_scheme):
                    continue
                number = source_number.group(1) if source_number else int(explicit.group(1)) if explicit else len(items) + 1
                prompt = explicit.group(2) if explicit else body
                if len(prompt) > 4:
                    item = _draft_item(number, f"{section} / {subsection}" if subsection else section, prompt, paper_scheme=paper_scheme)
                    if source_options:
                        item["response_type"] = "CUSTOM"
                        item["response_options"] = [dict(option) for option in source_options]
                    items.append(item)
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
    import fitz

    try:
        reader = fitz.open(stream=data, filetype="pdf")
    except (fitz.FileDataError, ValueError) as exc:
        raise ValueError("The PDF is invalid or cannot be opened.") from exc
    if reader.needs_pass:
        reader.close()
        raise ValueError("Password-protected PDFs cannot be imported. Provide an accessible controlled copy.")
    if len(reader) > 120:
        reader.close()
        raise ValueError("The PDF has too many pages for checklist drafting.")
    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    section = ""
    paper_scheme = False
    pending: dict[str, Any] | None = None
    # The assessment-column suffix is evidence for the source vocabulary.
    # It is not safe to map abbreviated answers without this explicit header.
    header = re.compile(r"^(.*?)\s+S\s+U\s+N/C\s+N/A\s*$", re.IGNORECASE)
    ignore_prefix = (
        "sl/qms/", "page ", "form №:", "form no", "revision:",
        "issued ", "name & signature", "name and signature",
        "auditor's assessment", "auditor’s assessment",
    )
    ignore_exact = {"Contractors Audit", "Audit Checklist"}

    def flush() -> None:
        nonlocal pending
        if pending is not None:
            items.append(pending)
            pending = None

    for page_number, page in enumerate(reader, 1):
        content = page.get_text("text") or ""
        if not content.strip():
            warnings.append(f"Page {page_number}: no selectable text; scanned-page OCR is not performed.")
            continue
        raw_lines = [re.sub(r"\s+", " ", raw).strip() for raw in content.splitlines()]
        lines: list[str] = []
        cursor = 0
        while cursor < len(raw_lines):
            token = raw_lines[cursor]
            if [part.upper() for part in raw_lines[cursor:cursor + 4]] == ["S", "U", "N/C", "N/A"]:
                lines.append("S U N/C N/A")
                cursor += 4
                continue
            if re.fullmatch(r"\d{1,4}[.)]", token) and cursor + 1 < len(raw_lines):
                lines.append(token + " " + raw_lines[cursor + 1])
                cursor += 2
                continue
            lines.append(token)
            cursor += 1
        i = 0
        while i < len(lines):
            line = lines[i]
            if not line:
                i += 1
                continue
            if is_checklist_form_metadata(line):
                flush()
                i += 1
                continue
            if line.lower().startswith("remarks:"):
                flush()
                i += 1
                continue
            if line in ignore_exact or line.lower().startswith(ignore_prefix):
                i += 1
                continue
            section_match = header.fullmatch(line)
            if section_match:
                flush()
                section = section_match.group(1).strip()[:128]
                paper_scheme = True
                i += 1
                continue
            # In PDFs a wide section heading and its S/U/N/C/N/A labels
            # may wrap over up to three physical lines. Use the explicit
            # assessment header as an anchor before classifying the text.
            wrapped_heading = False
            for length in (1, 2, 3):
                last = i + length
                if last >= len(lines) or lines[last].upper() != "S U N/C N/A":
                    continue
                fragments = lines[i:last]
                if all(part and not _NUMBERED.match(part) and not part.startswith(("*", "•")) for part in fragments):
                    flush()
                    section = " ".join(fragments)[:128]
                    paper_scheme = True
                    i = last + 1
                    wrapped_heading = True
                    break
            if wrapped_heading:
                continue
            if (match := _NUMBERED.match(line)):
                flush()
                pending = _draft_item(int(match.group(1)), section, match.group(2), paper_scheme=paper_scheme)
                i += 1
                continue
            if pending is None and _HEADING.fullmatch(line) and len(line) >= 6:
                section = line[:128]
                paper_scheme = False
                i += 1
                continue
            if pending is not None:
                # Preserve wrapped audit criteria, including continuations
                # across page boundaries, instead of dropping their text.
                proposed = f"{pending['prompt']} {line}"
                pending["prompt"] = re.sub(r"\s+", " ", proposed)[:8000]
            i += 1
    flush()
    reader.close()
    return items, warnings

def draft_from_upload(data: bytes, filename: str) -> dict[str, Any]:
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Choose a nonempty Word or PDF checklist under 10 MB.")
    suffix = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    if suffix == "docx":
        if not data.startswith(b"PK"):
            raise ValueError("This file is not a valid DOCX.")
        try:
            items, warnings = _word_items(data)
        except Exception as error:
            raise ValueError("The DOCX checklist could not be read. Upload an intact Word document.") from error
    elif suffix == "pdf":
        if not data.startswith(b"%PDF"):
            raise ValueError("This file is not a valid PDF.")
        try:
            items, warnings = _pdf_items(data)
        except Exception as error:
            raise ValueError("The PDF checklist could not be read. Upload an intact, selectable-text PDF.") from error
        warnings.append("Confirm PDF section boundaries, wrapped text and assessment-column mapping in the draft editor.")
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
