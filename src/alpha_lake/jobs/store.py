from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import duckdb

from alpha_lake.config import RootConfig
from alpha_lake.jobs._shared import _new_id, _utcnow
from alpha_lake.jobs.models import (
    JobDefinition,
    JobRun,
    SourceCallRecord,
    SourceRateLimitOverride,
    SourceWithLimits,
    SymbolEntry,
    SymbolSourceOverride,
    WorkerState,
)

_OPS_SCHEMA: str = "ops"


def _resolve_ops_schema(con: duckdb.DuckDBPyConnection) -> str:
    """Return the correct ops schema name for *con*.

    When Postgres is attached as ``pg_catalog``, ops tables must live there
    so they are shared across containers.  In embedded mode the native
    ``ops`` schema is used.
    """
    try:
        con.execute("SELECT 1 FROM pg_catalog.ops.job_definition LIMIT 0")
        return "pg_catalog.ops"
    except Exception:
        return "ops"


def ensure_ops_schema(con: duckdb.DuckDBPyConnection) -> None:
    global _OPS_SCHEMA
    _OPS_SCHEMA = _resolve_ops_schema(con)
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {_OPS_SCHEMA}")
    con.execute(
        f"CREATE TABLE IF NOT EXISTS {_OPS_SCHEMA}.job_definition ("
        "  job_name TEXT PRIMARY KEY,"
        "  job_type TEXT NOT NULL,"
        "  enabled BOOLEAN NOT NULL DEFAULT TRUE,"
        "  hold BOOLEAN NOT NULL DEFAULT FALSE,"
        "  schedule_kind TEXT NOT NULL DEFAULT 'manual',"
        "  schedule_json TEXT NOT NULL DEFAULT '{}',"
        "  params_json TEXT NOT NULL DEFAULT '{}',"
        "  max_attempts INTEGER NOT NULL DEFAULT 3,"
        "  priority INTEGER NOT NULL DEFAULT 100,"
        "  concurrency_key TEXT NOT NULL DEFAULT '',"
        "  source_id TEXT,"
        "  dataset TEXT,"
        "  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        "  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    )
    _fk_cross_catalog = "." in _OPS_SCHEMA
    _job_name_col = (
        "  job_name TEXT NOT NULL"
        if _fk_cross_catalog
        else f"  job_name TEXT NOT NULL REFERENCES {_OPS_SCHEMA}.job_definition(job_name)"
    )
    con.execute(
        f"CREATE TABLE IF NOT EXISTS {_OPS_SCHEMA}.job_run ("
        "  run_id TEXT PRIMARY KEY,"
        f"{_job_name_col},"
        "  job_type TEXT NOT NULL,"
        "  status TEXT NOT NULL,"
        "  idempotency_key TEXT NOT NULL,"
        "  params_json TEXT NOT NULL DEFAULT '{}',"
        "  requested_for_date DATE,"
        "  source_id TEXT,"
        "  dataset TEXT,"
        "  priority INTEGER NOT NULL DEFAULT 100,"
        "  attempt INTEGER NOT NULL DEFAULT 0,"
        "  max_attempts INTEGER NOT NULL DEFAULT 3,"
        "  scheduled_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        "  started_at TIMESTAMPTZ,"
        "  finished_at TIMESTAMPTZ,"
        "  heartbeat_at TIMESTAMPTZ,"
        "  worker_id TEXT,"
        "  result_json TEXT,"
        "  failure_json TEXT,"
        "  ingestion_run_id TEXT,"
        "  ducklake_snapshot_id TEXT,"
        "  created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    )
    con.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS ux_job_run_idempotency"
        f" ON {_OPS_SCHEMA}.job_run (job_name, idempotency_key)"
    )
    con.execute(
        f"CREATE INDEX IF NOT EXISTS ix_job_run_status_scheduled"
        f" ON {_OPS_SCHEMA}.job_run (status, scheduled_at, priority)"
    )
    con.execute(
        f"CREATE TABLE IF NOT EXISTS {_OPS_SCHEMA}.source_rate_limit_override ("
        "  source_id TEXT PRIMARY KEY,"
        "  hold BOOLEAN NOT NULL DEFAULT FALSE,"
        "  rate_limit_per_sec DOUBLE,"
        "  rate_limit_per_min INTEGER,"
        "  rate_limit_per_day INTEGER,"
        "  reason TEXT NOT NULL DEFAULT '',"
        "  updated_by TEXT NOT NULL DEFAULT 'operator',"
        "  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    )
    con.execute(
        f"CREATE TABLE IF NOT EXISTS {_OPS_SCHEMA}.source_call_ledger ("
        "  call_id TEXT PRIMARY KEY,"
        "  source_id TEXT NOT NULL,"
        "  endpoint TEXT NOT NULL DEFAULT '',"
        "  job_run_id TEXT,"
        "  called_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        "  status TEXT NOT NULL,"
        "  cost_units INTEGER NOT NULL DEFAULT 1,"
        "  metadata_json TEXT NOT NULL DEFAULT '{}'"
        ")"
    )
    con.execute(
        f"CREATE INDEX IF NOT EXISTS ix_source_call_ledger_source_called"
        f" ON {_OPS_SCHEMA}.source_call_ledger (source_id, called_at)"
    )
    con.execute(
        f"CREATE TABLE IF NOT EXISTS {_OPS_SCHEMA}.worker_state ("
        "  worker_id TEXT PRIMARY KEY,"
        "  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        "  heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        "  current_run_id TEXT,"
        "  version TEXT NOT NULL DEFAULT ''"
        ")"
    )
    con.execute(
        f"CREATE TABLE IF NOT EXISTS {_OPS_SCHEMA}.symbol_registry ("
        "  symbol TEXT PRIMARY KEY,"
        "  added_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        "  removed_at TIMESTAMPTZ,"
        "  added_by TEXT NOT NULL DEFAULT 'auto',"
        "  metadata TEXT"
        ")"
    )
    con.execute(
        f"CREATE TABLE IF NOT EXISTS {_OPS_SCHEMA}.symbol_source_override ("
        "  symbol TEXT PRIMARY KEY,"
        "  source_id TEXT NOT NULL,"
        "  reason TEXT NOT NULL DEFAULT '',"
        "  updated_by TEXT NOT NULL DEFAULT 'operator',"
        "  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    )


def seed_job_defs_from_config(con: duckdb.DuckDBPyConnection, cfg: RootConfig) -> None:
    worker = cfg.worker
    if not worker.enabled or not worker.job_definitions:
        return
    now = _utcnow()
    for jd in worker.job_definitions:
        con.execute(
            f"INSERT INTO {_OPS_SCHEMA}.job_definition "
            "(job_name, job_type, enabled, hold, schedule_kind, schedule_json, "
            " params_json, max_attempts, priority, concurrency_key, source_id, dataset,"
            " created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (job_name) DO UPDATE SET "
            "  enabled = EXCLUDED.enabled,"
            "  hold = EXCLUDED.hold,"
            "  schedule_json = EXCLUDED.schedule_json,"
            "  params_json = EXCLUDED.params_json,"
            "  max_attempts = EXCLUDED.max_attempts,"
            "  priority = EXCLUDED.priority,"
            "  concurrency_key = EXCLUDED.concurrency_key,"
            "  source_id = EXCLUDED.source_id,"
            "  dataset = EXCLUDED.dataset,"
            "  updated_at = ?",
            [
                jd.job_name,
                jd.job_type,
                jd.enabled,
                jd.hold,
                jd.schedule_kind,
                json.dumps(jd.schedule),
                json.dumps(jd.params),
                jd.max_attempts,
                jd.priority,
                jd.concurrency_key,
                jd.source_id,
                jd.dataset,
                now,
                now,
                now,
            ],
        )


def seed_default_job_defs(con: duckdb.DuckDBPyConnection) -> None:
    from alpha_lake.jobs.models import DEFAULT_JOB_DEFS

    now = _utcnow()
    for jd in DEFAULT_JOB_DEFS:
        con.execute(
            f"INSERT INTO {_OPS_SCHEMA}.job_definition "
            "(job_name, job_type, enabled, hold, schedule_kind, schedule_json, "
            " params_json, max_attempts, priority, concurrency_key, source_id, dataset,"
            " created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (job_name) DO NOTHING",
            [
                jd.job_name,
                jd.job_type,
                jd.enabled,
                jd.hold,
                jd.schedule_kind,
                json.dumps(jd.schedule_json),
                json.dumps(jd.params_json),
                jd.max_attempts,
                jd.priority,
                jd.concurrency_key,
                jd.source_id,
                jd.dataset,
                now,
                now,
            ],
        )


class PostgresJobStore:
    """JobStore implementation backed by Postgres through DuckDB's pg_catalog."""

    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    @property
    def _ops(self) -> str:
        return _OPS_SCHEMA

    def _row_to_job_def(self, row: tuple[Any, ...]) -> JobDefinition:
        return JobDefinition(
            job_name=row[0],
            job_type=row[1],
            enabled=row[2],
            hold=row[3],
            schedule_kind=row[4],
            schedule_json=json.loads(row[5]) if isinstance(row[5], str) else (row[5] or {}),
            params_json=json.loads(row[6]) if isinstance(row[6], str) else (row[6] or {}),
            max_attempts=row[7],
            priority=row[8],
            concurrency_key=row[9],
            source_id=row[10],
            dataset=row[11],
            created_at=row[12],
            updated_at=row[13],
        )

    def _row_to_run(self, row: tuple[Any, ...]) -> JobRun:
        return JobRun(
            run_id=row[0],
            job_name=row[1],
            job_type=row[2],
            status=row[3],
            idempotency_key=row[4],
            params_json=json.loads(row[5]) if isinstance(row[5], str) else (row[5] or {}),
            requested_for_date=row[6],
            source_id=row[7],
            dataset=row[8],
            priority=row[9],
            attempt=row[10],
            max_attempts=row[11],
            scheduled_at=row[12],
            started_at=row[13],
            finished_at=row[14],
            heartbeat_at=row[15],
            worker_id=row[16],
            result_json=json.loads(row[17]) if isinstance(row[17], str) and row[17] else None,
            failure_json=json.loads(row[18]) if isinstance(row[18], str) and row[18] else None,
            ingestion_run_id=row[19],
            ducklake_snapshot_id=row[20],
            created_at=row[21],
        )

    # ── Job definitions ─────────────────────────────────────────────────

    def list_job_defs(self) -> list[JobDefinition]:
        rows = self._con.execute(
            f"SELECT * FROM {self._ops}.job_definition ORDER BY priority, job_name"
        ).fetchall()
        return [self._row_to_job_def(r) for r in rows]

    def get_job_def(self, job_name: str) -> JobDefinition | None:
        row = self._con.execute(
            f"SELECT * FROM {_OPS_SCHEMA}.job_definition WHERE job_name = ?",
            [job_name],
        ).fetchone()
        return self._row_to_job_def(row) if row else None

    def seed_job_defs(self, defs: list[JobDefinition]) -> None:
        now = _utcnow()
        for jd in defs:
            self._con.execute(
                f"INSERT INTO {_OPS_SCHEMA}.job_definition "
                "(job_name, job_type, enabled, hold, schedule_kind, schedule_json, "
                " params_json, max_attempts, priority, concurrency_key, source_id, dataset,"
                " created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (job_name) DO UPDATE SET "
                "  enabled = EXCLUDED.enabled,"
                "  hold = EXCLUDED.hold,"
                "  schedule_json = EXCLUDED.schedule_json,"
                "  params_json = EXCLUDED.params_json,"
                "  max_attempts = EXCLUDED.max_attempts,"
                "  priority = EXCLUDED.priority,"
                "  concurrency_key = EXCLUDED.concurrency_key,"
                "  source_id = EXCLUDED.source_id,"
                "  dataset = EXCLUDED.dataset,"
                "  updated_at = ?",
                [
                    jd.job_name,
                    jd.job_type,
                    jd.enabled,
                    jd.hold,
                    jd.schedule_kind,
                    jd.schedule_json,
                    jd.params_json,
                    jd.max_attempts,
                    jd.priority,
                    jd.concurrency_key,
                    jd.source_id,
                    jd.dataset,
                    now,
                    now,
                ],
            )

    def update_job_def(self, job_name: str, **kwargs: Any) -> JobDefinition | None:
        allowed = {"enabled", "hold", "schedule_json", "max_attempts", "priority"}
        updates: list[str] = []
        values: list[Any] = []
        for k, v in kwargs.items():
            if k not in allowed:
                raise ValueError(f"Cannot update {k} on job definition")
            updates.append(f"{k} = ?")
            values.append(v)
        if not updates:
            return self.get_job_def(job_name)
        updates.append("updated_at = ?")
        values.append(_utcnow())
        values.append(job_name)
        self._con.execute(
            f"UPDATE {_OPS_SCHEMA}.job_definition SET {', '.join(updates)} WHERE job_name = ?",
            values,
        )
        return self.get_job_def(job_name)

    # ── Job runs ───────────────────────────────────────────────────────

    def list_runs(
        self,
        status: str | None = None,
        job_name: str | None = None,
        source_id: str | None = None,
        dataset: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[JobRun]:
        clauses: list[str] = []
        values: list[Any] = []
        if status:
            clauses.append("status = ?")
            values.append(status)
        if job_name:
            clauses.append("job_name = ?")
            values.append(job_name)
        if source_id:
            clauses.append("source_id = ?")
            values.append(source_id)
        if dataset:
            clauses.append("dataset = ?")
            values.append(dataset)
        where = " AND ".join(clauses) if clauses else "TRUE"
        rows = self._con.execute(
            f"SELECT * FROM {_OPS_SCHEMA}.job_run WHERE {where}"
            f" ORDER BY created_at DESC LIMIT {int(limit)} OFFSET {int(offset)}",
            values,
        ).fetchall()
        return [self._row_to_run(r) for r in rows]

    def get_run(self, run_id: str) -> JobRun | None:
        row = self._con.execute(
            f"SELECT * FROM {_OPS_SCHEMA}.job_run WHERE run_id = ?",
            [run_id],
        ).fetchone()
        return self._row_to_run(row) if row else None

    def create_run(self, run: JobRun) -> JobRun:
        now = run.created_at or _utcnow()
        self._con.execute(
            f"INSERT INTO {_OPS_SCHEMA}.job_run "
            "(run_id, job_name, job_type, status, idempotency_key, params_json, "
            " requested_for_date, source_id, dataset, priority, attempt, max_attempts, "
            " scheduled_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                run.run_id or _new_id(),
                run.job_name,
                run.job_type,
                run.status,
                run.idempotency_key,
                run.params_json,
                run.requested_for_date,
                run.source_id,
                run.dataset,
                run.priority,
                run.attempt,
                run.max_attempts,
                run.scheduled_at or now,
                now,
            ],
        )
        return run

    def claim_next(self, worker_id: str) -> JobRun | None:
        row = self._con.execute(
            f"UPDATE {_OPS_SCHEMA}.job_run "
            "SET status = 'running', started_at = ?, heartbeat_at = ?,"
            "  worker_id = ?, attempt = attempt + 1 "
            f"WHERE run_id = ("
            f"  SELECT r.run_id FROM {_OPS_SCHEMA}.job_run r"
            f"  JOIN {_OPS_SCHEMA}.job_definition d ON d.job_name = r.job_name"
            f"  LEFT JOIN {_OPS_SCHEMA}.source_rate_limit_override o"
            f"    ON o.source_id = r.source_id"
            "  WHERE r.status IN ('queued', 'deferred')"
            "    AND r.scheduled_at <= now()"
            "    AND d.enabled = TRUE"
            "    AND d.hold = FALSE"
            "    AND (o.hold IS NULL OR o.hold = FALSE)"
            "  ORDER BY r.priority ASC, r.scheduled_at ASC"
            "  LIMIT 1"
            ")"
            " RETURNING *",
            [_utcnow(), _utcnow(), worker_id],
        ).fetchone()
        return self._row_to_run(row) if row else None

    def succeed_run(self, run_id: str, result: dict[str, Any]) -> None:
        self._con.execute(
            f"UPDATE {_OPS_SCHEMA}.job_run SET status = 'succeeded',"
            " finished_at = ?, result_json = ? WHERE run_id = ?",
            [_utcnow(), json.dumps(result), run_id],
        )

    def fail_run(self, run_id: str, failure: dict[str, Any]) -> None:
        self._con.execute(
            f"UPDATE {_OPS_SCHEMA}.job_run SET status = 'failed',"
            " finished_at = ?, failure_json = ? WHERE run_id = ?",
            [_utcnow(), json.dumps(failure), run_id],
        )

    def defer_run(self, run_id: str, retry_at: datetime | None = None) -> None:
        self._con.execute(
            f"UPDATE {_OPS_SCHEMA}.job_run SET status = 'deferred',"
            " scheduled_at = COALESCE(?, scheduled_at + interval '5 minutes')"
            " WHERE run_id = ?",
            [retry_at, run_id],
        )

    def quota_exhausted_run(self, run_id: str, failure: dict[str, Any]) -> None:
        self._con.execute(
            f"UPDATE {_OPS_SCHEMA}.job_run SET status = 'quota_exhausted',"
            " finished_at = ?, failure_json = ? WHERE run_id = ?",
            [_utcnow(), json.dumps(failure), run_id],
        )

    def cancel_run(self, run_id: str) -> bool:
        self._con.execute(
            f"UPDATE {_OPS_SCHEMA}.job_run SET status = 'cancelled',"
            " finished_at = ? WHERE run_id = ? AND status IN ('queued', 'deferred')",
            [_utcnow(), run_id],
        )
        return self._con.execute("SELECT changes()").fetchone()[0] > 0

    def requeue_run(self, run_id: str) -> JobRun | None:
        existing = self.get_run(run_id)
        if existing is None or existing.status not in ("failed", "quota_exhausted"):
            return None
        new_run = JobRun(
            run_id=_new_id(),
            job_name=existing.job_name,
            job_type=existing.job_type,
            status="queued",
            idempotency_key=f"{existing.idempotency_key}:retry:{existing.attempt + 1}",
            params_json=existing.params_json,
            requested_for_date=existing.requested_for_date,
            source_id=existing.source_id,
            dataset=existing.dataset,
            priority=existing.priority,
            max_attempts=existing.max_attempts,
            scheduled_at=_utcnow(),
        )
        return self.create_run(new_run)

    # ── Source budgets ─────────────────────────────────────────────────

    def list_sources(self) -> list[SourceWithLimits]:
        from alpha_lake.config import get_config

        cfg = get_config()
        overrides = {
            r[0]: r
            for r in self._con.execute(
                f"SELECT * FROM {_OPS_SCHEMA}.source_rate_limit_override"
            ).fetchall()
        }
        from alpha_lake.connectors.base import call_ledger_summary
        from alpha_lake.secrets import get_store

        store = get_store()
        sources: list[SourceWithLimits] = []
        for sid, sc in sorted(cfg.sources.items()):
            override = overrides.get(sid)
            has_key = store.get(f"{sid}_api_key") is not None
            ledger = call_ledger_summary(sid).get(sid, {})
            swl = SourceWithLimits(
                source_id=sid,
                requires_key=sc.requires_key,
                has_key=has_key or bool(sc.api_key),
                configured_rate_limit_per_sec=sc.rate_limit_per_sec,
                configured_rate_limit_per_min=sc.rate_limit_per_min,
                configured_rate_limit_per_day=sc.rate_limit_per_day,
                effective_rate_limit_per_sec=(
                    override[2] if override and override[2] is not None else sc.rate_limit_per_sec
                ),
                effective_rate_limit_per_min=(
                    override[3] if override and override[3] is not None else sc.rate_limit_per_min
                ),
                effective_rate_limit_per_day=(
                    override[4] if override and override[4] is not None else sc.rate_limit_per_day
                ),
                hold=override[1] if override else False,
                calls_last_min=ledger.get("calls_last_min", 0),
                calls_last_day=ledger.get("calls_last_day", 0),
            )
            sources.append(swl)
        return sources

    def get_source(self, source_id: str) -> SourceWithLimits | None:
        for s in self.list_sources():
            if s.source_id == source_id:
                return s
        return None

    def set_source_hold(self, source_id: str, hold: bool, reason: str = "") -> None:
        self._con.execute(
            f"INSERT INTO {_OPS_SCHEMA}.source_rate_limit_override "
            "(source_id, hold, reason, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT (source_id) DO UPDATE SET"
            "  hold = EXCLUDED.hold,"
            "  reason = EXCLUDED.reason,"
            "  updated_at = EXCLUDED.updated_at",
            [source_id, hold, reason, _utcnow()],
        )

    def set_rate_limit(
        self,
        source_id: str,
        per_sec: float | None = None,
        per_min: int | None = None,
        per_day: int | None = None,
        reason: str = "",
    ) -> None:
        existing = self._con.execute(
            f"SELECT * FROM {_OPS_SCHEMA}.source_rate_limit_override WHERE source_id = ?",
            [source_id],
        ).fetchone()
        if existing:
            cur_sec = existing[2] if per_sec is None else per_sec
            cur_min = existing[3] if per_min is None else per_min
            cur_day = existing[4] if per_day is None else per_day
            cur_reason = existing[5] if reason == "" else reason
        else:
            cur_sec = per_sec
            cur_min = per_min
            cur_day = per_day
            cur_reason = reason

        from alpha_lake.config import get_config

        cfg = get_config()
        sc = cfg.sources.get(source_id)
        if sc:
            if cur_sec is not None and cur_sec > sc.rate_limit_per_sec:
                raise ValueError(
                    f"Rate limit per-sec {cur_sec} exceeds"
                    f" configured maximum {sc.rate_limit_per_sec}"
                )
            if (
                cur_min is not None
                and sc.rate_limit_per_min is not None
                and cur_min > sc.rate_limit_per_min
            ):
                raise ValueError(
                    f"Rate limit per-min {cur_min} exceeds"
                    f" configured maximum {sc.rate_limit_per_min}"
                )
            if (
                cur_day is not None
                and sc.rate_limit_per_day is not None
                and cur_day > sc.rate_limit_per_day
            ):
                raise ValueError(
                    f"Rate limit per-day {cur_day} exceeds"
                    f" configured maximum {sc.rate_limit_per_day}"
                )

        self._con.execute(
            f"INSERT INTO {_OPS_SCHEMA}.source_rate_limit_override "
            "(source_id, hold, rate_limit_per_sec,"
            " rate_limit_per_min, rate_limit_per_day, reason,"
            " updated_at) "
            "VALUES (?, FALSE, ?, ?, ?, ?, ?) "
            "ON CONFLICT (source_id) DO UPDATE SET"
            "  rate_limit_per_sec = EXCLUDED.rate_limit_per_sec,"
            "  rate_limit_per_min = EXCLUDED.rate_limit_per_min,"
            "  rate_limit_per_day = EXCLUDED.rate_limit_per_day,"
            "  reason = EXCLUDED.reason,"
            "  updated_at = EXCLUDED.updated_at",
            [source_id, cur_sec, cur_min, cur_day, cur_reason, _utcnow()],
        )

    # ── Call ledger ────────────────────────────────────────────────────

    def record_call(
        self,
        source_id: str,
        endpoint: str,
        status: str,
        job_run_id: str | None = None,
        cost_units: int = 1,
    ) -> None:
        self._con.execute(
            f"INSERT INTO {_OPS_SCHEMA}.source_call_ledger "
            "(call_id, source_id, endpoint, job_run_id,"
            " called_at, status, cost_units, metadata_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                _new_id(),
                source_id,
                endpoint,
                job_run_id,
                _utcnow(),
                status,
                cost_units,
                json.dumps({}),
            ],
        )

    def count_calls_in_window(self, source_id: str, window_secs: int) -> int:
        cutoff = _utcnow() - timedelta(seconds=window_secs)
        row = self._con.execute(
            f"SELECT COUNT(*) FROM {_OPS_SCHEMA}.source_call_ledger"
            " WHERE source_id = ? AND called_at >= ?",
            [source_id, cutoff],
        ).fetchone()
        return row[0] if row else 0

    # ── Worker state ───────────────────────────────────────────────────

    def upsert_worker_state(self, state: WorkerState) -> None:
        self._con.execute(
            f"INSERT INTO {_OPS_SCHEMA}.worker_state "
            "(worker_id, started_at, heartbeat_at, current_run_id, version) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (worker_id) DO UPDATE SET"
            "  heartbeat_at = EXCLUDED.heartbeat_at,"
            "  current_run_id = EXCLUDED.current_run_id,"
            "  version = EXCLUDED.version",
            [
                state.worker_id,
                state.started_at or _utcnow(),
                state.heartbeat_at or _utcnow(),
                state.current_run_id,
                state.version,
            ],
        )

    def list_workers(self) -> list[WorkerState]:
        rows = self._con.execute(
            f"SELECT * FROM {_OPS_SCHEMA}.worker_state ORDER BY heartbeat_at DESC"
        ).fetchall()
        return [
            WorkerState(
                worker_id=r[0],
                started_at=r[1],
                heartbeat_at=r[2],
                current_run_id=r[3],
                version=r[4],
            )
            for r in rows
        ]

    # ── Symbol registry ────────────────────────────────────────────────

    def list_symbols(self, active_only: bool = True) -> list[SymbolEntry]:
        if active_only:
            rows = self._con.execute(
                f"SELECT symbol, added_at, removed_at, added_by, metadata"
                f" FROM {_OPS_SCHEMA}.symbol_registry WHERE removed_at IS NULL"
                " ORDER BY symbol"
            ).fetchall()
        else:
            rows = self._con.execute(
                f"SELECT symbol, added_at, removed_at, added_by, metadata"
                f" FROM {_OPS_SCHEMA}.symbol_registry ORDER BY symbol"
            ).fetchall()
        return [
            SymbolEntry(
                symbol=r[0], added_at=r[1], removed_at=r[2], added_by=r[3] or "auto", metadata=r[4]
            )
            for r in rows
        ]

    def add_symbol(self, symbol: str, added_by: str = "auto") -> SymbolEntry:
        now = _utcnow()
        existing = self.get_symbol(symbol)
        if existing and existing.removed_at is None:
            return existing
        if existing and existing.removed_at is not None:
            self._con.execute(
                f"UPDATE {_OPS_SCHEMA}.symbol_registry"
                " SET removed_at = NULL, added_by = ? WHERE symbol = ?",
                [added_by, symbol],
            )
        else:
            self._con.execute(
                f"INSERT INTO {_OPS_SCHEMA}.symbol_registry (symbol, added_at, added_by)"
                " VALUES (?, ?, ?)",
                [symbol, now, added_by],
            )
        return SymbolEntry(symbol=symbol, added_at=now, added_by=added_by)

    def remove_symbol(self, symbol: str) -> SymbolEntry | None:
        self._con.execute(
            f"UPDATE {_OPS_SCHEMA}.symbol_registry"
            " SET removed_at = ? WHERE symbol = ? AND removed_at IS NULL",
            [_utcnow(), symbol],
        )
        return self.get_symbol(symbol)

    def get_symbol(self, symbol: str) -> SymbolEntry | None:
        row = self._con.execute(
            f"SELECT symbol, added_at, removed_at, added_by, metadata"
            f" FROM {_OPS_SCHEMA}.symbol_registry WHERE symbol = ?",
            [symbol],
        ).fetchone()
        if not row:
            return None
        return SymbolEntry(
            symbol=row[0],
            added_at=row[1],
            removed_at=row[2],
            added_by=row[3] or "auto",
            metadata=row[4],
        )

    def list_symbol_source_overrides(self) -> list[SymbolSourceOverride]:
        rows = self._con.execute(
            f"SELECT symbol, source_id, reason, updated_by, updated_at"
            f" FROM {_OPS_SCHEMA}.symbol_source_override ORDER BY symbol"
        ).fetchall()
        return [
            SymbolSourceOverride(
                symbol=r[0],
                source_id=r[1],
                reason=r[2] or "",
                updated_by=r[3] or "operator",
                updated_at=r[4],
            )
            for r in rows
        ]

    def get_symbol_source_override(self, symbol: str) -> SymbolSourceOverride | None:
        row = self._con.execute(
            f"SELECT symbol, source_id, reason, updated_by, updated_at"
            f" FROM {_OPS_SCHEMA}.symbol_source_override WHERE symbol = ?",
            [symbol],
        ).fetchone()
        if not row:
            return None
        return SymbolSourceOverride(
            symbol=row[0],
            source_id=row[1],
            reason=row[2] or "",
            updated_by=row[3] or "operator",
            updated_at=row[4],
        )

    def set_symbol_source_override(
        self,
        symbol: str,
        source_id: str,
        reason: str = "",
    ) -> SymbolSourceOverride:
        self._con.execute(
            f"INSERT INTO {_OPS_SCHEMA}.symbol_source_override"
            " (symbol, source_id, reason, updated_at)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT (symbol) DO UPDATE SET"
            "  source_id = EXCLUDED.source_id,"
            "  reason = EXCLUDED.reason,"
            "  updated_at = EXCLUDED.updated_at",
            [symbol, source_id, reason, _utcnow()],
        )
        return SymbolSourceOverride(symbol=symbol, source_id=source_id, reason=reason)

    def remove_symbol_source_override(self, symbol: str) -> bool:
        self._con.execute(
            f"DELETE FROM {_OPS_SCHEMA}.symbol_source_override WHERE symbol = ?",
            [symbol],
        )
        return self._con.execute("SELECT changes()").fetchone()[0] > 0


class MemoryJobStore:
    """In-memory JobStore for testing."""

    def __init__(self) -> None:
        self._job_defs: dict[str, JobDefinition] = {}
        self._runs: dict[str, JobRun] = {}
        self._source_overrides: dict[str, SourceRateLimitOverride] = {}
        self._call_ledger: list[SourceCallRecord] = []
        self._workers: dict[str, WorkerState] = {}
        self._symbols: dict[str, SymbolEntry] = {}
        self._symbol_source_overrides: dict[str, SymbolSourceOverride] = {}

    # ── Job definitions ─────────────────────────────────────────────────

    def list_job_defs(self) -> list[JobDefinition]:
        return sorted(self._job_defs.values(), key=lambda j: (j.priority, j.job_name))

    def get_job_def(self, job_name: str) -> JobDefinition | None:
        return self._job_defs.get(job_name)

    def seed_job_defs(self, defs: list[JobDefinition]) -> None:
        for jd in defs:
            existing = self._job_defs.get(jd.job_name)
            if existing:
                for k, v in jd.__dict__.items():
                    if k not in ("job_name", "job_type", "created_at", "updated_at"):
                        setattr(existing, k, v)
            else:
                self._job_defs[jd.job_name] = jd

    def update_job_def(self, job_name: str, **kwargs: Any) -> JobDefinition | None:
        allowed = {"enabled", "hold", "schedule_json", "max_attempts", "priority"}
        jd = self._job_defs.get(job_name)
        if jd is None:
            return None
        for k, v in kwargs.items():
            if k not in allowed:
                raise ValueError(f"Cannot update {k} on job definition")
            setattr(jd, k, v)
        return jd

    # ── Job runs ───────────────────────────────────────────────────────

    def list_runs(
        self,
        status: str | None = None,
        job_name: str | None = None,
        source_id: str | None = None,
        dataset: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[JobRun]:
        result = list(self._runs.values())
        if status:
            result = [r for r in result if r.status == status]
        if job_name:
            result = [r for r in result if r.job_name == job_name]
        if source_id:
            result = [r for r in result if r.source_id == source_id]
        if dataset:
            result = [r for r in result if r.dataset == dataset]
        result.sort(key=lambda r: r.created_at or _utcnow(), reverse=True)
        return result[offset : offset + limit] if offset else result[:limit]

    def get_run(self, run_id: str) -> JobRun | None:
        return self._runs.get(run_id)

    def create_run(self, run: JobRun) -> JobRun:
        run.run_id = run.run_id or _new_id()
        run.created_at = run.created_at or _utcnow()
        run.scheduled_at = run.scheduled_at or run.created_at
        self._runs[run.run_id] = run
        return run

    def claim_next(self, worker_id: str) -> JobRun | None:
        candidates = sorted(
            [
                r
                for r in self._runs.values()
                if r.status in ("queued", "deferred")
                and r.scheduled_at is not None
                and r.scheduled_at <= _utcnow()
            ],
            key=lambda r: (r.priority, r.scheduled_at or _utcnow()),
        )
        for r in candidates:
            jd = self._job_defs.get(r.job_name)
            if jd and not jd.enabled:
                continue
            if jd and jd.hold:
                continue
            override = self._source_overrides.get(r.source_id or "")
            if override and override.hold:
                continue
            r.status = "running"
            r.started_at = _utcnow()
            r.heartbeat_at = _utcnow()
            r.worker_id = worker_id
            r.attempt += 1
            return r
        return None

    def succeed_run(self, run_id: str, result: dict[str, Any]) -> None:
        r = self._runs.get(run_id)
        if r:
            r.status = "succeeded"
            r.finished_at = _utcnow()
            r.result_json = result

    def fail_run(self, run_id: str, failure: dict[str, Any]) -> None:
        r = self._runs.get(run_id)
        if r:
            r.status = "failed"
            r.finished_at = _utcnow()
            r.failure_json = failure

    def defer_run(self, run_id: str, retry_at: datetime | None = None) -> None:
        r = self._runs.get(run_id)
        if r:
            r.status = "deferred"
            r.scheduled_at = retry_at or (_utcnow() + timedelta(minutes=5))

    def quota_exhausted_run(self, run_id: str, failure: dict[str, Any]) -> None:
        r = self._runs.get(run_id)
        if r:
            r.status = "quota_exhausted"
            r.finished_at = _utcnow()
            r.failure_json = failure

    def cancel_run(self, run_id: str) -> bool:
        r = self._runs.get(run_id)
        if r is None or r.status not in ("queued", "deferred"):
            return False
        r.status = "cancelled"
        r.finished_at = _utcnow()
        return True

    def requeue_run(self, run_id: str) -> JobRun | None:
        existing = self._runs.get(run_id)
        if existing is None or existing.status not in ("failed", "quota_exhausted"):
            return None
        new_run = JobRun(
            run_id=_new_id(),
            job_name=existing.job_name,
            job_type=existing.job_type,
            status="queued",
            idempotency_key=f"{existing.idempotency_key}:retry:{existing.attempt + 1}",
            params_json=existing.params_json,
            requested_for_date=existing.requested_for_date,
            source_id=existing.source_id,
            dataset=existing.dataset,
            priority=existing.priority,
            max_attempts=existing.max_attempts,
            scheduled_at=_utcnow(),
        )
        return self.create_run(new_run)

    # ── Source budgets ─────────────────────────────────────────────────

    def list_sources(self) -> list[SourceWithLimits]:
        from alpha_lake.config import get_config

        cfg = get_config()
        from alpha_lake.secrets import get_store

        store = get_store()
        now = _utcnow()
        sources: list[SourceWithLimits] = []

        seen: set[str] = set()
        for sid, sc in sorted(cfg.sources.items()):
            seen.add(sid)
            override = self._source_overrides.get(sid)
            has_key = store.get(f"{sid}_api_key") is not None
            calls_last_min = sum(
                1
                for c in self._call_ledger
                if c.source_id == sid and c.called_at and c.called_at > now - timedelta(seconds=60)
            )
            calls_last_day = sum(
                1
                for c in self._call_ledger
                if c.source_id == sid
                and c.called_at
                and c.called_at > now - timedelta(seconds=86400)
            )
            swl = SourceWithLimits(
                source_id=sid,
                requires_key=sc.requires_key,
                has_key=has_key or bool(sc.api_key),
                configured_rate_limit_per_sec=sc.rate_limit_per_sec,
                configured_rate_limit_per_min=sc.rate_limit_per_min,
                configured_rate_limit_per_day=sc.rate_limit_per_day,
                effective_rate_limit_per_sec=(
                    override.rate_limit_per_sec
                    if override and override.rate_limit_per_sec is not None
                    else sc.rate_limit_per_sec
                ),
                effective_rate_limit_per_min=(
                    override.rate_limit_per_min
                    if override and override.rate_limit_per_min is not None
                    else sc.rate_limit_per_min
                ),
                effective_rate_limit_per_day=(
                    override.rate_limit_per_day
                    if override and override.rate_limit_per_day is not None
                    else sc.rate_limit_per_day
                ),
                hold=override.hold if override else False,
                calls_last_min=calls_last_min,
                calls_last_day=calls_last_day,
            )
            sources.append(swl)

        for sid, ov in self._source_overrides.items():
            if sid not in seen:
                sources.append(
                    SourceWithLimits(
                        source_id=sid,
                        hold=ov.hold,
                        effective_rate_limit_per_sec=ov.rate_limit_per_sec,
                        effective_rate_limit_per_min=ov.rate_limit_per_min,
                        effective_rate_limit_per_day=ov.rate_limit_per_day,
                    )
                )

        return sources

    def get_source(self, source_id: str) -> SourceWithLimits | None:
        for s in self.list_sources():
            if s.source_id == source_id:
                return s
        return None

    def set_source_hold(self, source_id: str, hold: bool, reason: str = "") -> None:
        override = self._source_overrides.get(source_id)
        if override:
            override.hold = hold
            override.reason = reason
        else:
            self._source_overrides[source_id] = SourceRateLimitOverride(
                source_id=source_id, hold=hold, reason=reason, updated_at=_utcnow()
            )

    def set_rate_limit(
        self,
        source_id: str,
        per_sec: float | None = None,
        per_min: int | None = None,
        per_day: int | None = None,
        reason: str = "",
    ) -> None:
        from alpha_lake.config import get_config

        cfg = get_config()
        sc = cfg.sources.get(source_id)
        if sc:
            if per_sec is not None and per_sec > sc.rate_limit_per_sec:
                raise ValueError(
                    f"Rate limit per-sec {per_sec} exceeds"
                    f" configured maximum {sc.rate_limit_per_sec}"
                )
            if (
                per_min is not None
                and sc.rate_limit_per_min is not None
                and per_min > sc.rate_limit_per_min
            ):
                raise ValueError(
                    f"Rate limit per-min {per_min} exceeds"
                    f" configured maximum {sc.rate_limit_per_min}"
                )
            if (
                per_day is not None
                and sc.rate_limit_per_day is not None
                and per_day > sc.rate_limit_per_day
            ):
                raise ValueError(
                    f"Rate limit per-day {per_day} exceeds"
                    f" configured maximum {sc.rate_limit_per_day}"
                )
        override = self._source_overrides.get(source_id)
        if override:
            if per_sec is not None:
                override.rate_limit_per_sec = per_sec
            if per_min is not None:
                override.rate_limit_per_min = per_min
            if per_day is not None:
                override.rate_limit_per_day = per_day
            override.reason = reason
            override.updated_at = _utcnow()
        else:
            self._source_overrides[source_id] = SourceRateLimitOverride(
                source_id=source_id,
                rate_limit_per_sec=per_sec,
                rate_limit_per_min=per_min,
                rate_limit_per_day=per_day,
                reason=reason,
                updated_at=_utcnow(),
            )

    # ── Call ledger ────────────────────────────────────────────────────

    def record_call(
        self,
        source_id: str,
        endpoint: str,
        status: str,
        job_run_id: str | None = None,
        cost_units: int = 1,
    ) -> None:
        self._call_ledger.append(
            SourceCallRecord(
                call_id=_new_id(),
                source_id=source_id,
                endpoint=endpoint,
                job_run_id=job_run_id,
                called_at=_utcnow(),
                status=status,
                cost_units=cost_units,
            )
        )

    def count_calls_in_window(self, source_id: str, window_secs: int) -> int:
        cutoff = _utcnow() - timedelta(seconds=window_secs)
        return sum(
            1
            for c in self._call_ledger
            if c.source_id == source_id and c.called_at and c.called_at > cutoff
        )

    # ── Worker state ───────────────────────────────────────────────────

    def upsert_worker_state(self, state: WorkerState) -> None:
        self._workers[state.worker_id] = state

    def list_workers(self) -> list[WorkerState]:
        return sorted(
            self._workers.values(), key=lambda w: w.heartbeat_at or _utcnow(), reverse=True
        )

    # ── Symbol registry ────────────────────────────────────────────────

    def list_symbols(self, active_only: bool = True) -> list[SymbolEntry]:
        result = list(self._symbols.values())
        if active_only:
            result = [s for s in result if s.removed_at is None]
        return sorted(result, key=lambda s: s.symbol)

    def add_symbol(self, symbol: str, added_by: str = "auto") -> SymbolEntry:
        existing = self._symbols.get(symbol)
        if existing and existing.removed_at is None:
            return existing
        if existing and existing.removed_at is not None:
            existing.removed_at = None
            existing.added_by = added_by
            return existing
        entry = SymbolEntry(symbol=symbol, added_at=_utcnow(), added_by=added_by)
        self._symbols[symbol] = entry
        return entry

    def remove_symbol(self, symbol: str) -> SymbolEntry | None:
        entry = self._symbols.get(symbol)
        if entry:
            entry.removed_at = _utcnow()
        return entry

    def get_symbol(self, symbol: str) -> SymbolEntry | None:
        return self._symbols.get(symbol)

    def list_symbol_source_overrides(self) -> list[SymbolSourceOverride]:
        return list(self._symbol_source_overrides.values())

    def get_symbol_source_override(self, symbol: str) -> SymbolSourceOverride | None:
        return self._symbol_source_overrides.get(symbol)

    def set_symbol_source_override(
        self,
        symbol: str,
        source_id: str,
        reason: str = "",
    ) -> SymbolSourceOverride:
        override = SymbolSourceOverride(
            symbol=symbol, source_id=source_id, reason=reason, updated_at=_utcnow()
        )
        self._symbol_source_overrides[symbol] = override
        return override

    def remove_symbol_source_override(self, symbol: str) -> bool:
        return self._symbol_source_overrides.pop(symbol, None) is not None
