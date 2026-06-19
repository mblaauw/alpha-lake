from pathlib import Path

import pytest

from tests.fixtures import golden_dir  # ty: ignore


@pytest.fixture
def golden_fixtures() -> Path:
    return golden_dir()
