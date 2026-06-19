# alpha-lake-python-toolchain

Python toolchain conventions for the Alpha-Lake project. Use this skill whenever you need to run linting, type-checking, tests, add dependencies, or use the `just` task runner.

## Tool invocation

- **Always** `uv run <tool>` — never invoke `ruff`, `ty`, `pytest`, or other tools directly. This ensures the project-pinned version is used.
- **Never** `ruff format` — opencode handles formatting automatically.
- `uv add <pkg>` to add a new dependency. Do not hand-edit `pyproject.toml` dependency lists.
- `uv add --dev <pkg>` to add a dev dependency.
- `uv lock` after dependency changes (or let `uv add` do it). `uv.lock` is committed.
- Docker uses `uv sync --frozen --no-dev` — the lock file must always be in sync.

## just recipes

| Recipe | Command | Purpose |
|--------|---------|---------|
| `just up` | `docker compose up -d` | Start reference stack |
| `just down` | `docker compose down` | Stop reference stack |
| `just reset` | `docker compose down -v && up` | Reset stack (destroy data) |
| `just logs` | `docker compose logs -f` | Follow logs |
| `just lint` | `ruff check src/ tests/ && ty check` | Lint + type-check (final gate before commit) |
| `just test` | `uv run pytest` | Run tests |
| `just replay` | `uv run pytest tests/replay/` | Run golden replay tests |

Always run `just lint` before proposing a commit. If `just` is not installed, run the underlying commands directly:
```bash
uv run ruff check src/ tests/
uv run ty check --output-format full
```

## Ruff

Configured in `[tool.ruff]` in `pyproject.toml`. Enabled rules: `E, F, I, N, W, UP, B, SIM, ARG`. No formatting configuration (opencode handles that).

```bash
uv run ruff check src/ tests/
uv run ruff check --fix src/ tests/  # auto-fix fixable violations
```

## ty (type checker)

Configured in `[tool.ty]` in `pyproject.toml`. Includes `src/` and `tests/`. Tests are more lenient (`possibly-unresolved-reference = "warn"` in tests, `"error"` in source).

```bash
uv run ty check --output-format full
```

Suppress a diagnostic with inline comments:
```python
x: int = "hello"  # type: ignore[invalid-assignment]
```
