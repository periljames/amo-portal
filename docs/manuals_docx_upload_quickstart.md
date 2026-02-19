# Manuals DOCX Upload Quickstart

Manuals now supports a direct DOCX upload flow from the Manuals Dashboard.

## Route
- `GET /maintenance/:amoCode/manuals`

## Frontend flow
1. Open Manuals dashboard.
2. Fill Manual code, title, revision, optional issue.
3. Choose a `.docx` file and click **Upload DOCX**.
4. Use **Open reader for uploaded revision** to open the structured HTML reader for that draft revision.

## Backend endpoint
- `POST /manuals/t/{tenant_slug}/upload-docx` (multipart form)
  - `code`, `title`, `rev_number`, optional `issue_number`, optional `manual_type`, optional `owner_role`, and `file`.

The backend creates/updates the manual, creates a draft revision, extracts text from DOCX (`word/document.xml`), and populates initial section/block content so the reader has content immediately.
