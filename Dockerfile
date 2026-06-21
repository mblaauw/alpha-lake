FROM python:3.13-slim

WORKDIR /app

RUN pip install uv && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
COPY src/ src/
RUN uv sync --frozen --no-dev --no-cache

ENTRYPOINT ["uv", "run", "--frozen", "python", "-m", "alpha_lake.cli"]
