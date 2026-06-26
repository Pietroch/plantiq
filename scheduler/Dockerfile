# scheduler/Dockerfile

FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY scheduler/pyproject.toml .
RUN mkdir -p src && pip install --no-cache-dir -e ".[dev]"

COPY scheduler/src/ ./src/
COPY scheduler/tests/ ./tests/

CMD ["python", "-m", "plantiq.run"]
