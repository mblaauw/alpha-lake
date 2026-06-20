---
name: connector
description: Alpha-Lake connector template for httpx+tenacity resources. Use when implementing source clients, fetches, raw archive, retries, or ingestion resources.
---

# Connector

Connectors fetch and archive. They do not interpret facts.

## Checklist

- Read auth, rate limit, retry, enabled, and parser version from registry/config.
- Build deterministic request params and `request_params_hash`.
- Fetch with `httpx` and `tenacity`.
- Archive raw bytes before parse.
- Emit manifest/fetch metadata.
- Return raw pointer + metadata to normalize step.
- Record per-entity outcome: `ok`, `empty`, `failed`, or `quarantined`.

## Canonical Flow

```python
async def fetch_resource(entity: str, cfg: SourceDatasetConfig) -> RawFetch:
    params = canonical_params(entity, cfg)
    response = await client.get(cfg.endpoint, params=params)
    raw_bytes = response.content
    manifest = archive_raw(
        source_id=cfg.source_id,
        endpoint=cfg.endpoint,
        params=params,
        raw_bytes=raw_bytes,
        parser_version_intended=cfg.parser_version,
    )
    return RawFetch(manifest=manifest, body=raw_bytes)
```

## Required Metadata

```text
fetch_id
source_id
endpoint
request_params_hash
request_params_json
ingest_ts
http_status
content_hash
content_type
byte_size
parser_version_intended
```

## Gates

```bash
rg -n "canonical|DuckLake|MERGE|Patito|validate" src/alpha_lake/connectors src/alpha_lake/raw
rg -n "except Exception:\s*pass|return \[\]" src/alpha_lake/connectors
```

Matches usually indicate connector overreach or hidden partial failure.

## Forbidden

- Do not parse into facts inside connectors.
- Do not write DuckLake/canonical tables.
- Do not hide partial failures.
- Do not hardcode retry/rate/auth behavior that belongs in registry data.
