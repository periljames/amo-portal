# SSL/TLS setup for the AMO Portal

This guide covers enabling HTTPS for both the backend API and the frontend dev server.
In production, SSL/TLS is typically terminated at a reverse proxy or load balancer (e.g., Nginx,
Traefik, AWS ALB), and Let’s Encrypt is commonly used to issue certificates there.

## Backend (FastAPI/Uvicorn)

The backend ships with a small launcher that wires SSL settings through to Uvicorn.

### Run with SSL

```bash
export SSL_CERTFILE=/path/to/server.crt
export SSL_KEYFILE=/path/to/server.key
# Optional
export SSL_CA_CERTS=/path/to/ca_bundle.crt
export SSL_KEYFILE_PASSWORD=changeit

python -m amodb.serve
```

### Self-signed cert for local development

```bash
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout ./certs/dev.key \
  -out ./certs/dev.crt \
  -days 365 \
  -subj "/CN=localhost"
```

Then run:

```bash
SSL_CERTFILE=./certs/dev.crt SSL_KEYFILE=./certs/dev.key python -m amodb.serve
```

## Frontend (Vite dev server)

Enable HTTPS in the Vite dev server via environment variables:

```bash
export VITE_HTTPS=true
export VITE_HTTPS_CERT_PATH=./certs/dev.crt
export VITE_HTTPS_KEY_PATH=./certs/dev.key
# Optional
export VITE_HTTPS_CA_PATH=./certs/ca_bundle.crt

npm run dev
```

If you set `VITE_HTTPS=true` without paths, Vite will start HTTPS with its default self-signed
certificate.

## Do I need to generate a certificate?

It depends on where you terminate TLS:

- **Production:** You should use a real certificate from a trusted CA. Let’s Encrypt is a great
  choice and is commonly configured at the reverse proxy/load balancer layer. In that setup, you
  typically do **not** need the app itself to terminate TLS; your proxy handles HTTPS and forwards
  plain HTTP to the app on the internal network.
- **Local development/testing:** Use a self-signed certificate (see above) or enable Vite’s
  built-in HTTPS. Browsers will warn about self-signed certs, which is expected for local usage.

If you want the FastAPI process itself to terminate TLS in production (not typical), you still
need a valid cert + key pair from a CA (Let’s Encrypt or another provider) and then set
`SSL_CERTFILE`/`SSL_KEYFILE` accordingly.

## Production checklist (recommended)

1. **Terminate TLS at a reverse proxy/load balancer** (Nginx/Traefik/ALB) with a trusted
   certificate (Let’s Encrypt). The proxy forwards plain HTTP to the app on the private network.
2. **Set CORS origins** to your HTTPS frontend origin(s), e.g.:
   ```bash
   export CORS_ALLOWED_ORIGINS="https://portal.example.com"
   ```
3. **Set the frontend API base URL** to the HTTPS backend origin:
   ```bash
   export VITE_API_BASE_URL="https://api.example.com"
   ```

## Tailscale HTTPS and public internet access

If you want access from the open internet (without adding users to your tailnet), use
**Tailscale Funnel**. A plain `https://<device>.<tailnet>.ts.net` URL is usually only reachable by
tailnet members unless Funnel is enabled for that route.

Typical setup for a local frontend running on `5173`:

```bash
# On the machine running the app
tailscale serve --https=443 http://127.0.0.1:5173
tailscale funnel 443 on
```

Then verify status:

```bash
tailscale serve status
tailscale funnel status
```

### Windows CMD full script (copy/paste)

Use this if your frontend runs on port `5173` and you want it reachable from the public internet
without inviting users to your tailnet.

```bat
@echo off
setlocal

REM 1) Start Vite so it listens on all interfaces
cd /d D:\XLK-Assets-AMO-Portal-and-DB\amo-portal\frontend
start "AMO Portal Frontend" cmd /k "npm run dev -- --host 0.0.0.0 --port 5173"

REM 2) Publish local port through Tailscale HTTPS and enable Funnel
REM    (run in an elevated cmd if required by your system policy)
tailscale serve --bg --https=443 http://127.0.0.1:5173
tailscale funnel 443 on

REM 3) Show status and the URL to test
echo.
echo ===== tailscale serve status =====
tailscale serve status
echo.
echo ===== tailscale funnel status =====
tailscale funnel status

echo.
echo Test from a network NOT logged into your tailnet:
echo   https://james.tail05da5e.ts.net/

echo.
echo If it still fails, run these checks:
echo   tailscale status
echo   tailscale netcheck

echo.
echo To disable public access later:
echo   tailscale funnel 443 off
echo   tailscale serve reset

endlocal
```

Notes:
- Funnel publishes your service publicly; anyone with the URL can reach it.
- For a stable production endpoint, prefer running a built frontend + reverse proxy rather than a
  dev server.
- If you are testing with Vite, run it with host binding (for example, `--host 0.0.0.0`) and use
  the same local port you publish through `tailscale serve`.

### Example: Nginx + Let’s Encrypt (proxying to Uvicorn)

```nginx
server {
  listen 80;
  server_name api.example.com;
  location /.well-known/acme-challenge/ { root /var/www/certbot; }
  location / { return 301 https://$host$request_uri; }
}

server {
  listen 443 ssl;
  server_name api.example.com;

  ssl_certificate /etc/letsencrypt/live/api.example.com/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;

  location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
```

Then provision/renew certs with Certbot (Let’s Encrypt). The backend launcher already enables
`proxy_headers` so forwarded proto/host are honored.
