from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from alpha_lake.config import RootConfig
from alpha_lake.jobs._shared import _new_id, _utcnow
from alpha_lake.jobs.models import JobDefinition, JobRun, JobStore


class Scheduler:
    """Check job definitions and enqueue runs that are due."""

    def __init__(self, store: JobStore, cfg: RootConfig) -> None:
        self._store = store
        self._cfg = cfg

    def _source_is_held(self, source_id: str | None) -> bool:
        if not source_id:
            return False
        src = self._store.get_source(source_id)
        return bool(src and src.hold)

    def enqueue_manual(self, job_name: str) -> JobRun | None:
        """Enqueue a manual run for the given job definition."""
        jd = self._store.get_job_def(job_name)
        if jd is None or not jd.enabled or jd.hold:
            return None
        if self._source_is_held(jd.source_id):
            return None
        run = JobRun(
            run_id=_new_id(),
            job_name=jd.job_name,
            job_type=jd.job_type,
            status="queued",
            idempotency_key=f"manual:{_new_id()}",
            params_json=jd.params_json,
            source_id=jd.source_id,
            dataset=jd.dataset,
            priority=jd.priority,
            max_attempts=jd.max_attempts,
            scheduled_at=_utcnow(),
        )
        return self._store.create_run(run)

    def enqueue_due(self) -> int:
        """Enqueue runs for every due job definition.

        Returns the number of new runs enqueued.
        """
        now = _utcnow()
        defs = self._store.list_job_defs()
        count = 0
        for jd in defs:
            if not jd.enabled or jd.hold:
                continue
            if jd.schedule_kind == "manual":
                continue
            if self._source_is_held(jd.source_id):
                continue
            run = self._build_due_run(jd, now)
            if run is not None:
                self._store.create_run(run)
                count += 1
        return count

    def _build_due_run(self, jd: JobDefinition, now: datetime) -> JobRun | None:
        runs = self._store.list_runs(job_name=jd.job_name, limit=5)
        idem_key = self._compute_idempotency_key(jd, runs, now)
        if idem_key is None:
            return None
        for r in runs:
            if r.idempotency_key == idem_key:
                return None
        return JobRun(
            run_id=_new_id(),
            job_name=jd.job_name,
            job_type=jd.job_type,
            status="queued",
            idempotency_key=idem_key,
            params_json=jd.params_json,
            source_id=jd.source_id,
            dataset=jd.dataset,
            priority=jd.priority,
            max_attempts=jd.max_attempts,
            scheduled_at=now,
        )

    def _compute_idempotency_key(
        self,
        jd: JobDefinition,
        recent_runs: list[JobRun],
        now: datetime,
    ) -> str | None:
        sk = jd.schedule_kind
        sched = jd.schedule_json or {}

        if sk == "interval":
            interval = sched.get("interval_seconds", 3600)
            if recent_runs:
                last = max(r.scheduled_at or now for r in recent_runs)
                if last + timedelta(seconds=interval) > now:
                    return None
            slot = int(now.timestamp() / interval) * interval
            return f"scheduled:interval:{interval}:{slot}"

        if sk == "daily_time":
            cal = sched.get("calendar", "XNYS")
            run_time = sched.get("time", "18:00")
            tz_name = sched.get("timezone", "UTC")
            tz = ZoneInfo(tz_name)
            local_now = now.astimezone(tz)
            if cal:
                from alpha_lake.calendar_ import is_trading_day

                today = local_now.date()
                if not is_trading_day(today):
                    return None
            cutoff = datetime.combine(
                local_now.date(),
                datetime.strptime(run_time, "%H:%M").time(),
                tzinfo=tz,
            )
            if local_now < cutoff:
                return None
            return f"scheduled:daily_time:{local_now.date().isoformat()}:{run_time}"

        if sk == "market_close":
            today = now.date()
            from alpha_lake.calendar_ import is_trading_day

            if not is_trading_day(today):
                return None
            return f"scheduled:market_close:{today.isoformat()}"

        return None
