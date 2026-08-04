# Procurement Evidence Data Contract

Each retained evidence record is tenant-scoped and linked to one Procurement entity: requisition, RFQ, quotation, purchase order, receipt, supplier, or Quality hold.

Supported sources:

- uploaded retained file
- signed physical form or register entry
- controlled DMS document and revision
- external software or supplier-portal record
- email or other traceable source

Uploaded files retain the original filename, MIME type, byte size, SHA-256 digest and controlled storage path. Reference-only records retain the physical location, external reference or DMS identifiers without requiring a duplicate upload.

Quality evidence enters `PENDING` verification. Only Quality-authorized roles can mark it `VERIFIED` or `REJECTED`. Voiding changes the evidence status and records the reason; it does not delete the retained file or audit history.
