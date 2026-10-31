# syntax=docker/dockerfile:1
# Backend image: supervisord runs the API (uvicorn) and the ADS-B ingest.
# The build context is the repo root (see infra/docker-compose.yml), so the
# root .dockerignore applies.

FROM python:3.12-slim AS base

# --- Dependencies: uv installs the locked runtime dependencies into /app/.venv ---
FROM base AS deps

# Keep in step with the uv in ci.yml and infra/Dockerfile.test.
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /bin/uv

# Copy files out of the cache mount instead of hard-linking across filesystems. Never
# download a Python: the venv must use this image's, which the runtime stage shares.
ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# The cache mount keeps uv's downloads between builds without baking them into a
# layer, so a lockfile change re-installs from local wheels. --locked installs uv.lock
# as it is but fails if pyproject.toml changed without it: a stale lock stops the Pi's
# deploy, with the old containers still serving, instead of shipping an image that
# lacks a dependency.
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# --- Runtime: no uv, no test or lint tools ---
FROM base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

COPY --from=deps /app/.venv ./.venv

COPY backend/ ./backend/
# Airport dataset used for scoring; the API refuses to start without it
COPY data/ ./data/
# FAKE_ADSB mode imports sample_data.adsb_generator
COPY sample_data/ ./sample_data/
COPY backend/supervisord.conf /app/supervisord.conf
COPY --chmod=755 backend/entrypoint.sh /app/entrypoint.sh
# Its version is the one the game reports when no BUILD_VERSION is set (backend/version.py)
COPY pyproject.toml ./

# The version the game reports. The release workflow passes the release version (the git tag
# without its v), so an image pulled as latest still names its release. Last, so a new version
# reuses every layer above.
ARG BUILD_VERSION=
ENV BUILD_VERSION=${BUILD_VERSION}

EXPOSE 8000

# The entrypoint starts the API and ingest under supervisord
CMD ["/app/entrypoint.sh"]
