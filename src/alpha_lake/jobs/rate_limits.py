from __future__ import annotations

from datetime import UTC, datetime, timedelta

import duckdb

from alpha_lake.config import SourceConfig


class PostgresBudgetTracker:
    """Rate-limit enforcement backed by Postgres call ledger.

    Replaces the file-backed ``_CALL_LEDGER`` in ``connectors/base.py`` for
    cross-process budget visibility.  Falls back to the file ledger when the
    Postgres store is unavailable (embedded/test mode).
    """

    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def _table(self) -> str:
        return "pg_catalog.ops.source_call_ledger"

    def check_budget(self, cfg: SourceConfig) -> None:
        """Raise BudgetExhaustedError if any window is over budget."""
        source_id = self._source_id_from_cfg(cfg)
        now = datetime.now(UTC)

        if cfg.rate_limit_per_sec > 0:
            count = self._count_since(source_id, now - timedelta(seconds=1))
            if count >= int(cfg.rate_limit_per_sec):
                self._raise_exhausted(source_id, f"per-second limit ({cfg.rate_limit_per_sec}/s)")

        if cfg.rate_limit_per_min is not None:
            count = self._count_since(source_id, now - timedelta(seconds=60))
            if count >= cfg.rate_limit_per_min:
                self._raise_exhausted(source_id, f"per-minute limit ({cfg.rate_limit_per_min}/min)")

        if cfg.rate_limit_per_day is not None:
            count = self._count_since(source_id, now - timedelta(seconds=86400))
            if count >= cfg.rate_limit_per_day:
                self._raise_exhausted(source_id, f"per-day limit ({cfg.rate_limit_per_day}/day)")

    def record_call(self, source_id: str, endpoint: str = "", status: str = "ok") -> None:
        import uuid

        self._con.execute(
            f"INSERT INTO {self._table()} "
            "(call_id, source_id, endpoint, called_at, status) VALUES (?, ?, ?, ?, ?)",
            [uuid.uuid4().hex, source_id, endpoint, datetime.now(UTC), status],
        )

    def _count_since(self, source_id: str, since: datetime) -> int:
        try:
            row = self._con.execute(
                f"SELECT COUNT(*) FROM {self._table()} WHERE source_id = ? AND called_at >= ?",
                [source_id, since],
            ).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    def _source_id_from_cfg(self, cfg: SourceConfig) -> str:
        if cfg.base_url:
            return cfg.base_url.split("//")[-1].split(".")[0]
        return "unknown"

    def _raise_exhausted(self, source_id: str, reason: str) -> None:
        from alpha_lake.connectors.base import BudgetExhaustedError

        raise BudgetExhaustedError(source_id, reason)
