# Alpha-Lake — just recipes

# Start the reference stack
up:
    docker compose up -d

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

# Bootstrap the catalog
bootstrap:
    docker compose exec app alpha-lake bootstrap

# Ingest market data
ingest *args:
    docker compose exec app alpha-lake ingest {{ args }}

# Run health checks
health:
    docker compose exec app alpha-lake health

# Run tests (embedded harness)
test *args:
    uv run pytest {{ args }}

# Run type checks
typecheck:
    uv run ty check --output-format full

# Run golden replay
replay *args:
    uv run pytest tests/replay/ {{ args }}

# Freeze test fixtures
freeze-fixtures:
    uv run python -m alpha_lake.fixtures freeze

# Vendor offline dependencies
vendor:
    uv export --no-dev --output-file vendor/wheelhouse/requirements.txt
    docker compose pull

# Lint and type-check
lint:
    uv run ruff check src/ tests/
    uv run ty check --output-format full
    uv run lint-imports
