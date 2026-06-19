from __future__ import annotations

import abc
import datetime

from alpha_lake.models import SecurityId, SourceId


class CatalogPort(abc.ABC):
    """Interface for catalog operations (DuckLake or SQLite)."""

    @abc.abstractmethod
    def bootstrap(self) -> None: ...

    @abc.abstractmethod
    def list_datasets(self) -> list[str]: ...

    @abc.abstractmethod
    def health(self) -> dict[str, str]: ...


class StoragePort(abc.ABC):
    """Interface for raw archive storage (S3 or local FS)."""

    @abc.abstractmethod
    def store_raw(self, path: str, data: bytes) -> str: ...

    @abc.abstractmethod
    def read_raw(self, path: str) -> bytes: ...


class SecurityMasterPort(abc.ABC):
    """Interface for security master resolution."""

    @abc.abstractmethod
    def resolve(self, identifier: str, source: SourceId) -> SecurityId | None: ...


class ClockPort(abc.ABC):
    """Interface for time sources (replaceable in tests/replay)."""

    @abc.abstractmethod
    def now(self) -> datetime.datetime: ...

    @abc.abstractmethod
    def today(self) -> datetime.date: ...
