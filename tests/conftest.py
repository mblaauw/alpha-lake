import pytest

from alpha_lake.harness import EmbeddedHarness


@pytest.fixture(scope="session")
def harness() -> EmbeddedHarness:
    h = EmbeddedHarness()
    h.start()
    yield h
    h.stop()


@pytest.fixture
def db(harness: EmbeddedHarness) -> type:
    return harness.conn


@pytest.fixture
def data_path(harness: EmbeddedHarness) -> type:
    return harness.data_path
