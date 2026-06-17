FROM python:3.14-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-cache

COPY src/ src/

RUN uv build --no-cache && uv pip install dist/*.whl --no-cache

ENTRYPOINT ["alpha-lake"]
