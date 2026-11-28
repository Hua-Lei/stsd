# syntax=docker/dockerfile:1

FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.3 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "-m", "stsd.worker"]
