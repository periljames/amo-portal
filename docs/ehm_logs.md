# EHM/ECTM Log Ingestion

This backend supports ingesting EHM/ECTM logs that contain a fixed binary header followed by a zlib-compressed, line-oriented text payload.

## Supported Log Format
- **Binary header:** default 8 bytes (skipped during decode).
- **Payload:** zlib/DEFLATE compressed text.
- **Record headers:** line oriented and typically look like:
  - `AutoTrend[0] Data at [MM/DD/YYYY HH:MM:SS.xx]:`
  - `Engine Run[0] at [MM/DD/YYYY HH:MM:SS.xx]:`
  - `Fault (Xcptn: ...) at [MM/DD/YYYY HH:MM:SS.xx]:`
  - `Sensor failure at [MM/DD/YYYY HH:MM:SS.xx]:`
  - `Event detected at [MM/DD/YYYY HH:MM:SS.xx]:`
- **Record trailer tokens:** often appear as a line like `$376B`.

## Decoding Logic
1. Read the file as bytes.
2. Attempt zlib decompression after skipping the default 8-byte header.
3. If that fails, scan for a valid zlib header (`0x78 0x01`, `0x78 0x9C`, `0x78 0xDA`) and attempt decompression from the first valid offset.
4. Decode the result as UTF-8 (replacement on invalid bytes).

## Parsing Rules
Parsed records capture:
- `record_type` and optional `index`
- `unit_time` (ISO-8601 with UTC tzinfo when parseable)
- `unit_time_raw` (original timestamp string)
- `payload_json` (key/value fields extracted from record blocks)
- `raw_text` (full original record text for auditability)
- `parse_version` (increment when parsing logic changes)

Parsing is resilient: missing fields or unexpected lines will not crash the pipeline.

## API Endpoints

### Upload
`POST /reliability/ehm/logs/upload`

Multipart form fields:
- `file` (**required**): `.log` file
- `aircraft_serial_number` (or `tail` / `aircraft_id`)
- `engine_position` (**required**)
- `engine_serial_number` (optional)
- `source` (optional)
- `notes` (optional)

Response includes a deduplication flag when a hash match already exists.

### List Logs
`GET /reliability/ehm/logs`

Filters:
- `aircraft_serial_number`
- `engine_position`
- `parse_status`
- `from`, `to` (created_at window)
- `limit`, `offset`

### Log Details
`GET /reliability/ehm/logs/{log_id}`

### Raw Text (Decompressed)
`GET /reliability/ehm/logs/{log_id}/raw-text`

### Parsed Records
`GET /reliability/ehm/logs/{log_id}/records`

Filters:
- `record_type`
- `from`, `to` (unit_time window)
- `limit`, `offset`

### Technician Snapshot
`GET /reliability/ehm/assets/{assetId}/snapshot?engine_position=LH&at=2025-03-10T12:40:00Z`

Returns:
- Identity and unit time range
- Data-quality classification (GOOD/SUSPECT/BAD) with reasons
- Latest AutoTrend summary (if present)
- Engine Run summaries
- Faults and sensor failures
- Derived interpretation placeholder
- Evidence references (log/record ids)

## Extending the Parser
To add new record types:
1. Extend header parsing in `amodb/apps/reliability/ehm.py`.
2. Add normalization logic if needed.
3. Update parser tests with new fixtures.
4. Bump `EHM_PARSE_VERSION` to enable re-parsing.
