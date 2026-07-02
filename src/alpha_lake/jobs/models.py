from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol, runtime_checkable


@dataclass
class JobDefinition:
    job_name: str
    job_type: str
    enabled: bool = True
    hold: bool = False
    schedule_kind: str = "manual"
    schedule_json: dict[str, Any] = field(default_factory=dict)
    params_json: dict[str, Any] = field(default_factory=dict)
    max_attempts: int = 3
    priority: int = 100
    concurrency_key: str = ""
    source_id: str | None = None
    dataset: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def last_run(self) -> JobRun | None:
        return None

    @property
    def next_due_at(self) -> datetime | None:
        return None

    @property
    def last_status(self) -> str | None:
        return None


@dataclass
class JobRun:
    run_id: str
    job_name: str
    job_type: str
    status: str
    idempotency_key: str
    params_json: dict[str, Any] = field(default_factory=dict)
    requested_for_date: date | None = None
    source_id: str | None = None
    dataset: str | None = None
    priority: int = 100
    attempt: int = 0
    max_attempts: int = 3
    scheduled_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    heartbeat_at: datetime | None = None
    worker_id: str | None = None
    result_json: dict[str, Any] | None = None
    failure_json: dict[str, Any] | None = None
    ingestion_run_id: str | None = None
    ducklake_snapshot_id: str | None = None
    created_at: datetime | None = None


@dataclass
class SourceRateLimitOverride:
    source_id: str
    hold: bool = False
    rate_limit_per_sec: float | None = None
    rate_limit_per_min: int | None = None
    rate_limit_per_day: int | None = None
    reason: str = ""
    updated_by: str = "operator"
    updated_at: datetime | None = None


@dataclass
class SourceCallRecord:
    call_id: str
    source_id: str
    endpoint: str = ""
    job_run_id: str | None = None
    called_at: datetime | None = None
    status: str = ""
    cost_units: int = 1
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkerState:
    worker_id: str
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    current_run_id: str | None = None
    version: str = ""
    paused: bool = False


@dataclass
class SymbolEntry:
    symbol: str
    added_at: datetime | None = None
    removed_at: datetime | None = None
    added_by: str = "auto"
    metadata: str | None = None


@dataclass
class SymbolSourceOverride:
    symbol: str
    source_id: str
    reason: str = ""
    updated_by: str = "operator"
    updated_at: datetime | None = None


DEFAULT_JOB_DEFS: list[JobDefinition] = [
    JobDefinition(
        job_name="source.health",
        job_type="source_health",
        schedule_kind="interval",
        schedule_json={"interval_seconds": 3600},
        concurrency_key="health",
        max_attempts=3,
        priority=100,
    ),
    JobDefinition(
        job_name="bars.bootstrap.active",
        job_type="bars_bootstrap",
        schedule_kind="manual",
        params_json={"symbols": "active", "source_id": "stooq", "lookback_years": 3},
        concurrency_key="bars",
        source_id="stooq",
        dataset="bars",
        max_attempts=3,
        priority=40,
    ),
    JobDefinition(
        job_name="bars.refresh.eod",
        job_type="bars_refresh",
        schedule_kind="market_close",
        schedule_json={"calendar": "XNYS", "offset_minutes": 30},
        params_json={
            "symbols": "active",
            "from_policy": "last_missing_or_previous_session",
            "to_policy": "latest_closed_session",
        },
        concurrency_key="bars",
        dataset="bars",
        max_attempts=3,
        priority=10,
    ),
    JobDefinition(
        job_name="bars.refresh.morning",
        job_type="bars_refresh",
        schedule_kind="daily_time",
        schedule_json={
            "timezone": "Europe/Amsterdam",
            "time": "07:05",
            "calendar": "XNYS",
            "skip_non_trading_days": True,
        },
        params_json={"symbols": "active", "source_id": "yahoo"},
        concurrency_key="bars",
        dataset="bars",
        max_attempts=3,
        priority=5,
    ),
    JobDefinition(
        job_name="indicators.compute.eod",
        job_type="indicators_compute",
        schedule_kind="daily_time",
        schedule_json={
            "timezone": "Europe/Amsterdam",
            "time": "07:15",
            "calendar": "XNYS",
            "skip_non_trading_days": True,
        },
        params_json={"symbols": "active", "trigger": "after_bars_refresh"},
        concurrency_key="indicators",
        dataset="technical_indicators",
        max_attempts=3,
        priority=20,
    ),
    JobDefinition(
        job_name="stooq.rebuild",
        job_type="stooq_rebuild",
        schedule_kind="manual",
        concurrency_key="stooq",
        max_attempts=3,
        priority=50,
    ),
    JobDefinition(
        job_name="datasets.refresh.core",
        job_type="dataset_refresh",
        schedule_kind="daily_time",
        schedule_json={
            "timezone": "Europe/Amsterdam",
            "time": "07:00",
        },
        params_json={
            "datasets": [
                "earnings_calendar",
                "insider_tx",
                "attention_metrics",
                "news",
                "sentiment",
                "analyst_estimates",
                "macro_series",
            ],
        },
        concurrency_key="datasets",
        max_attempts=3,
        priority=30,
    ),
]


@dataclass
class SourceWithLimits:
    source_id: str
    requires_key: bool = True
    has_key: bool = False
    configured_rate_limit_per_sec: float = 10.0
    configured_rate_limit_per_min: int | None = None
    configured_rate_limit_per_day: int | None = None
    effective_rate_limit_per_sec: float | None = None
    effective_rate_limit_per_min: int | None = None
    effective_rate_limit_per_day: int | None = None
    hold: bool = False
    calls_last_min: int = 0
    calls_last_day: int = 0
    next_day_reset_at: str | None = None


@runtime_checkable
class JobStore(Protocol):
    def list_job_defs(self) -> list[JobDefinition]: ...
    def get_job_def(self, job_name: str) -> JobDefinition | None: ...
    def seed_job_defs(self, defs: list[JobDefinition]) -> None: ...
    def update_job_def(self, job_name: str, **kwargs: Any) -> JobDefinition | None: ...

    def list_runs(
        self,
        status: str | None = None,
        job_name: str | None = None,
        source_id: str | None = None,
        dataset: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[JobRun]: ...
    def get_run(self, run_id: str) -> JobRun | None: ...
    def create_run(self, run: JobRun) -> JobRun: ...
    def claim_next(self, worker_id: str) -> JobRun | None: ...
    def succeed_run(self, run_id: str, result: dict[str, Any]) -> None: ...
    def fail_run(self, run_id: str, failure: dict[str, Any]) -> None: ...
    def defer_run(self, run_id: str, retry_at: datetime | None = None) -> None: ...
    def quota_exhausted_run(self, run_id: str, failure: dict[str, Any]) -> None: ...
    def cancel_run(self, run_id: str) -> bool: ...
    def requeue_run(self, run_id: str) -> JobRun | None: ...

    def list_sources(self) -> list[SourceWithLimits]: ...
    def get_source(self, source_id: str) -> SourceWithLimits | None: ...
    def set_source_hold(self, source_id: str, hold: bool, reason: str = "") -> None: ...
    def set_rate_limit(
        self,
        source_id: str,
        per_sec: float | None = None,
        per_min: int | None = None,
        per_day: int | None = None,
        reason: str = "",
    ) -> None: ...

    def record_call(
        self,
        source_id: str,
        endpoint: str,
        status: str,
        job_run_id: str | None = None,
        cost_units: int = 1,
    ) -> None: ...
    def count_calls_in_window(self, source_id: str, window_secs: int) -> int: ...

    def upsert_worker_state(self, state: WorkerState) -> None: ...
    def list_workers(self) -> list[WorkerState]: ...

    def list_symbols(self, active_only: bool = True) -> list[SymbolEntry]: ...
    def add_symbol(self, symbol: str, added_by: str = "auto") -> SymbolEntry: ...
    def remove_symbol(self, symbol: str) -> SymbolEntry | None: ...
    def get_symbol(self, symbol: str) -> SymbolEntry | None: ...

    def list_symbol_source_overrides(self) -> list[SymbolSourceOverride]: ...
    def get_symbol_source_override(self, symbol: str) -> SymbolSourceOverride | None: ...
    def set_symbol_source_override(
        self,
        symbol: str,
        source_id: str,
        reason: str = "",
    ) -> SymbolSourceOverride: ...
    def remove_symbol_source_override(self, symbol: str) -> bool: ...
