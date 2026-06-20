from __future__ import annotations

import abc
import os


class SecretStore(abc.ABC):
    """Interface for secret retrieval — replaceable in tests."""

    @abc.abstractmethod
    def get(self, key: str) -> str:
        ...

    @abc.abstractmethod
    def set(self, key: str, value: str) -> None:
        ...

    @abc.abstractmethod
    def delete(self, key: str) -> None:
        ...


class EnvSecretStore(SecretStore):
    """Production secret store reading from environment variables.

    Looks up keys as {prefix}{key} in the environment. Default prefix
    is ALPHA_LAKE_ and keys are uppercased: get("eodhd_api_key") reads
    ALPHA_LAKE_EODHD_API_KEY.
    """

    def __init__(self, prefix: str = "ALPHA_LAKE_"):
        self._prefix = prefix

    def get(self, key: str) -> str:
        env_key = f"{self._prefix}{key.upper()}"
        value = os.environ.get(env_key, "")
        return value

    def set(self, key: str, value: str) -> None:
        env_key = f"{self._prefix}{key.upper()}"
        os.environ[env_key] = value

    def delete(self, key: str) -> None:
        env_key = f"{self._prefix}{key.upper()}"
        os.environ.pop(env_key, None)


class StaticSecretStore(SecretStore):
    """Test secret store returning fixed values."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, key: str) -> str:
        return self._store.get(key, "")

    def set(self, key: str, value: str) -> None:
        self._store[key] = value

    def delete(self, key: str) -> None:
        self._store.pop(key, None)


_store: SecretStore = EnvSecretStore()


def get_store() -> SecretStore:
    return _store


def set_store(store: SecretStore) -> None:
    global _store
    _store = store
