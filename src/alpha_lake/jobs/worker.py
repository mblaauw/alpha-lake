from __future__ import annotations

import signal
import time
from typing import Any

import duckdb

from alpha_lake.cli_ui import fail as fail_log
from alpha_lake.cli_ui import info, ok, warn
from alpha_lake.config import RootConfig
from alpha_lake.connectors.base import BudgetExhaustedError
from alpha_lake.jobs._shared import _utcnow
from alpha_lake.jobs.models import JobRun, JobStore
from alpha_lake.jobs.scheduler import Scheduler

_HANDLERS: dict[str, Any] = {}


def _register_handlers() -> None:
    from alpha_lake.jobs.handlers import (
        handle_bars_bootstrap,
        handle_bars_refresh,
        handle_dataset_refresh,
        handle_indicators_compute,
        handle_source_health,
        handle_stooq_rebuild,
    )

    _HANDLERS["bars_bootstrap"] = handle_bars_bootstrap
    _HANDLERS["bars_refresh"] = handle_bars_refresh
    _HANDLERS["dataset_refresh"] = handle_dataset_refresh
    _HANDLERS["source_health"] = handle_source_health
    _HANDLERS["stooq_rebuild"] = handle_stooq_rebuild
    _HANDLERS["indicators_compute"] = handle_indicators_compute


class Worker:
    """Single-process worker that claims and executes jobs.

    Polls the store for queued runs, dispatches to the registered handler,
    and records success/failure.
    """

    def __init__(
        self,
        store: JobStore,
        scheduler: Scheduler,
        cfg: RootConfig,
        poll_interval: float = 5.0,
        once: bool = False,
    ) -> None:
        self._store = store
        self._scheduler = scheduler
        self._cfg = cfg
        self._poll_interval = poll_interval
        self._once = once
        self._shutdown = False
        self._worker_id = f"worker-{_utcnow().strftime('%Y%m%d%H%M%S')}-{id(self):x}"

        _register_handlers()
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum: int, _frame: Any) -> None:
        self._shutdown = True
        info(f"Received signal {signum}, shutting down after current job...")

    def run(self) -> None:
        """Main loop: poll → schedule → claim → execute."""
        self._catch_up()
        while not self._shutdown:
            self._heartbeat()

            # Check if this worker has been paused via the API
            workers = self._store.list_workers()
            my_state = next((w for w in workers if w.worker_id == self._worker_id), None)
            if my_state is not None and my_state.paused:
                time.sleep(self._poll_interval)
                continue

            try:
                self._scheduler.enqueue_due()
            except Exception as exc:
                warn(f"Scheduler error: {exc}")

            claimed = self._store.claim_next(self._worker_id)
            if claimed is not None:
                self._execute(claimed)
            elif self._once:
                break
            else:
                time.sleep(self._poll_interval)

        info("Worker shut down.")

    def _catch_up(self) -> None:
        """Enqueue runs for missed trading days on startup."""
        try:
            count = self._scheduler.catch_up_missed()
            if count:
                ok(f"Catch-up enqueued {count} missed job run(s).")
        except Exception as exc:
            warn(f"Catch-up error (non-fatal): {exc}")

    def _heartbeat(self, current_run_id: str | None = None) -> None:
        from alpha_lake.jobs.models import WorkerState

        self._store.upsert_worker_state(
            WorkerState(
                worker_id=self._worker_id,
                heartbeat_at=_utcnow(),
                current_run_id=current_run_id,
                version="0.1.0",
            )
        )

    def _execute(self, run: JobRun) -> None:
        """Run a single claimed job."""
        handler = _HANDLERS.get(run.job_type)
        if handler is None:
            fail_log(f"No handler for job_type={run.job_type} (run={run.run_id[:8]})")
            self._store.fail_run(run.run_id, {"error": f"Unknown job_type: {run.job_type}"})
            return

        info(f"Running {run.job_name} ({run.run_id[:8]}) job_type={run.job_type}")
        self._heartbeat(current_run_id=run.run_id)
        t0 = time.monotonic()
        try:
            con = self._connect()
            result = handler(con, self._cfg, run, self._store)
            con.close()
        except BudgetExhaustedError as exc:
            duration = time.monotonic() - t0
            fail_log(
                f"Budget exhausted {run.job_name} ({run.run_id[:8]}) after {duration:.1f}s: {exc}"
            )
            self._store.quota_exhausted_run(run.run_id, {"error": str(exc)})
            return
        except Exception as exc:
            duration = time.monotonic() - t0
            fail_log(f"Failed {run.job_name} ({run.run_id[:8]}) after {duration:.1f}s: {exc}")
            if run.attempt < run.max_attempts - 1:
                self._store.defer_run(run.run_id)
            else:
                self._store.fail_run(run.run_id, {"error": str(exc)})
            return

        duration = time.monotonic() - t0
        self._store.succeed_run(run.run_id, result)
        ok(f"Completed {run.job_name} ({run.run_id[:8]}) in {duration:.1f}s")

    def _connect(self) -> duckdb.DuckDBPyConnection:
        from alpha_lake.catalog import connect as _catalog_connect

        return _catalog_connect(self._cfg)
