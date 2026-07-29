FROM python:3.13.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN groupadd --system app && useradd --system --gid app --home /app app \
    && pip install --no-cache-dir uv==0.11.7

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend /app/backend
COPY missions /app/missions
COPY prompts /app/prompts
COPY contracts /app/contracts
RUN chown -R app:app /app

USER app
EXPOSE 8080
CMD ["/app/backend/.venv/bin/uvicorn", "english_sprint_api.main:app", "--app-dir", "/app/backend/src", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips=*"]
