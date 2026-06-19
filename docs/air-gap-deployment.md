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

## Verify

```bash
just health
just bootstrap
```

## Updating

Repeat the vendor step on the networked machine and transfer `vendor/` again.
