FROM python:3.13-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /uvx /bin/

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --default-index https://pypi.org/simple

COPY . .

ENV PATH="/app/.venv/bin:$PATH"


CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
