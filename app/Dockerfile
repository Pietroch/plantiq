# app/Dockerfile

FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY app/pyproject.toml .
RUN mkdir -p src && pip install --no-cache-dir -e ".[dev]"

COPY app/src/ ./src/
COPY app/tests/ ./tests/
