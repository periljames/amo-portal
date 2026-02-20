# Manuals DOCX Upload Quickstart

Manuals supports direct DOCX upload from the Manuals Dashboard with an automatic preview panel.

## Route
- `GET /maintenance/:amoCode/manuals`

## Frontend flow
1. Open Manuals dashboard.
2. Fill Manual code and title.
3. Fill **Issue number (required)**, then revision number.
4. Choose a `.docx` file.
5. Review the automatic preview in the right panel.
6. Click **Upload DOCX**.
7. Click **Open reader for uploaded revision**.

## Backend endpoints
- `POST /manuals/t/{tenant_slug}/upload-docx/preview` (multipart form)
  - `file`.
  - Returns heading + paragraph count + sample lines for right-side preview.
- `POST /manuals/t/{tenant_slug}/upload-docx` (multipart form)
  - `code`, `title`, `issue_number` (required), `rev_number`, optional `manual_type`, optional `owner_role`, and `file`.

The upload endpoint creates/updates the manual, creates a draft revision, extracts DOCX text (`word/document.xml`), and stores initial section/block content so the reader has content immediately.
