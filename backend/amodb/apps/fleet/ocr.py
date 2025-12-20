from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import csv
import re
from pathlib import Path
from statistics import mean
from typing import Iterable, Sequence

from PIL import Image


class OCRDependencyError(RuntimeError):
    pass


@dataclass
class OCRTable:
    headers: list[str]
    rows: list[list[str]]
    text: str
    confidence: float | None
    samples: list[str]


def detect_file_type(content: bytes, filename: str | None) -> str:
    if content.startswith(b"%PDF"):
        return "pdf"

    suffix = Path(filename or "").suffix.lower()
    if suffix in {".csv", ".txt"}:
        return "csv"
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        return "excel"

    try:
        Image.open(BytesIO(content))
    except Exception:
        pass
    else:
        return "image"

    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}:
        return "image"

    return "unknown"


def _load_tesseract():
    try:
        import pytesseract  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise OCRDependencyError(
            "pytesseract is required for OCR. Install with 'pip install pytesseract'."
        ) from exc
    return pytesseract


def _load_pdf_converter():
    try:
        from pdf2image import convert_from_bytes  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise OCRDependencyError(
            "pdf2image is required for PDF OCR. Install with 'pip install pdf2image'."
        ) from exc
    return convert_from_bytes


def _extract_images(content: bytes, file_type: str) -> list[Image.Image]:
    if file_type == "image":
        return [Image.open(BytesIO(content))]
    if file_type == "pdf":
        convert_from_bytes = _load_pdf_converter()
        return convert_from_bytes(content)
    raise ValueError(f"Unsupported OCR file type '{file_type}'.")


def _extract_confidence(data: dict) -> float | None:
    confs: list[float] = []
    for val in data.get("conf", []):
        try:
            parsed = float(val)
        except (TypeError, ValueError):
            continue
        if parsed >= 0:
            confs.append(parsed)
    if not confs:
        return None
    return mean(confs)


def _extract_text_samples(text: str, max_samples: int = 5) -> list[str]:
    samples: list[str] = []
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned:
            samples.append(cleaned)
        if len(samples) >= max_samples:
            break
    return samples


def extract_table_from_bytes(content: bytes, file_type: str) -> OCRTable:
    pytesseract = _load_tesseract()

    images = _extract_images(content, file_type)
    texts: list[str] = []
    confidences: list[float] = []

    for image in images:
        text = pytesseract.image_to_string(image)
        texts.append(text)
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        conf = _extract_confidence(data)
        if conf is not None:
            confidences.append(conf)

    combined_text = "\n".join([t for t in texts if t])
    headers, rows = parse_ocr_table(combined_text)

    confidence = mean(confidences) if confidences else None
    samples = _extract_text_samples(combined_text)
    return OCRTable(
        headers=headers,
        rows=rows,
        text=combined_text,
        confidence=confidence,
        samples=samples,
    )


def _dedupe_headers(headers: Sequence[str]) -> list[str]:
    counts: dict[str, int] = {}
    cleaned: list[str] = []
    for header in headers:
        base = header.strip() or "column"
        count = counts.get(base, 0)
        counts[base] = count + 1
        cleaned.append(f"{base}_{count + 1}" if count else base)
    return cleaned


def _strip_empty(rows: Iterable[list[str]]) -> list[list[str]]:
    cleaned: list[list[str]] = []
    for row in rows:
        if any(cell.strip() for cell in row):
            cleaned.append([cell.strip() for cell in row])
    return cleaned


def parse_ocr_table(text: str) -> tuple[list[str], list[list[str]]]:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return [], []

    sniff_sample = "\n".join(lines[:5])
    delimiter: str | None = None
    try:
        dialect = csv.Sniffer().sniff(sniff_sample, delimiters=[",", "\t", ";", "|"])
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = None

    parsed_rows: list[list[str]] = []
    if delimiter:
        reader = csv.reader(lines, delimiter=delimiter)
        parsed_rows = [[cell.strip() for cell in row] for row in reader]
    else:
        for line in lines:
            parsed_rows.append([cell for cell in re.split(r"\s{2,}", line) if cell])

    if not parsed_rows:
        return [], []

    headers = _dedupe_headers(parsed_rows[0])
    rows = parsed_rows[1:]
    padded_rows: list[list[str]] = []
    for row in rows:
        padded = row[: len(headers)]
        if len(padded) < len(headers):
            padded = padded + [""] * (len(headers) - len(padded))
        padded_rows.append(padded)

    return headers, _strip_empty(padded_rows)
