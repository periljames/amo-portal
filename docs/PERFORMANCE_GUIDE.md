# AMO Portal Performance Guide

This guide outlines how to support ultra-fast connections (100–400 Gbps) while keeping
the portal responsive on slow and high-latency networks (sub‑5 Mbps, 3G/4G, and jittery
links). It focuses on layered optimizations across edge delivery, backend handling, and
frontend performance.

## 1) Edge delivery and networking
- **CDN in front of the frontend**: Cache static assets, enable HTTP/2 + HTTP/3 (QUIC),
  and serve close to users to reduce latency.
- **TLS termination at edge**: Keep connections warm and reuse TLS sessions to minimize
  handshake overhead.
- **Cache-control for static assets**: Use long-lived cache headers for immutable, hashed
  build artifacts (e.g., `Cache-Control: public, max-age=31536000, immutable`).
- **Compression at the edge**: Use Brotli (preferred) or gzip for text assets.

## 2) Ultra-fast upload handling (100–400 Gbps)
For very high throughput, keep API servers out of the data path:
- **Direct-to-object-storage uploads**: Issue pre-signed URLs for uploads so clients send
  data straight to object storage (S3/GCS/MinIO), not through FastAPI.
- **Multipart/resumable uploads**: Support resumable chunks (S3 multipart or tus.io) to
  reduce re-transfers on failures and jitter.
- **Checksum validation**: Validate upload integrity server-side using per-part checksums.

## 3) Slow/high-latency network resilience
- **HTTP/2 multiplexing**: Avoid head-of-line blocking on slow networks.
- **Request shaping**: Prefer small JSON payloads and pagination for large lists.
- **Idempotency keys**: Make long-running or retryable operations safe to repeat.
- **Client retries with backoff**: Exponential backoff + jitter in the frontend to avoid
  thundering-herd behavior during network flaps.

## 4) Frontend performance for mobile & poor connectivity
- **Code splitting and lazy routes**: Load only what a user needs for the current page.
- **Responsive images**: Use `srcset` and modern formats (AVIF/WebP) where possible.
- **Lazy-load below-the-fold assets**: Defer non-critical images or tables.
- **Skeleton UI + optimistic updates**: Keep the app responsive even if data is delayed.
- **Offline/poor-connection support**: Cache critical reads in a service worker where
  appropriate (dashboard summaries, critical reference data).

## 5) Backend tuning and API responsiveness
- **GZip/Brotli**: Compress JSON responses to reduce payload size.
- **Async streaming for large responses**: Use streamed responses for exports or reports.
- **Worker sizing**: Tune Uvicorn/Gunicorn workers to CPU cores and workload profile.
- **DB access patterns**: Ensure indexes match high-traffic filters and pagination usage.

## 6) Suggested environment variables
These are useful defaults for upload and response tuning (adjust per environment):
- `GZIP_MINIMUM_SIZE=1024`
- `GZIP_COMPRESSLEVEL=6`
- `MAX_REQUEST_BODY_BYTES` (global Content-Length guard; set to 0 to disable)
- `PLATFORM_SETTINGS_CACHE_TTL_SEC=30` (platform settings cache for request sizing)
- `AMO_ASSET_MAX_UPLOAD_BYTES`
- `TRAINING_MAX_UPLOAD_BYTES`
- `AIRCRAFT_DOC_MAX_UPLOAD_BYTES`
- `EHM_LOG_MAX_UPLOAD_BYTES`

## 7) Quick checklist
- [ ] CDN configured with HTTP/2/3 and caching.
- [ ] Direct upload flow to object storage for large files.
- [ ] Frontend uses responsive images + lazy loading.
- [ ] API responses compressed and paginated.
- [ ] Retries/backoff for unreliable networks.
