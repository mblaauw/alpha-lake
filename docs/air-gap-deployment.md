# Air-Gap Deployment

Alpha-Lake can be fully deployed in air-gapped (offline) environments by transferring pre-built vendor artifacts.

## Prerequisites

- A networked machine with Docker and Python 3.12+
- `uv` installed
- Network access to PyPI, Docker Hub, and GitHub Container Registry (one-time only)
- Target machine with Docker and Python 3.12+

## One-Time Vendor Step (online)

```bash
just vendor
```

This produces:
- `vendor/wheelhouse/requirements.txt` — pinned Python dependencies
- `vendor/images/` — pulled Docker images (or `vendor/images.tar.gz`)

Transfer the entire `vendor/` directory to the air-gapped machine.

## Deploy (offline)

```bash
# Load Docker images from local archive
docker load < vendor/images.tar.gz

# Start the stack without network
just up --offline
```

## DuckDB Extension Vendoring

DuckDB extensions (ducklake, httpfs, parquet, postgres, sqlite_scanner) are autoloaded
from DuckDB's CDN by default. In air-gapped environments, extension files must be
vendored manually.

### Extension File Locations

Download extension files from DuckDB's extension repository for your platform:

| Platform | Extension directory |
|----------|-------------------|
| macOS (arm64) | `~/.duckdb/extensions/{duckdb_version}/osx_arm64/` |
| Linux (amd64) | `~/.duckdb/extensions/{duckdb_version}/linux_amd64/` |
| Linux (arm64) | `~/.duckdb/extensions/{duckdb_version}/linux_arm64/` |

### Required Extensions

- `ducklake.duckdb_extension`
- `httpfs.duckdb_extension`
- `parquet.duckdb_extension`
- `postgres_scanner.duckdb_extension`
- `sqlite_scanner.duckdb_extension`

### Configuration

Set DuckDB's extension directory before loading extensions:

```sql
SET extension_directory = '/path/to/vendored/extensions';
```

Or set the environment variable `DUCKDB_EXTENSION_DIRECTORY`.

### Verify Offline Installation

```python
import duckdb
con = duckdb.connect()
con.execute("SET extension_directory = '/path/to/vendored/extensions'")
con.execute("INSTALL ducklake")   # loads from local dir, not CDN
con.execute("LOAD ducklake")
```

## Verify

```bash
just health
just bootstrap
```

## Updating

Repeat the vendor step on the networked machine and transfer `vendor/` again.
