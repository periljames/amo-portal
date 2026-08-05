from __future__ import annotations

import io
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from pyxlsb import open_workbook

from . import ingestion


_original_parse_upload = ingestion.parse_upload


def _parse_xlsb(payload: bytes, filename: str, source_system: str, requested_dataset: str | None):
    parsed: list[ingestion.ParsedDataset] = []
    with open_workbook(io.BytesIO(payload)) as workbook:
        for sheet_name in workbook.sheets:
            with workbook.get_sheet(sheet_name) as sheet:
                raw_rows = [tuple(cell.v for cell in row) for row in sheet.rows()]
            if not raw_rows:
                continue
            header_index = ingestion._detect_header_row(raw_rows)
            headers = [ingestion.normalize_header(value) for value in raw_rows[header_index]]
            if not any(headers):
                continue
            rows = [
                ingestion._row_from_values(headers, values)
                for values in raw_rows[header_index + 1 : header_index + 1 + ingestion.MAX_ROWS_PER_DATASET]
                if any(value not in (None, "") for value in values)
            ]
            if not rows:
                continue
            try:
                dataset = ingestion.classify_dataset(sheet_name, headers, requested_dataset)
            except HTTPException:
                if requested_dataset:
                    raise
                continue
            parsed.append(
                ingestion.ParsedDataset(
                    dataset=dataset,
                    source_name=filename,
                    source_sheet=sheet_name,
                    headers=headers,
                    rows=rows,
                    fingerprint=ingestion.fingerprint_dataset(source_system, dataset, headers, sheet_name),
                )
            )
    return parsed


async def parse_upload(file: UploadFile, source_system: str, requested_dataset: str | None = None):
    filename = file.filename or "upload"
    if Path(filename).suffix.lower() != ".xlsb":
        return await _original_parse_upload(file, source_system, requested_dataset)

    payload = await file.read()
    if len(payload) > ingestion.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Upload exceeds 50 MB")
    try:
        parsed = _parse_xlsb(payload, filename, source_system, requested_dataset)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "XLSB_PARSE_FAILED",
                "message": "The binary workbook could not be read safely.",
                "reason": str(exc),
            },
        ) from exc
    if not parsed:
        raise HTTPException(status_code=422, detail="No classifiable induction datasets were found in the XLSB workbook")
    return parsed


ingestion.parse_upload = parse_upload
