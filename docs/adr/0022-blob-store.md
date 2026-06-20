# ADR-0022: Blob Store — unified raw archive interface

**Status:** Accepted

**Context:**
The raw archive system used `Path(cfg.lake.data_path)` for all storage operations, which treated S3 URIs (`s3://lake/`) as local directory paths in stack mode. This caused a storage split-brain: canonical data reached RustFS correctly via DuckDB S3 settings, but raw archive writes went to the container's ephemeral disk. Raw data survived only until container restart, and the stack-mode raw archive was effectively invisible.

Additionally, there was no abstraction boundary between storage backends — any code that touched raw data needed to know whether it was talking to local FS or S3.

**Decision:**
Introduce a `BlobStore` ABC in a new `storage` layer that abstracts raw byte I/O, with two backends:

1. **`_LocalBlobStore`** — wraps `pathlib.Path` for local filesystem access (used by embedded harness).
2. **`_S3BlobStore`** — wraps `s3fs.S3FileSystem` for S3-compatible object storage (used by reference stack).

The factory function `get_blob_store(uri: str) -> BlobStore` selects the backend based on URI scheme (`s3://` → S3, everything else → local).

The `BlobStore` interface:
```python
class BlobStore(ABC):
    @abstractmethod
    def read_bytes(self, path: str) -> bytes: ...
    @abstractmethod
    def write_bytes(self, path: str, data: bytes) -> None: ...
    @abstractmethod
    def exists(self, path: str) -> bool: ...
```

The single `data_path` config key is split into `canonical_data_path` (for DuckLake / canonical data) and `raw_archive_uri` (for the raw archive blob store). This makes the two storage domains explicit.

**Backend choice — s3fs vs raw httpx+SigV4:**
`s3fs` wraps boto3 and is the de facto Python S3 abstraction. It is already a transitive dependency via pyarrow. Using it avoids maintaining custom SigV4 signing code and provides a stable, well-tested S3 interface.

**Consequences:**
- Positive: Storage split-brain eliminated — raw archive writes go to the correct backend in both modes.
- Positive: Clean abstraction boundary — `storage` is an import-linter layer above `config`, below adapters.
- Positive: Adding new backends (GCS, Azure Blob) requires only a new class and a factory branch.
- Negative: `s3fs` adds ~5 MB to the deployment footprint (boto3 transitive dep).
- Negative: Blob operations are synchronous — no async API for concurrent raw-archive reads.

**References:**
- `src/alpha_lake/storage/__init__.py`
- DESIGN.md §16, §8

**Date:** 2026-06-20
