# PERFORMANCE PLAN

## 1) Performance targets

Because `portal_spec.md` is unavailable, the following are placeholders:
- API p95 latency target: `UNKNOWN__FILL_ME`
- API p99 latency target: `UNKNOWN__FILL_ME`
- Upload completion SLO: `UNKNOWN__FILL_ME`
- Streaming reconnect SLO: `UNKNOWN__FILL_ME`

`ASSUMPTION__REVIEW`: Start measuring with p95/p99 by route family and set SLOs after 7 days baseline.

## 2) Bottleneck checklist

- DB connection pool saturation (`DB_POOL_SIZE`, overflow, wait time).
- Upload path disk IO saturation on APP temp storage.
- SSE connection fan-out and idle timeout churn.
- Broker publish backlog when realtime enabled.
- Frontend static asset cache misses / cold starts.

## 3) NGINX route group policy

| Route group | Buffering policy | Body size | Timeout policy | Notes |
|---|---|---|---|---|
| `/` frontend | `proxy_buffering on` | small bodies | standard timeouts | Cache static assets aggressively. |
| `/api` standard | request buffering on | `client_max_body_size UNKNOWN__FILL_ME` | medium API timeouts | Default JSON API traffic. |
| `/api/upload` | `proxy_request_buffering off` `ASSUMPTION__REVIEW` | `client_max_body_size UNKNOWN__FILL_ME` | longer read/send timeout | Avoid buffering huge bodies on EDGE disk. |
| `/api/stream` mapped to `/api/events` | `proxy_buffering off` | tiny | long read timeout | Required for SSE/event stream behavior. |
| `/mqtt` (if used) | websocket upgrade; buffering off | tiny | long idle/read timeout | Confirmed from existing docs snippet, backend does not expose native ws endpoint. |

## 4) Upload strategy

Confirmed: multiple FastAPI `UploadFile` routes exist.

Plan:
- Keep APP local fast temp path for in-flight multipart handling.
- Apply route-level limits in backend env and NGINX.
- Persist durable artifacts to NAS-backed path asynchronously where possible.
- Add checksum/size logging for postmortems.

`UNKNOWN__FILL_ME`: max upload size, expected concurrency, resumable upload requirement.

## 5) Streaming strategy

Confirmed SSE endpoint: `/api/events` with replay support (`lastEventId`).

Plan:
- Disable proxy buffering on stream path.
- Set read timeout sufficiently above heartbeat interval.
- Keep keepalive enabled; propagate disconnect code mapping.
- Track reconnect rate and event lag metrics.

## 6) Caching strategy

### HTTP edge caching
- Cache frontend static files with immutable fingerprint headers.
- Do not cache authenticated API responses by default.
- Consider micro-cache for unauthenticated health/docs endpoints `ASSUMPTION__REVIEW`.

### App-level caching
- Maintain short TTL for platform settings cache (already present in backend).
- Evaluate tenant metadata cache with strict invalidation hooks `UNKNOWN__FILL_ME`.

## 7) What to measure

Minimum dashboards:
- Request volume, error rate, p50/p95/p99 per route group.
- DB query latency and pool checkout wait.
- Upload throughput and 413/5xx error ratios.
- SSE active connections + reconnect attempts.
- Broker connection state from `/healthz` output.
