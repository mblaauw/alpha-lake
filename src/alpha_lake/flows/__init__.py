from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

import duckdb

from alpha_lake.canonical import DATASETS, write_bars, write_dataset
from alpha_lake.cli_ui import warn
from alpha_lake.clock import get_clock
from alpha_lake.connectors import ConnectorFn, get_connector, has_api_key
from alpha_lake.normalize import bars_from_json
from alpha_lake.quality import check_market_sanity
from alpha_lake.raw import archive
from alpha_lake.source_registry import get_primary_source, get_source_precedence

StepCallback = Callable[[int, int | None, str], None]
"""``fn(current, total, label)`` called after each processing step.

*current* is the 0‑based index of the completed step, *total* is the
expected count (or *None* when the total is unknown), and *label* is a
human‑readable description of the step just completed.
"""


def _missing_dates(
    con: duckdb.DuckDBPyConnection,
    table: str,
    sid: str,
    from_date: str = "",
    to_date: str = "",
) -> list[str]:
    """Return ISO date strings missing from the canonical table for *sid*.

    When the entire requested range is already covered the list is empty —
    the caller can skip the API call / synthetic generation entirely.

    *from_date* and *to_date* are ISO strings (or empty for unbounded).
    When both are empty the helper checks for *any* existing data and returns
    ``['<today>']`` when the table is empty or ``[]`` when data already exists.
    """
    try:
        existing = {
            r[0]
            for r in con.execute(
                f"""SELECT DISTINCT effective_date FROM {table}
                    WHERE security_id = ?
                      AND (? = '' OR effective_date >= DATE(?))
                      AND (? = '' OR effective_date <= DATE(?))""",
                [sid, from_date, from_date, to_date, to_date],
            ).fetchall()
        }
    except duckdb.CatalogException:
        existing = set()

    f = date.fromisoformat(from_date) if from_date else None
    t = date.fromisoformat(to_date) if to_date else None

    if f is None and t is None:
        if existing:
            return []
        return [date.today().isoformat()]

    if f is None:
        f = min(existing, default=date.today())
    if t is None:
        t = max(existing, default=date.today())

    missing: list[str] = []
    d = f
    while d <= t:
        if d not in existing:
            missing.append(d.isoformat())
        d += timedelta(days=1)
    return missing


def _dataset_has_coverage(
    con: duckdb.DuckDBPyConnection,
    table: str,
    id_col: str,
    sid: str,
    from_date: str = "",
    to_date: str = "",
    source_id: str | None = None,
) -> bool:
    """Check if canonical *table* already has data for *sid* in [from_date, to_date].

    When both date bounds are empty, checks for *any* row with that ID.
    When *source_id* is given, also checks ``source_id`` column — this
    prevents source-blind false positives (e.g. Finnhub news causing
    Marketaux news to be skipped).
    Returns ``True`` when all requested data already exists — caller can skip.
    """
    source_clause = " AND source_id = ?" if source_id else ""
    source_params = [source_id] if source_id else []
    try:
        if from_date or to_date:
            rows = con.execute(
                f"""SELECT 1 FROM {table}
                    WHERE {id_col} = ?
                      AND (? = '' OR effective_date >= DATE(?))
                      AND (? = '' OR effective_date <= DATE(?))
                      {source_clause}
                    LIMIT 1""",
                [sid, from_date, from_date, to_date, to_date, *source_params],
            ).fetchall()
            return len(rows) > 0
        rows = con.execute(
            f"SELECT 1 FROM {table} WHERE {id_col} = ? {source_clause} LIMIT 1",
            [sid, *source_params],
        ).fetchall()
        return len(rows) > 0
    except Exception:
        return False


def _synthetic_payload(from_date: str, to_date: str, clock_now: datetime, sid: str = "") -> bytes:
    """Generate synthetic raw payload for offline/CI mode.

    When *sid* is given, uses a deterministic seed so the same symbol
    always produces the same OHLCV series. The ``source_id`` is set to
    ``"demo"`` so the data is clearly distinguishable from real data.
    """
    import hashlib
    import json
    import random

    seed = int(hashlib.sha256(sid.encode()).hexdigest()[:8], 16) if sid else 42
    rng = random.Random(seed)

    date_str = from_date or to_date or clock_now.date().isoformat()
    base = 50.0 + rng.uniform(0, 400)
    records = []
    for day_offset in range(252):
        d = date.fromisoformat(date_str) - timedelta(days=day_offset)
        daily_vol = base * (0.95 + rng.random() * 0.1)
        o = round(daily_vol, 2)
        high_v = round(o * (1 + rng.random() * 0.03), 2)
        low_v = round(o * (1 - rng.random() * 0.03), 2)
        close_v = round(o + rng.uniform(-0.5, 0.5), 2)
        v = int(1e6 + rng.random() * 1e7)
        records.append(
            {
                "date": d.isoformat(),
                "open": o,
                "high": high_v,
                "low": low_v,
                "close": close_v,
                "volume": v,
            }
        )
    records.sort(key=lambda r: r["date"])
    return json.dumps(records).encode()


async def _fetch_and_ingest(
    con: duckdb.DuckDBPyConnection,
    connector: ConnectorFn,
    sid: str,
    src: str,
    from_date: str,
    to_date: str,
    run_id: str,
    clock_now: datetime,
) -> int:
    """Fetch from connector, archive, normalize, write."""
    raw_fetch = await connector(symbol=sid, from_date=from_date, to_date=to_date)
    raw_bytes = raw_fetch.body
    content_hash = archive(raw_bytes)

    import json

    raw_data = json.loads(raw_bytes)
    records = raw_data if isinstance(raw_data, list) else [raw_data]

    df = bars_from_json(
        raw=records,
        security_id=sid,
        source_id=src,
        source_fetch_id=raw_fetch.manifest.get("request_params_hash", f"fetch_{sid}"),
        ingestion_run_id=run_id,
        content_hash=content_hash,
        available_at=clock_now,
        ingested_at=clock_now,
    )
    df = check_market_sanity(df)
    return write_bars(con, df)


def _ingest_synthetic(
    con: duckdb.DuckDBPyConnection,
    sid: str,
    from_date: str,
    to_date: str,
    run_id: str,
    clock_now: datetime,
) -> int:
    """Synthetic data path for offline/CI mode."""
    raw_bytes = _synthetic_payload(from_date, to_date, clock_now, sid)
    content_hash = archive(raw_bytes)

    import json

    raw_data = json.loads(raw_bytes)
    records = raw_data if isinstance(raw_data, list) else [raw_data]

    df = bars_from_json(
        raw=records,
        security_id=sid,
        source_id="demo",
        source_fetch_id=f"fetch_{sid}",
        ingestion_run_id=run_id,
        content_hash=content_hash,
        available_at=clock_now,
    )
    df = check_market_sanity(df)
    return write_bars(con, df)


def ingest_bars(
    con: duckdb.DuckDBPyConnection,
    security_ids: list[str],
    from_date: str = "",
    to_date: str = "",
    source_id: str | None = None,
    on_step: StepCallback | None = None,
) -> int:
    """Run the full bars ingestion pipeline.

    Tries the connector layer first (online); falls back to synthetic
    data when no API credentials are available (offline/CI).

    1. Fetch raw data (connector or synthetic)
    2. Archive raw bytes
    3. Normalize to Polars DataFrame
    4. Validate with market sanity checks
    5. Write to canonical table
    """
    src = source_id or get_primary_source("bars_daily")
    if not src:
        raise ValueError("No source configured for bars_daily")

    connector = get_connector(src, "bars_daily")
    creds = has_api_key(src)
    clock_now = get_clock().now()
    run_id = f"run_{clock_now.strftime('%Y%m%d_%H%M%S')}"
    total = 0
    n = len(security_ids)

    if connector and creds:

        async def _run_all():
            t = 0
            for i, sid in enumerate(security_ids):
                if on_step:
                    on_step(i, n, sid)
                missing = _missing_dates(con, "lake_bars", sid, from_date, to_date)
                if not missing:
                    continue
                t += await _fetch_and_ingest(
                    con,
                    connector,
                    sid,
                    src,
                    missing[0],
                    missing[-1],
                    run_id,
                    clock_now,
                )
            return t

        total = asyncio.run(_run_all())
    else:
        warn(
            f"No API key for {src} — generating synthetic data. "
            "Set {src}_API_KEY in .env for real ingestion."
        )
        for i, sid in enumerate(security_ids):
            if on_step:
                on_step(i, n, sid)
            missing = _missing_dates(con, "lake_bars", sid, from_date, to_date)
            if not missing:
                continue
            total += _ingest_synthetic(con, sid, missing[0], missing[-1], run_id, clock_now)

    if on_step:
        on_step(n, n, f"done — {total} bars")

    return total


def backfill_bars(
    con: duckdb.DuckDBPyConnection,
    security_ids: list[str],
    start_date: date,
    end_date: date,
    source_id: str | None = None,
    on_step: StepCallback | None = None,
) -> int:
    """Backfill bars for a date range.

    Iterates through each business day and ingests missing data.
    """
    from alpha_lake.calendar_ import trading_days_in_range

    total = 0
    days = trading_days_in_range(start_date, end_date)
    n = len(security_ids) * len(days)
    step = 0
    for sid in security_ids:
        for dt in days:
            if on_step:
                on_step(step, n, f"{sid} {dt}")
            step += 1
            _r = con.execute(
                "SELECT COUNT(*) FROM lake_bars WHERE security_id = ? AND effective_date = ?",
                [sid, dt],
            ).fetchone()
            existing = _r[0] if _r else 0
            if existing == 0:
                total += ingest_bars(con, [sid], dt.isoformat(), dt.isoformat(), source_id)
    if on_step:
        on_step(n, n, f"done — {total} bars")

    return total


def reparse_bars(
    con: duckdb.DuckDBPyConnection,
    security_ids: list[str],
    effective_date: date | None = None,
    on_step: StepCallback | None = None,
) -> int:
    """Reparse raw archive data and rewrite canonical rows.

    Creates a NEW knowledge-time version: the reparsed row gets a new
    available_at set to reparse time, while preserving content_hash
    pointing to the original raw archive blobs. Both the original and
    the new reparse version coexist in the lake.
    """
    import json

    from alpha_lake.normalize import bars_from_json
    from alpha_lake.quality import check_market_sanity
    from alpha_lake.raw import read_raw

    reparse_ts = get_clock().now()
    total = 0
    all_rows: list[tuple[str, str, str, str, str, Any, Any]] = []
    for sid in security_ids:
        if effective_date:
            rows = con.execute(
                "SELECT content_hash, source_id, source_fetch_id, "
                "ingestion_run_id, available_at, ingested_at "
                "FROM lake_bars WHERE security_id = ? AND effective_date = ?",
                [sid, effective_date],
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT DISTINCT content_hash, source_id, source_fetch_id, ingestion_run_id, "
                "available_at, ingested_at FROM lake_bars WHERE security_id = ?",
                [sid],
            ).fetchall()
        all_rows.extend((sid, *r) for r in rows)

    n = len(all_rows)
    for i, (sid, content_hash, src_id, fetch_id, run_id, _avail_at, ingested_at) in enumerate(
        all_rows
    ):
        if on_step:
            on_step(i, n, f"{sid} #{content_hash[:8]}")
        raw = read_raw(content_hash)
        raw_data = json.loads(raw.decode())
        if isinstance(raw_data, dict):
            raw_data = [raw_data]
        df = bars_from_json(
            raw_data, sid, src_id, fetch_id, run_id, content_hash, reparse_ts, ingested_at
        )
        df = check_market_sanity(df)
        total += write_bars(con, df)
    if on_step:
        on_step(n, n, f"done — {total} rows")

    return total


def compact_dataset(con: duckdb.DuckDBPyConnection, table: str) -> int:
    """Compact a canonical table by removing duplicate versions.

    Keeps only the newest available_at per (natural_key + version_hash).
    Uses window-function dedup for portability across DuckDB, Postgres, and SQLite.
    """
    ds = DATASETS.get(table)
    if not ds:
        raise ValueError(f"No dataset registered for {table}, cannot compact")

    key_cols = ", ".join(ds.natural_keys)
    stg = f"_compact_{table}"

    con.execute(f"""
        CREATE TABLE {stg} AS
        SELECT * EXCLUDE rn FROM (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY {key_cols}, available_at, version_hash
                    ORDER BY available_at
                ) AS rn
            FROM {table}
        ) dup
        WHERE rn = 1
    """)
    con.execute(f"DELETE FROM {table}")
    cols = ", ".join(c[0] for c in con.execute(f"DESCRIBE {stg}").fetchall())
    con.execute(f"INSERT INTO {table} SELECT {cols} FROM {stg}")
    con.execute(f"DROP TABLE IF EXISTS {stg}")

    _r = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return _r[0] if _r else 0


def ingest_dataset(
    con: duckdb.DuckDBPyConnection,
    dataset: str,
    series_id: str | None = None,
    security_id: str | None = None,
    from_date: str = "",
    to_date: str = "",
    source_id: str | None = None,
    cohort: str = "all-stocks",
) -> int:
    """Run the full ingestion pipeline for a generic dataset.

    Fetches from the connector, archives raw data, normalizes to a
    Polars DataFrame, and writes to the canonical table.
    """
    src = source_id
    if not src:
        precedence = get_source_precedence(dataset)
        if precedence:
            src = precedence[0]
        else:
            from alpha_lake.source_registry import get_dataset_sources

            sources = get_dataset_sources(dataset)
            if sources:
                src = next(iter(sources))
    if not src:
        raise ValueError(f"No source configured for {dataset}")

    connector = get_connector(src, dataset)
    if not connector:
        raise ValueError(f"No connector registered for {src}/{dataset}")

    clock_now = get_clock().now()
    run_id = f"run_{clock_now.strftime('%Y%m%d_%H%M%S')}"

    import json

    kwargs: dict = {}
    if dataset == "macro_series":
        kwargs["series_id"] = series_id or "GDP"
        kwargs["from_date"] = from_date
        kwargs["to_date"] = to_date
    elif dataset == "economic_calendar":
        kwargs["from_date"] = from_date or ""
        kwargs["to_date"] = to_date or ""
    elif dataset == "attention_metrics":
        kwargs["ticker"] = security_id or "AAPL"
        kwargs["cohort"] = cohort
    elif dataset == "sentiment" and src == "stocktwits":
        kwargs["symbol"] = security_id or "AAPL"
    elif dataset == "social_posts" and src == "reddit":
        kwargs["subreddit"] = security_id or "wallstreetbets"
    elif dataset in ("insider_tx", "fundamentals") and src == "sec":
        kwargs["cik"] = security_id or "0000320193"
    elif dataset == "news" and src == "tiingo":
        kwargs["tickers"] = security_id or "AAPL"
        if from_date:
            kwargs["start_date"] = from_date
        if to_date:
            kwargs["end_date"] = to_date
    elif dataset in ("earnings_calendar",) and not security_id:
        if from_date:
            kwargs["from_date"] = from_date
        if to_date:
            kwargs["to_date"] = to_date
    elif dataset == "congress_trades":
        pass
    else:
        kwargs["symbol"] = security_id or "AAPL"
        if from_date and dataset not in ("analyst_estimates", "insider_tx"):
            kwargs["from_date"] = from_date
        if to_date and dataset not in ("analyst_estimates", "insider_tx"):
            kwargs["to_date"] = to_date

    # ── Idempotency guard: skip connector if data already in lake ────────
    table_aliases = {
        "news": "news_articles",
        "sentiment": "sentiment_annotations",
    }
    _table = table_aliases.get(dataset, dataset)
    _id_col: str | None = None
    _id_val: str | None = None
    if dataset == "macro_series":
        _id_col = "series_id"
        _id_val = series_id or "GDP"
    elif dataset in ("insider_tx", "analyst_estimates", "fundamentals"):
        _id_col = "security_id"
        _id_val = security_id or "AAPL"
    elif dataset == "economic_calendar":
        _id_col = "event_id"
        _id_val = ""
    elif dataset == "earnings_calendar":
        _id_col = "security_id"
        _id_val = security_id or ""

    # News and sentiment don't have a security_id column — check by source + date
    if dataset in ("news", "sentiment"):
        covered = _dataset_has_coverage(
            con,
            _table,
            "source_id",
            src,
            from_date=from_date,
            to_date=to_date,
        )
        if covered:
            return 0

    # Attention metrics: allow per-cohort ingestion (cohort != default → always fetch)
    if dataset == "attention_metrics" and cohort == "all-stocks":
        covered = _dataset_has_coverage(
            con,
            _table,
            "source_id",
            src,
            from_date=from_date,
            to_date=to_date,
        )
        if covered:
            return 0

    if _id_col and _id_val:
        covered = _dataset_has_coverage(
            con,
            _table,
            _id_col,
            _id_val,
            from_date=from_date,
            to_date=to_date,
            source_id=src,
        )
        if covered:
            return 0

    raw_fetch = asyncio.run(connector(**kwargs))
    raw_bytes = raw_fetch.body
    content_hash = archive(raw_bytes)

    raw_data = json.loads(raw_bytes)
    if dataset == "macro_series" and isinstance(raw_data, dict):
        records = raw_data.get("observations", [raw_data])
    elif dataset == "insider_tx" and isinstance(raw_data, dict):
        records = raw_data.get("data", [raw_data])
    elif dataset == "sentiment" and src == "stocktwits" and isinstance(raw_data, dict):
        records = raw_data.get("messages", [raw_data])
    elif dataset == "attention_metrics" and src == "apewisdom" and isinstance(raw_data, dict):
        records = raw_data.get("results", [raw_data])
    elif src == "marketaux" and isinstance(raw_data, dict):
        records = raw_data.get("data", [raw_data])
    elif isinstance(raw_data, dict):
        records = [raw_data]
    else:
        records = raw_data

    fetch_id = raw_fetch.manifest.get("request_params_hash", f"fetch_{run_id}")

    if dataset == "macro_series":
        from alpha_lake.normalize import macro_series_from_json

        df = macro_series_from_json(
            raw=records,
            series_id=kwargs.get("series_id", series_id or "GDP"),
            source_id=src,
            source_fetch_id=fetch_id,
            ingestion_run_id=run_id,
            content_hash=content_hash,
            available_at=clock_now,
        )
    elif dataset == "news":
        if src == "marketaux":
            from alpha_lake.normalize import marketaux_news_from_json

            df = marketaux_news_from_json(
                raw=records,
                source_id=src,
                source_fetch_id=fetch_id,
                ingestion_run_id=run_id,
                content_hash=content_hash,
                available_at=clock_now,
            )
        else:
            from alpha_lake.normalize import news_from_json

            df = news_from_json(
                raw=records,
                source_id=src,
                source_fetch_id=fetch_id,
                ingestion_run_id=run_id,
                content_hash=content_hash,
                available_at=clock_now,
            )
    elif dataset == "sentiment":
        if src == "marketaux":
            from alpha_lake.normalize import marketaux_sentiment_from_json

            df = marketaux_sentiment_from_json(
                raw=records,
                source_id=src,
                source_fetch_id=fetch_id,
                ingestion_run_id=run_id,
                content_hash=content_hash,
                available_at=clock_now,
            )
        elif src == "stocktwits":
            from alpha_lake.normalize import stocktwits_sentiment_from_json

            df = stocktwits_sentiment_from_json(
                raw=records,
                symbol=kwargs.get("symbol", security_id or "AAPL"),
                source_id=src,
                source_fetch_id=fetch_id,
                ingestion_run_id=run_id,
                content_hash=content_hash,
                available_at=clock_now,
            )
        else:
            from alpha_lake.normalize import sentiment_from_news

            df = sentiment_from_news(
                raw=records,
                source_id=src,
                source_fetch_id=fetch_id,
                ingestion_run_id=run_id,
                content_hash=content_hash,
                available_at=clock_now,
            )
    elif dataset == "economic_calendar":
        from alpha_lake.normalize import economic_calendar_from_json

        df = economic_calendar_from_json(
            raw=records,
            source_id=src,
            source_fetch_id=fetch_id,
            ingestion_run_id=run_id,
            content_hash=content_hash,
            available_at=clock_now,
        )
    elif dataset == "attention_metrics":
        from alpha_lake.normalize import apewisdom_attention_from_json

        df = apewisdom_attention_from_json(
            raw=records,
            ticker=kwargs.get("ticker", security_id or "AAPL"),
            cohort=kwargs.get("cohort", cohort),
            source_id=src,
            source_fetch_id=fetch_id,
            ingestion_run_id=run_id,
            content_hash=content_hash,
            available_at=clock_now,
        )
    elif dataset == "analyst_estimates":
        from alpha_lake.normalize import analyst_estimates_from_json

        df = analyst_estimates_from_json(
            raw=records,
            security_id=kwargs.get("symbol", security_id or "AAPL"),
            source_id=src,
            source_fetch_id=fetch_id,
            ingestion_run_id=run_id,
            content_hash=content_hash,
            available_at=clock_now,
        )
    elif dataset == "insider_tx":
        from alpha_lake.normalize import insider_tx_from_json

        df = insider_tx_from_json(
            raw=records,
            security_id=kwargs.get("symbol", security_id or "AAPL"),
            source_id=src,
            source_fetch_id=fetch_id,
            ingestion_run_id=run_id,
            content_hash=content_hash,
            available_at=clock_now,
        )
    else:
        raise ValueError(f"No normalize function wired for dataset '{dataset}'")

    table_aliases = {
        "news": "news_articles",
        "sentiment": "sentiment_annotations",
    }
    table = table_aliases.get(dataset, dataset)
    if df.is_empty():
        return 0
    return write_dataset(con, table, df)


def compute_indicators(
    con: duckdb.DuckDBPyConnection,
    security_ids: list[str] | None = None,
    as_of: datetime | None = None,
    on_step: StepCallback | None = None,
) -> int:
    """Compute all technical indicators from lake_bars and write to technical_indicators.

    Reads bars for each symbol (with a 300-day lookback to cover 252-period
    calculations), computes all indicators via single-pass batch, and stores
    the result PIT in the technical_indicators table.

    When *security_ids* is None (default), processes every symbol in lake_bars.
    """
    if as_of is None:
        as_of = get_clock().now()

    if security_ids is None:
        rows = con.execute(
            "SELECT DISTINCT security_id FROM lake_bars"
            " WHERE security_id IS NOT NULL AND security_id != '' LIMIT 200"
        ).fetchall()
        security_ids = [str(r[0]) for r in rows if r[0]]

    if not security_ids:
        return 0

    from datetime import timedelta

    from alpha_lake.serving import read_bars_asof

    start = (as_of - timedelta(days=400)).date()
    end = as_of.date()

    bars = read_bars_asof(
        con,
        security_ids=security_ids,
        as_of=as_of,
        start_date=start,
        end_date=end,
    )
    if bars.is_empty():
        return 0

    from alpha_lake.derived.compute import _SPY_SECURITY_ID, compute_all_indicators
    from alpha_lake.security_master import register as _register_security

    try:
        spy_bars = read_bars_asof(
            con, security_ids=[_SPY_SECURITY_ID], as_of=as_of, start_date=start, end_date=end
        )
    except Exception:
        spy_bars = None

    if spy_bars is None or spy_bars.is_empty():
        _register_security(
            con,
            symbol="SPY",
            security_id=_SPY_SECURITY_ID,
            effective_start=start,
            name="SPDR S&P 500 ETF Trust",
            exchange="ARCX",
        )
        warn("SPY has no bars yet. Run `just ingest --security-id SPY` first.")
        spy_bars = None

    df = compute_all_indicators(bars, as_of, benchmark_bars=spy_bars)
    if df.is_empty():
        return 0

    n = len(security_ids)
    for i, sid in enumerate(security_ids):
        if on_step:
            on_step(i, n, sid)

    total = write_dataset(con, "technical_indicators", df)

    if on_step:
        on_step(n, n, f"done — {total} indicator rows")

    return total
