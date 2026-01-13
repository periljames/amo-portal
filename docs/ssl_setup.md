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
