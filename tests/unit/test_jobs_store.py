from datetime import UTC, datetime
from uuid import uuid4

import pytest

from alpha_lake.config import load_config
from alpha_lake.jobs.models import JobDefinition, JobRun, WorkerState
from alpha_lake.jobs.store import MemoryJobStore


@pytest.fixture(autouse=True)
def _load_cfg():
    """Source methods in MemoryJobStore iterate over configured sources.

    Load the stack config so those lookups don't fail.  The test creates
    overrides independently; config just needs to be available.
    """
    load_config("config/stack.toml")
    return


@pytest.fixture
def store() -> MemoryJobStore:
    return MemoryJobStore()


# ── Job Definitions ────────────────────────────────────────────────────────


def test_list_defs_empty(store: MemoryJobStore):
    assert store.list_job_defs() == []


def test_seed_and_list(store: MemoryJobStore):
    defs = [
        JobDefinition(job_name="test.a", job_type="process"),
        JobDefinition(job_name="test.b", job_type="batch", enabled=False),
    ]
    store.seed_job_defs(defs)
    result = store.list_job_defs()
    assert len(result) == 2
    names = {d.job_name for d in result}
    assert names == {"test.a", "test.b"}


def test_seed_upserts(store: MemoryJobStore):
    d1 = JobDefinition(job_name="test.a", job_type="process", priority=100)
    store.seed_job_defs([d1])
    d2 = JobDefinition(job_name="test.a", job_type="process", priority=200)
    store.seed_job_defs([d2])
    updated = store.get_job_def("test.a")
    assert updated is not None
    assert updated.priority == 200


def test_get_def(store: MemoryJobStore):
    d = JobDefinition(job_name="test.a", job_type="process")
    store.seed_job_defs([d])
    assert store.get_job_def("test.a") == d
    assert store.get_job_def("nonexistent") is None


def test_update_def(store: MemoryJobStore):
    d = JobDefinition(job_name="test.a", job_type="process")
    store.seed_job_defs([d])
    store.update_job_def("test.a", hold=True)
    updated = store.get_job_def("test.a")
    assert updated is not None
    assert updated.hold is True


def test_update_def_nonexistent(store: MemoryJobStore):
    store.update_job_def("nonexistent", hold=True)


# ── Job Runs ───────────────────────────────────────────────────────────────


def _make_run(job_name: str = "test.a", status: str = "queued", **kw) -> JobRun:
    return JobRun(
        run_id=str(uuid4()),
        job_name=job_name,
        job_type="process",
        idempotency_key=str(uuid4()),
        status=status,
        scheduled_at=datetime.now(UTC),
        **kw,
    )


def test_list_runs_empty(store: MemoryJobStore):
    assert store.list_runs() == []


def test_create_and_list(store: MemoryJobStore):
    r = _make_run()
    store.create_run(r)
    runs = store.list_runs()
    assert len(runs) == 1
    assert runs[0].run_id == r.run_id


def test_list_runs_filter_status(store: MemoryJobStore):
    r1 = _make_run(status="queued")
    r2 = _make_run(status="running")
    store.create_run(r1)
    store.create_run(r2)
    assert len(store.list_runs(status="queued")) == 1
    assert len(store.list_runs(status="running")) == 1


def test_list_runs_filter_job(store: MemoryJobStore):
    r1 = _make_run(job_name="test.a")
    r2 = _make_run(job_name="test.b")
    store.create_run(r1)
    store.create_run(r2)
    assert len(store.list_runs(job_name="test.a")) == 1


def test_get_run(store: MemoryJobStore):
    r = _make_run()
    store.create_run(r)
    assert store.get_run(r.run_id) == r
    assert store.get_run("nonexistent") is None


def test_claim_next(store: MemoryJobStore):
    d = JobDefinition(job_name="test.a", job_type="process")
    store.seed_job_defs([d])
    r = _make_run(status="queued")
    store.create_run(r)
    claimed = store.claim_next("worker-1")
    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.worker_id == "worker-1"


def test_claim_next_respects_status(store: MemoryJobStore):
    d = JobDefinition(job_name="test.a", job_type="process")
    store.seed_job_defs([d])
    running = _make_run(status="running")
    succeeded = _make_run(status="succeeded")
    store.create_run(running)
    store.create_run(succeeded)
    assert store.claim_next("worker-1") is None


def test_claim_next_priority_order(store: MemoryJobStore):
    d = JobDefinition(job_name="test.a", job_type="process")
    store.seed_job_defs([d])
    r1 = _make_run(priority=200)
    r2 = _make_run(priority=100)
    store.create_run(r1)
    store.create_run(r2)
    claimed = store.claim_next("worker-1")
    assert claimed is not None
    assert claimed.run_id == r2.run_id


def test_succeed_run(store: MemoryJobStore):
    r = _make_run(status="running")
    store.create_run(r)
    store.succeed_run(r.run_id, {"ok": True})
    updated = store.get_run(r.run_id)
    assert updated is not None
    assert updated.status == "succeeded"
    assert updated.result_json == {"ok": True}


def test_fail_run(store: MemoryJobStore):
    r = _make_run(status="running")
    store.create_run(r)
    store.fail_run(r.run_id, {"error": "oops"})
    updated = store.get_run(r.run_id)
    assert updated is not None
    assert updated.status == "failed"
    assert updated.failure_json == {"error": "oops"}


def test_defer_run(store: MemoryJobStore):
    r = _make_run(status="running")
    store.create_run(r)
    store.defer_run(r.run_id)
    updated = store.get_run(r.run_id)
    assert updated is not None
    assert updated.status == "deferred"


def test_cancel_run(store: MemoryJobStore):
    r = _make_run(status="queued")
    store.create_run(r)
    assert store.cancel_run(r.run_id) is True
    cancelled = store.get_run(r.run_id)
    assert cancelled is not None
    assert cancelled.status == "cancelled"


def test_cancel_run_rejects_running(store: MemoryJobStore):
    r = _make_run(status="running")
    store.create_run(r)
    assert store.cancel_run(r.run_id) is False


def test_cancel_run_nonexistent(store: MemoryJobStore):
    assert store.cancel_run("nonexistent") is False


def test_requeue_run(store: MemoryJobStore):
    r = _make_run(status="failed")
    store.create_run(r)
    requeued = store.requeue_run(r.run_id)
    assert requeued is not None
    assert requeued.status == "queued"
    assert requeued.attempt == 0
    assert requeued.idempotency_key != r.idempotency_key


def test_requeue_run_from_quota_exhausted(store: MemoryJobStore):
    r = _make_run(status="quota_exhausted")
    store.create_run(r)
    requeued = store.requeue_run(r.run_id)
    assert requeued is not None
    assert requeued.status == "queued"


# ── Sources ────────────────────────────────────────────────────────────────


def test_set_source_hold(store: MemoryJobStore):
    store.set_source_hold("test_source", hold=True, reason="testing")
    src = store.get_source("test_source")
    assert src is not None
    assert src.hold is True
    assert src.source_id == "test_source"


def test_set_rate_limit(store: MemoryJobStore):
    store.set_rate_limit("test_source", per_sec=5.0, per_min=60)
    src = store.get_source("test_source")
    assert src is not None
    assert src.effective_rate_limit_per_sec == 5.0
    assert src.effective_rate_limit_per_min == 60


# ── Workers ────────────────────────────────────────────────────────────────


def test_upsert_worker_state(store: MemoryJobStore):
    ws = WorkerState(worker_id="worker-1", version="1.0")
    store.upsert_worker_state(ws)
    workers = store.list_workers()
    assert len(workers) == 1
    assert workers[0].worker_id == "worker-1"


def test_upsert_worker_state_updates(store: MemoryJobStore):
    ws = WorkerState(worker_id="worker-1", version="1.0")
    store.upsert_worker_state(ws)
    ws2 = WorkerState(worker_id="worker-1", version="1.1", current_run_id="run-1")
    store.upsert_worker_state(ws2)
    workers = store.list_workers()
    assert len(workers) == 1
    assert workers[0].version == "1.1"
    assert workers[0].current_run_id == "run-1"


# ── Record Calls ───────────────────────────────────────────────────────────


def test_record_and_count_calls(store: MemoryJobStore):
    store.record_call("src", "/a", "200")
    store.record_call("src", "/b", "200")
    assert store.count_calls_in_window("src", 3600) >= 2
