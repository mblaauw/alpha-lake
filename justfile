# Alpha-Lake — just recipes

set shell := ["bash", "-c"]

# Start the reference stack
up *flags:
    docker compose up -d postgres rustfs {{ flags }}

# Stop the reference stack
down:
    docker compose down

# Reset the reference stack (destroy data)
reset:
    docker compose down -v
    docker compose up -d

# Follow logs
logs:
    docker compose logs -f

# Bootstrap the catalog (use run --rm: app container exits immediately)
bootstrap:
    docker compose run --rm app bootstrap

# Ingest market data (use run --rm: app container exits immediately)
ingest *args:
    docker compose run --rm app ingest {{ args }}

# Run health checks (use run --rm: app container exits immediately)
health:
    docker compose run --rm app health

# Run tests (embedded harness)
test *args:
    uv run pytest {{ args }}

# Run live API integration tests (skipped by default)
test-integration *args:
    uv run pytest tests/integration/ --run-live {{ args }}

# Run type checks
typecheck:
    uv run ty check --output-format full

# Run golden replay
replay *args:
    uv run pytest tests/replay/ {{ args }}

# Freeze test fixtures
freeze-fixtures:
    uv run python -m alpha_lake.fixtures freeze

# Vendor offline dependencies (experimental)
vendor:
    uv export --no-dev --output-file vendor/wheelhouse/requirements.txt
    docker compose pull
    rm -rf vendor/images && mkdir -p vendor/images
    for img in postgres:17-alpine rustfs/rustfs:latest; do \
      n=$(echo "$$img" | tr '/:' '_'); \
      docker save "$$img" | gzip > "vendor/images/$$n.tar.gz"; \
    done
    docker build -t alpha-lake-app:latest . && \
      docker save alpha-lake-app:latest | gzip > vendor/images/alpha-lake_app.tar.gz
    tar czf vendor/images.tar.gz -C vendor/images .
    echo "Vendor complete — transfer vendor/ to air-gapped environment"

# Lint and type-check
lint:
    uv run ruff check src/ tests/
    uv run ty check --output-format full
    uv run lint-imports
