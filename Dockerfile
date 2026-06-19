FROM python:3.13-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock ./
COPY src/ src/
RUN uv sync --frozen --no-dev --no-cache

ENTRYPOINT ["uv", "run", "--frozen", "python", "-m", "alpha_lake.cli"]
