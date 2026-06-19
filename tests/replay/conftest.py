import pytest

from tests.fixtures import golden_dir


@pytest.fixture
def golden_fixtures() -> type:
    return golden_dir()
