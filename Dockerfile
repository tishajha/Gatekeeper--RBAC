# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# GateKeeper RBAC Execution Platform — Dockerfile
#
# Multi-stage build:
#   1. `builder` stage installs build deps and compiles wheels.
#   2. `runtime` stage copies just the wheels into a slim base, keeping
#      the final image small and free of compiler toolchains.
#
# Build:    docker build -t gatekeeper:latest .
# Run:      docker run --rm -p 8000:8000 gatekeeper:latest
# Compose:  docker compose up --build
# ---------------------------------------------------------------------------

# ----- Stage 1: builder ----------------------------------------------------
FROM python:3.12-slim AS builder

# Standard Python hardening for containers:
#   - PYTHONDONTWRITEBYTECODE=1: skip .pyc files (bind-mount-friendly, smaller layer)
#   - PYTHONUNBUFFERED=1:        flush prints immediately (logs work in `docker logs`)
#   - PIP_NO_CACHE_DIR=1:        no pip cache, smaller layer
#   - PIP_DISABLE_PIP_VERSION_CHECK=1: skip the "newer pip available" message
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build deps for bcrypt (Rust-based) and any wheels that need compiling.
# These are NOT carried into the runtime stage.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy only requirements first so this layer is cached as long as the
# dependency list is stable. Source code changes won't bust this cache.
COPY requirements.txt ./

# Build wheels into /wheels — copied into the runtime stage in one shot.
RUN pip wheel --wheel-dir /wheels -r requirements.txt


# ----- Stage 2: runtime ----------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Make `python -m app.x` find the package without setting PYTHONPATH everywhere
    PYTHONPATH=/app

# Create a non-root user. Running as root inside containers is a common
# vulnerability — if the app is exploited, the attacker gets a low-privilege
# shell, not root.
RUN groupadd --system --gid 1001 gatekeeper \
 && useradd  --system --uid 1001 --gid gatekeeper --create-home gatekeeper

WORKDIR /app

# Install pre-built wheels from the builder stage. No compiler needed here.
COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels /wheels/*.whl \
 && rm -rf /wheels

# Copy the application source. .dockerignore keeps caches, venvs, secrets,
# and the local SQLite file out of the image.
COPY --chown=gatekeeper:gatekeeper app/    ./app/

# Drop root before running the app.
USER gatekeeper

# Document the port. EXPOSE is informational; -p on `docker run` is what
# actually publishes the port.
EXPOSE 8000

# Healthcheck so orchestrators (Compose, Kubernetes) can tell when the
# container is actually ready, not just running.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
                   sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else sys.exit(1)"

# Seed the DB on startup, then launch uvicorn.
# `sh -c` so the && chain works; `exec` ensures uvicorn is PID 1 and
# receives SIGTERM correctly on `docker stop`.
CMD ["sh", "-c", "python -m app.seed && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
