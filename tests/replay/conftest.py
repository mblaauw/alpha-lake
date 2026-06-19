import pytest

from tests.fixtures import golden_dir


@pytest.fixture
def golden_fixtures() -> Path:
    return golden_dir()
