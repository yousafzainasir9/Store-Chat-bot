# syntax=docker/dockerfile:1
# Multi-stage build using uv → small, non-root runtime image. Cloud-portable
# (same image runs on Render / Railway / Fly).

# ---- Builder: resolve + install deps into a venv with uv ----
FROM python:3.12-slim AS builder

# Bring in the uv binary from the official image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Create the runtime venv we copy into the final stage.
RUN uv venv /opt/venv

# Install dependencies first (better layer caching), then the package.
# If a uv.lock is committed, prefer reproducible installs:
#   COPY pyproject.toml uv.lock ./ && uv sync --frozen --no-dev
COPY pyproject.toml README.md ./
COPY app ./app
RUN uv pip install .

# ---- Runtime: minimal, non-root ----
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Non-root user.
RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app app ./app

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
