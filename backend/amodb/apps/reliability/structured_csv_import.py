from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_write_db
from amodb.security import get_current_active_user

from . import workbook_parity as wp
from . import workbook_parity_imports as imports

CSV_PROFILE_CODE = "STRUCTURED-CSV"
MAX_UPLOAD_BYTES = imports.MAX_UPLOAD_BYTES
MAX_PREVIEW_ROWS = imports.MAX_PREVIEW_ROWS
ALLOWED_EXTENSIONS = {".csv", ".tsv"}
ALLOWED_MIME_TYPES = {
    "text/csv",
    "text/tab-separated-values",
    "text/plain",
    "application/csv",
    "application/vnd.ms-excel",
    "application/octet-stream",
}


@dataclass(frozen=True)
class CsvCell:
    value: Any
    data_type: str = "s"


def csv_headers(dataset_code: wp.WorkbookDatasetCode) -> list[str]:
    definition = wp.DATASET_CATALOG[dataset_code]
    common = [
        "event_date",
        "event_end_date",
        "aircraft_serial_number",
        "ata_chapter",
        "reference_code",
        "title",
        "description",
    ]
    if dataset_code == wp.WorkbookDatasetCode.AI:
        common.remove("aircraft_serial_number")
    return [*common, *(field.key for field in definition.fields)]


def _decode_csv(content: bytes) -> str:
    if b"\x00" in content:
        raise ValueError("Structured CSV must be plain text and cannot contain NUL bytes.")
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Structured CSV must use UTF-8 encoding.") from exc


def _delimiter(filename: str, sample: str, requested: str | None) -> str:
    if requested:
        names = {"comma": ",", "semicolon": ";", "tab": "\t", "pipe": "|"}
        value = names.get(requested.lower(), requested)
        if value not in {",", ";", "\t", "|"}:
            raise ValueError("Delimiter must be comma, semicolon, tab or pipe.")
        return value
    if Path(filename).suffix.lower() == ".tsv":
        return "\t"
    try:
        return csv.Sniffer().sniff(sample[:8192], delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _rows(text: str, delimiter: str) -> list[list[str]]:
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    return [list(row) for row in reader]


def register(router: APIRouter) -> None:
    @router.get("/workbook-parity/imports/csv-template", response_class=Response)
    def csv_template(
        dataset_code: wp.WorkbookDatasetCode = Query(...),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        imports._amo_id(current_user)
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow(csv_headers(dataset_code))
        writer.writerow(["" for _ in csv_headers(dataset_code)])
        body = buffer.getvalue()
        return Response(
            content=body,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="reliability-{dataset_code.value.lower()}-template.csv"'},
        )

    @router.post("/workbook-parity/imports/csv-preview", status_code=201)
    async def preview_csv(
        dataset_code: wp.WorkbookDatasetCode = Form(...),
        delimiter: str | None = Form(default=None),
        header_row: int = Form(default=1, ge=1, le=100),
        source: UploadFile = File(...),
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = imports._amo_id(current_user)
        imports._require_import_permission(current_user)
        sanitized = imports._sanitize_filename(source.filename or "reliability.csv")
        extension = Path(sanitized).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=415, detail="Structured intake accepts only .csv or .tsv files.")
        content_type = (source.content_type or "").lower().split(";", 1)[0]
        if content_type and content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(status_code=415, detail="The upload MIME type is not accepted for structured CSV intake.")
        content = await source.read(MAX_UPLOAD_BYTES + 1)
        if not content:
            raise HTTPException(status_code=422, detail="The uploaded CSV is empty.")
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Structured CSV uploads are limited to 25 MiB.")
        try:
            text = _decode_csv(content)
            separator = _delimiter(sanitized, text, delimiter)
            matrix = _rows(text, separator)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if header_row > len(matrix):
            raise HTTPException(status_code=422, detail="Header row is beyond the end of the CSV file.")

        headers = matrix[header_row - 1]
        definition = wp.DATASET_CATALOG[dataset_code]
        aliases = imports._candidate_aliases(db, amo_id, CSV_PROFILE_CODE, dataset_code, "CSV")
        header_map, header_errors = imports._match_headers(headers, aliases)
        required = {field.key for field in definition.fields if field.required} | {"event_date"}
        if dataset_code != wp.WorkbookDatasetCode.AI:
            required.add("aircraft_serial_number")
        missing = sorted(required - set(header_map.values()))
        if header_errors or missing:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "CSV headers do not satisfy the controlled mapping.",
                    "header_errors": header_errors,
                    "missing_required_fields": missing,
                    "header_map": header_map,
                    "headers": headers,
                    "expected_template_headers": csv_headers(dataset_code),
                },
            )

        source_hash = hashlib.sha256(content).hexdigest()
        selected_sheet = f"CSV-{dataset_code.value}"
        existing = db.query(imports.ReliabilityWorkbookImportBatch).filter(
            imports.ReliabilityWorkbookImportBatch.amo_id == amo_id,
            imports.ReliabilityWorkbookImportBatch.profile_code == CSV_PROFILE_CODE,
            imports.ReliabilityWorkbookImportBatch.dataset_code == dataset_code.value,
            imports.ReliabilityWorkbookImportBatch.selected_sheet == selected_sheet,
            imports.ReliabilityWorkbookImportBatch.source_hash == source_hash,
        ).one_or_none()
        if existing:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "This structured CSV has already been previewed for this dataset.",
                    "batch_id": existing.id,
                    "status": existing.status,
                },
            )

        data_rows = [row for row in matrix[header_row:] if any(str(value).strip() for value in row)]
        if not data_rows:
            raise HTTPException(status_code=422, detail="The CSV contains no non-empty data rows after the header.")
        if len(data_rows) > MAX_PREVIEW_ROWS:
            raise HTTPException(status_code=422, detail="Structured CSV preview is limited to 10,000 non-empty rows. Split the source into controlled batches.")

        batch = imports.ReliabilityWorkbookImportBatch(
            amo_id=amo_id,
            profile_code=CSV_PROFILE_CODE,
            dataset_code=dataset_code.value,
            original_filename=(source.filename or sanitized)[:255],
            sanitized_filename=sanitized,
            file_extension=extension,
            file_size_bytes=len(content),
            source_hash=source_hash,
            status="PREVIEW_READY",
            detected_sheets=[{
                "name": "CSV",
                "state": "visible",
                "max_row": len(matrix),
                "max_column": max((len(row) for row in matrix), default=0),
                "format": "STRUCTURED_CSV",
                "delimiter": {",": "comma", ";": "semicolon", "\t": "tab", "|": "pipe"}[separator],
            }],
            selected_sheet=selected_sheet,
            header_row=header_row,
            header_map=header_map,
            created_by_user_id=current_user.id,
        )
        db.add(batch)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail="This structured CSV source has already been previewed.") from exc

        valid = invalid = 0
        for position, row in enumerate(data_rows, start=header_row + 1):
            cells = tuple(CsvCell(value=value) for value in row)
            raw, mapped, errors, row_hash = imports._build_preview_row(
                dataset_code,
                definition,
                position,
                cells,
                header_map,
                source_hash,
                selected_sheet,
            )
            status = "INVALID" if errors else "VALID"
            valid += int(status == "VALID")
            invalid += int(status == "INVALID")
            db.add(imports.ReliabilityWorkbookImportRowResult(
                batch_id=batch.id,
                row_number=position,
                row_source_hash=row_hash,
                raw_values=raw,
                mapped_values=mapped,
                errors=errors,
                status=status,
            ))
        batch.total_rows = len(data_rows)
        batch.valid_rows = valid
        batch.invalid_rows = invalid
        db.commit()
        db.refresh(batch)
        preview_rows = db.query(imports.ReliabilityWorkbookImportRowResult).filter(
            imports.ReliabilityWorkbookImportRowResult.batch_id == batch.id
        ).order_by(imports.ReliabilityWorkbookImportRowResult.row_number).limit(200).all()
        return {
            **imports._batch_dict(batch),
            "preview_rows": [
                {
                    "id": row.id,
                    "row_number": row.row_number,
                    "status": row.status,
                    "raw_values": row.raw_values,
                    "mapped_values": row.mapped_values,
                    "errors": row.errors,
                    "row_source_hash": row.row_source_hash,
                }
                for row in preview_rows
            ],
            "preview_truncated": len(data_rows) > 200,
            "format": "STRUCTURED_CSV",
        }
