import pytest

from alpha_lake.config import get_config, load_config
from alpha_lake.jobs.handlers import handle_source_health
from alpha_lake.jobs.models import JobRun
from alpha_lake.jobs.store import MemoryJobStore


@pytest.fixture(autouse=True)
def _cfg():
    load_config("config/stack.toml")
    return


def test_handle_source_health():
    store = MemoryJobStore()
    cfg = get_config()
    run = JobRun(
        run_id="test",
        job_name="source.health",
        job_type="source_health",
        idempotency_key="test",
        status="running",
    )
    result = handle_source_health(None, cfg, run, store)  # type: ignore[arg-type]
    assert "sources" in result
    assert "count" in result
    assert result["count"] >= 0
