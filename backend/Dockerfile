# Build from the repository root: docker build -f backend/Dockerfile .
FROM ghcr.io/astral-sh/uv:0.9.7 AS uv
FROM python:3.13-slim AS builder
COPY --from=uv /uv /bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/app ./app
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH="/app/backend/.venv/bin:$PATH" STAYTUS_CONFIG_DIR=/app/config
RUN useradd --uid 10001 --create-home staytus
WORKDIR /app/backend
COPY --from=builder --chown=staytus:staytus /app/backend/.venv ./.venv
COPY --chown=staytus:staytus config /app/config
USER staytus
EXPOSE 8000
ENTRYPOINT ["python", "-m", "app.container_entrypoint"]
CMD ["api"]
