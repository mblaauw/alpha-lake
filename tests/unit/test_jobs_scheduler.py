import pytest

from alpha_lake.config import load_config
from alpha_lake.jobs.models import JobDefinition
from alpha_lake.jobs.scheduler import Scheduler
from alpha_lake.jobs.store import MemoryJobStore


@pytest.fixture(autouse=True)
def _cfg():
    load_config("config/stack.toml")
    return


@pytest.fixture
def store() -> MemoryJobStore:
    return MemoryJobStore()


def test_enqueue_manual(store: MemoryJobStore):
    from alpha_lake.config import get_config

    jd = JobDefinition(job_name="test.a", job_type="process")
    store.seed_job_defs([jd])
    sched = Scheduler(store, get_config())
    run = sched.enqueue_manual("test.a")
    assert run is not None
    assert run.status == "queued"
    assert run.job_name == "test.a"


def test_enqueue_manual_disabled(store: MemoryJobStore):
    from alpha_lake.config import get_config

    jd = JobDefinition(job_name="test.a", job_type="process", enabled=False)
    store.seed_job_defs([jd])
    sched = Scheduler(store, get_config())
    assert sched.enqueue_manual("test.a") is None


def test_enqueue_manual_held(store: MemoryJobStore):
    from alpha_lake.config import get_config

    jd = JobDefinition(job_name="test.a", job_type="process", hold=True)
    store.seed_job_defs([jd])
    sched = Scheduler(store, get_config())
    assert sched.enqueue_manual("test.a") is None


def test_enqueue_manual_nonexistent(store: MemoryJobStore):
    from alpha_lake.config import get_config

    sched = Scheduler(store, get_config())
    assert sched.enqueue_manual("nonexistent") is None


def test_enqueue_due_interval(store: MemoryJobStore):
    from alpha_lake.config import get_config

    jd = JobDefinition(
        job_name="test.a",
        job_type="process",
        schedule_kind="interval",
        schedule_json={"interval_seconds": 60},
    )
    store.seed_job_defs([jd])
    sched = Scheduler(store, get_config())
    count = sched.enqueue_due()
    assert count == 1
    runs = store.list_runs(job_name="test.a")
    assert len(runs) == 1
    assert runs[0].status == "queued"


def test_enqueue_due_interval_idempotent(store: MemoryJobStore):
    from alpha_lake.config import get_config

    jd = JobDefinition(
        job_name="test.a",
        job_type="process",
        schedule_kind="interval",
        schedule_json={"interval_seconds": 3600},
    )
    store.seed_job_defs([jd])
    sched = Scheduler(store, get_config())
    sched.enqueue_due()
    sched.enqueue_due()
    runs = store.list_runs(job_name="test.a")
    assert len(runs) == 1


def test_enqueue_due_skip_manual(store: MemoryJobStore):
    from alpha_lake.config import get_config

    jd = JobDefinition(job_name="test.a", job_type="process", schedule_kind="manual")
    store.seed_job_defs([jd])
    sched = Scheduler(store, get_config())
    assert sched.enqueue_due() == 0


def test_enqueue_due_skip_held(store: MemoryJobStore):
    from alpha_lake.config import get_config

    jd = JobDefinition(
        job_name="test.a",
        job_type="process",
        schedule_kind="interval",
        hold=True,
        schedule_json={"interval_seconds": 60},
    )
    store.seed_job_defs([jd])
    sched = Scheduler(store, get_config())
    assert sched.enqueue_due() == 0
