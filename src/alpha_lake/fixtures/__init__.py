from __future__ import annotations

from datetime import UTC
from pathlib import Path

import polars as pl

from alpha_lake.canonical import write_bars
from alpha_lake.cli_ui import info
from alpha_lake.harness import EmbeddedHarness
from alpha_lake.replay import freeze_output
from alpha_lake.serving import read_bars_asof

_FIXTURE_DIR = Path(__file__).parents[3] / "tests" / "replay" / "fixtures"
_INDICATOR_DIR = _FIXTURE_DIR / "indicators"
_READOUT_DIR = _FIXTURE_DIR / "readouts"
_FUNDAMENTAL_DIR = _FIXTURE_DIR / "fundamentals"
_PROFILES_PATH = Path(__file__).parents[3] / "config" / "threshold_profiles.toml"
_PROJECT_ROOT = Path(__file__).parents[3]


def _sample_bars() -> pl.DataFrame:
    from datetime import date, datetime

    return pl.DataFrame(
        {
            "security_id": ["sec_aap"],
            "effective_date": [date(2026, 1, 5)],
            "available_at": [datetime(2026, 1, 5, 16, 0, 0)],
            "source_id": ["eodhd"],
            "open": [200.0],
            "high": [205.0],
            "low": [199.0],
            "close": [203.5],
            "volume": [5000000],
            "source_fetch_id": ["f1"],
            "raw_payload_hash": ["h1"],
            "ingestion_run_id": ["r1"],
            "content_hash": ["c1"],
            "version_hash": [""],
            "schema_version": [1],
            "parser_version": [1],
            "quality_status": ["valid"],
            "source_published_at": [None],
            "ingested_at": [None],
            "validated_at": [None],
        }
    ).with_columns(
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )


def _generate_indicator_bars() -> pl.DataFrame:
    from datetime import date, datetime, timedelta

    rows: list[dict] = []
    n_bars = 260
    start = date(2026, 1, 5)

    for sid, base, step in [("sec_aap", 200.0, 0.15), ("sec_msft", 150.0, 0.10)]:
        for i in range(n_bars):
            d = start - timedelta(days=n_bars - 1 - i)
            close_v = base + step * i
            open_v = close_v - 0.3
            high_v = close_v + 0.8
            low_v = close_v - 0.8
            vol = int(5_000_000 + i * 2000)
            rows.append(
                {
                    "security_id": sid,
                    "effective_date": d,
                    "available_at": datetime(2026, 1, 5, 16, 0, 0),
                    "source_id": "eodhd",
                    "open": open_v,
                    "high": high_v,
                    "low": low_v,
                    "close": close_v,
                    "volume": vol,
                    "source_fetch_id": "f1",
                    "raw_payload_hash": "h1",
                    "ingestion_run_id": "r1",
                    "content_hash": "c1",
                    "version_hash": "",
                    "schema_version": 1,
                    "parser_version": 1,
                    "quality_status": "valid",
                    "source_published_at": None,
                    "ingested_at": None,
                    "validated_at": None,
                }
            )

    df = pl.DataFrame(rows).with_columns(
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )
    return df.sort(["security_id", "effective_date"])


def _generate_spy_bars() -> pl.DataFrame:
    from datetime import date, datetime, timedelta

    rows: list[dict] = []
    n_bars = 260
    start = date(2026, 1, 5)

    for i in range(n_bars):
        d = start - timedelta(days=n_bars - 1 - i)
        close_v = 450.0 + 0.1 * i
        open_v = close_v - 0.2
        high_v = close_v + 0.5
        low_v = close_v - 0.5
        vol = int(50_000_000 + i * 10000)
        rows.append(
            {
                "security_id": "SPY",
                "effective_date": d,
                "available_at": datetime(2026, 1, 5, 16, 0, 0),
                "source_id": "eodhd",
                "open": open_v,
                "high": high_v,
                "low": low_v,
                "close": close_v,
                "volume": vol,
                "source_fetch_id": "f1",
                "raw_payload_hash": "h1",
                "ingestion_run_id": "r1",
                "content_hash": "c1",
                "version_hash": "",
                "schema_version": 1,
                "parser_version": 1,
                "quality_status": "valid",
                "source_published_at": None,
                "ingested_at": None,
                "validated_at": None,
            }
        )

    df = pl.DataFrame(rows).with_columns(
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )
    return df.sort("effective_date")


def _generate_fundamental_facts() -> pl.DataFrame:
    from datetime import date, datetime

    sids = ["sec_aap", "sec_msft"]
    rows: list[dict] = []

    for sid in sids:
        for q in range(8):
            year = 2024 + q // 4
            q_num = q % 4 + 1
            period_end = date(year, q_num * 3, (q_num * 3) % 30 or 30)
            fp = f"{year}Q{q_num}"
            filing_month = q_num * 3 + 1
            fm_year = year if filing_month <= 12 else year + 1
            fm_month = filing_month if filing_month <= 12 else filing_month - 12
            filing_dt = datetime(fm_year, fm_month, 15, 12, 0, 0)

            values: dict[str, float] = {
                "revenue": 10000.0 + q * 500.0 + (500.0 if sid == "sec_aap" else 0.0),
                "gross_profit": 6000.0 + q * 300.0,
                "operating_income": 3000.0 + q * 200.0,
                "net_income": 2000.0 + q * 150.0,
                "diluted_eps": 2.0 + q * 0.1,
                "ebitda": 3500.0 + q * 200.0,
                "operating_cash_flow": 2500.0 + q * 150.0,
                "capital_expenditure": -500.0 - q * 50.0,
            }

            for item, val in values.items():
                rows.append(
                    {
                        "security_id": sid,
                        "effective_date": period_end,
                        "available_at": filing_dt,
                        "source_id": "sec",
                        "source_published_at": filing_dt,
                        "ingested_at": filing_dt,
                        "validated_at": filing_dt,
                        "fiscal_period": fp,
                        "period_kind": "quarter",
                        "period_end": period_end,
                        "measurement_kind": "flow",
                        "statement_type": "income_statement",
                        "line_item": item,
                        "value": val,
                        "currency": "USD",
                        "source_currency": "USD",
                        "unit": "raw",
                        "source_priority": 1,
                        "source_fetch_id": "f1",
                        "raw_payload_hash": "h1",
                        "ingestion_run_id": "r1",
                        "content_hash": "c1",
                        "version_hash": f"{item}_{fp}",
                        "schema_version": 1,
                        "parser_version": 1,
                        "quality_status": "valid",
                    }
                )

            bs_items: dict[str, float] = {
                "cash_and_equivalents": 5000.0 + q * 200.0,
                "current_assets": 15000.0 + q * 500.0,
                "current_liabilities": 8000.0 + q * 200.0,
                "total_equity": 25000.0 + q * 1000.0,
                "short_term_debt": 1000.0 + q * 50.0,
                "long_term_debt": 8000.0 + q * 200.0,
                "total_debt": 9000.0 + q * 250.0,
            }

            for item, val in bs_items.items():
                rows.append(
                    {
                        "security_id": sid,
                        "effective_date": period_end,
                        "available_at": filing_dt,
                        "source_id": "sec",
                        "source_published_at": filing_dt,
                        "ingested_at": filing_dt,
                        "validated_at": filing_dt,
                        "fiscal_period": fp,
                        "period_kind": "quarter",
                        "period_end": period_end,
                        "measurement_kind": "instant",
                        "statement_type": "balance_sheet",
                        "line_item": item,
                        "value": val,
                        "currency": "USD",
                        "source_currency": "USD",
                        "unit": "raw",
                        "source_priority": 1,
                        "source_fetch_id": "f1",
                        "raw_payload_hash": "h1",
                        "ingestion_run_id": "r1",
                        "content_hash": "c1",
                        "version_hash": f"{item}_{fp}",
                        "schema_version": 1,
                        "parser_version": 1,
                        "quality_status": "valid",
                    }
                )

    df = pl.DataFrame(rows)
    for col in ("effective_date", "period_end"):
        df = df.with_columns(pl.col(col).cast(pl.Date))
    for col in ("available_at", "source_published_at", "ingested_at", "validated_at"):
        df = df.with_columns(pl.col(col).cast(pl.Datetime(time_zone="UTC")))
    return df


def _generate_analyst_estimates() -> pl.DataFrame:
    from datetime import date, datetime

    sids = ["sec_aap", "sec_msft"]
    rows: list[dict] = []
    for sid in sids:
        rows.append(
            {
                "security_id": sid,
                "effective_date": date(2026, 1, 5),
                "available_at": datetime(2026, 1, 5, 16, 0, 0),
                "source_id": "fmp",
                "target_mean": 250.0 if sid == "sec_aap" else 180.0,
                "target_high": 300.0 if sid == "sec_aap" else 220.0,
                "target_low": 200.0 if sid == "sec_aap" else 140.0,
                "strong_buy": 5,
                "buy": 3,
                "hold": 2,
                "sell": 0,
                "strong_sell": 0,
                "source_fetch_id": "f1",
                "raw_payload_hash": "h1",
                "ingestion_run_id": "r1",
                "content_hash": "c1",
                "version_hash": "v1",
                "schema_version": 1,
                "parser_version": 1,
                "quality_status": "valid",
            }
        )
    return pl.DataFrame(rows).with_columns(
        pl.col("effective_date").cast(pl.Date),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def _generate_earnings_calendar() -> pl.DataFrame:
    from datetime import date, datetime

    sids = ["sec_aap", "sec_msft"]
    rows: list[dict] = []
    for sid in sids:
        rows.append(
            {
                "security_id": sid,
                "effective_date": date(2026, 1, 5),
                "available_at": datetime(2026, 1, 5, 16, 0, 0),
                "source_id": "eodhd",
                "report_date": date(2026, 2, 1) if sid == "sec_aap" else date(2026, 1, 28),
                "session": "afternoon",
                "source_fetch_id": "f1",
                "raw_payload_hash": "h1",
                "ingestion_run_id": "r1",
                "content_hash": "c1",
                "version_hash": "v1",
                "schema_version": 1,
                "parser_version": 1,
                "quality_status": "valid",
            }
        )
    return pl.DataFrame(rows).with_columns(
        pl.col("effective_date").cast(pl.Date),
        pl.col("report_date").cast(pl.Date),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def freeze_bars() -> None:
    from datetime import datetime

    _FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    harness = EmbeddedHarness()
    harness.start()

    bars = _sample_bars()
    write_bars(harness.conn, bars)

    pit_result = read_bars_asof(
        harness.conn,
        ["sec_aap"],
        datetime(2026, 1, 5, 17, 0, 0),
    )

    freeze_output(pit_result, _FIXTURE_DIR)
    harness.stop()
    info(f"Froze {len(bars)} bars -> {_FIXTURE_DIR}")


def freeze_indicators() -> None:
    from datetime import datetime

    _INDICATOR_DIR.mkdir(parents=True, exist_ok=True)
    harness = EmbeddedHarness()
    harness.start()

    bars = _generate_indicator_bars()
    write_bars(harness.conn, bars)

    as_of = datetime(2026, 1, 5, 17, 0, 0, tzinfo=UTC)
    bars_df = read_bars_asof(
        harness.conn,
        ["sec_aap", "sec_msft"],
        as_of,
    )

    from alpha_lake.derived.compute import compute_all_indicators

    result = compute_all_indicators(bars_df, as_of)
    if "version_hash" in result.columns:
        result = result.sort(["security_id", "effective_date"])
    freeze_output(result, _INDICATOR_DIR)
    harness.stop()
    info(f"Froze {len(result)} indicator rows -> {_INDICATOR_DIR}")


def freeze_readouts() -> None:
    from datetime import datetime

    _READOUT_DIR.mkdir(parents=True, exist_ok=True)
    harness = EmbeddedHarness()
    harness.start()

    bars = _generate_indicator_bars()
    write_bars(harness.conn, bars)
    spy = _generate_spy_bars()
    write_bars(harness.conn, spy)

    as_of = datetime(2026, 1, 5, 17, 0, 0, tzinfo=UTC)
    bars_df = read_bars_asof(
        harness.conn,
        ["sec_aap", "sec_msft"],
        as_of,
    )
    spy_df = read_bars_asof(harness.conn, ["SPY"], as_of)

    from alpha_lake.interpretation.profiles import load_threshold_profiles
    from alpha_lake.interpretation.readouts import compute_all_readouts

    profiles = load_threshold_profiles(_PROFILES_PATH)
    observations = compute_all_readouts(bars_df, None, spy_df, as_of, profiles)

    obs_dicts = [o.to_dict() for o in observations]
    df = pl.DataFrame(obs_dicts)
    freeze_output(df, _READOUT_DIR)
    harness.stop()
    info(f"Froze {len(observations)} readout observations -> {_READOUT_DIR}")


def freeze_fundamentals() -> None:
    from datetime import datetime

    _FUNDAMENTAL_DIR.mkdir(parents=True, exist_ok=True)
    harness = EmbeddedHarness()
    harness.start()

    from alpha_lake.derived.fundamental_metrics import (
        compute_estimate_metrics,
        compute_fundamental_period_metrics,
    )

    as_of = datetime(2025, 12, 31, 23, 59, 0, tzinfo=UTC)

    facts = _generate_fundamental_facts()
    period_metrics = compute_fundamental_period_metrics(facts, as_of, ingestion_run_id="r1")

    estimates = _generate_analyst_estimates()
    earnings = _generate_earnings_calendar()
    est_metrics = compute_estimate_metrics(estimates, earnings, as_of, ingestion_run_id="r1")

    parts = [p for p in [period_metrics, est_metrics] if not p.is_empty()]
    result = pl.concat(parts) if parts else period_metrics

    freeze_output(result, _FUNDAMENTAL_DIR)
    harness.stop()
    info(f"Froze {len(result)} fundamental metric rows -> {_FUNDAMENTAL_DIR}")


def freeze() -> None:
    freeze_bars()
    freeze_indicators()
    freeze_readouts()
    freeze_fundamentals()
