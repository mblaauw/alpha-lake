from __future__ import annotations

import abc
from pathlib import Path


class BlobStore(abc.ABC):
    @abc.abstractmethod
    def read_bytes(self, path: str) -> bytes: ...

    @abc.abstractmethod
    def write_bytes(self, path: str, data: bytes) -> None: ...

    @abc.abstractmethod
    def exists(self, path: str) -> bool: ...


class _LocalBlobStore(BlobStore):
    def __init__(self, root: str) -> None:
        self._root = Path(root)

    def read_bytes(self, path: str) -> bytes:
        return (self._root / path).read_bytes()

    def write_bytes(self, path: str, data: bytes) -> None:
        p = self._root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def exists(self, path: str) -> bool:
        return (self._root / path).exists()


class _S3BlobStore(BlobStore):
    def __init__(
        self,
        bucket: str,
        endpoint: str,
        access_key: str,
        secret_key: str,
        use_ssl: bool = False,
        url_style: str = "path",
    ) -> None:
        import s3fs

        self._bucket = bucket
        self._fs = s3fs.S3FileSystem(
            endpoint_url=f"{'https' if use_ssl else 'http'}://{endpoint}",
            key=access_key,
            secret=secret_key,
            client_kwargs={"region_name": "us-east-1"},
            config_kwargs={"s3": {"addressing_style": url_style}},
        )

    def _key(self, path: str) -> str:
        return f"{self._bucket}/{path}"

    def read_bytes(self, path: str) -> bytes:
        return self._fs.read_bytes(self._key(path))

    def write_bytes(self, path: str, data: bytes) -> None:
        from os.path import dirname

        key = self._key(path)
        # s3fs.touch creates an empty file; we need write_bytes which creates
        # parent dirs implicitly. s3fs.filesystem.S3FileSystem.makedirs exists.
        self._fs.makedirs(dirname(key), exist_ok=True)
        self._fs.write_bytes(key, data)

    def exists(self, path: str) -> bool:
        return self._fs.exists(self._key(path))


def get_blob_store(uri: str) -> BlobStore:
    if uri.startswith("s3://"):
        from alpha_lake.config import get_config

        cfg = get_config()
        bucket = uri.removeprefix("s3://").rstrip("/")
        s3 = cfg.s3
        return _S3BlobStore(
            bucket=bucket,
            endpoint=s3.endpoint,
            access_key=s3.access_key,
            secret_key=s3.secret_key,
            use_ssl=s3.use_ssl,
            url_style=s3.url_style,
        )
    return _LocalBlobStore(uri)
