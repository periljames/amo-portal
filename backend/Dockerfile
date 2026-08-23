# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ASGI_APP=amodb.production_app:app \
    PORT=8080 \
    AMO_LICENSED_FONT_DIR=/usr/local/share/fonts/amo-licensed

WORKDIR /app

# PDF parsing libraries are Python dependencies, but DOCX/PDF fidelity also
# depends on system renderers, OCR tools and fontconfig. Microsoft/Monotype font
# files are intentionally not redistributed; licensed files may be mounted into
# AMO_LICENSED_FONT_DIR at deployment time and are indexed during startup.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    fontconfig \
    fonts-crosextra-caladea \
    fonts-crosextra-carlito \
    fonts-dejavu-core \
    fonts-liberation2 \
    fonts-noto-core \
    libpq-dev \
    libreoffice-writer \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-eng \
    && mkdir -p "${AMO_LICENSED_FONT_DIR}" \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY backend /app/backend
ENV PYTHONPATH=/app/backend

EXPOSE 8080
CMD ["sh", "-c", "fc-cache -f >/dev/null 2>&1 || true; exec python -m amodb.serve"]
