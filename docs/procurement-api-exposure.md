# Procurement API Exposure

The authenticated tenant API root is `/api/maintenance/{amo_code}/procurement`.

The evidence endpoints are registered through the existing Inventory and supply-chain application router:

- `GET /documents`
- `POST /documents`
- `GET /documents/{document_id}/download`
- `POST /documents/{document_id}/verify`
- `POST /documents/{document_id}/void`

All operations resolve the tenant from the authenticated user and AMO code. Upload and control mutations use explicit role restrictions.
