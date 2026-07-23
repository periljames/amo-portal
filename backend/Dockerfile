# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ASGI_APP=amodb.main:app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY backend /app/backend
ENV PYTHONPATH=/app/backend

EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn \"${ASGI_APP}\" --host 0.0.0.0 --port \"${PORT:-8080}\""]
