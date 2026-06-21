import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path so tests.fixtures is importable
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from tests.fixtures import golden_dir  # ty: ignore  # noqa: E402


@pytest.fixture
def golden_fixtures() -> Path:
    return golden_dir()
