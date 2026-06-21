from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
import pytest

import alpha_lake.config as _alpha_lake_config
from alpha_lake.canonical import write_bars
from alpha_lake.catalog import bootstrap as _bootstrap_catalog
from alpha_lake.catalog import connect
from alpha_lake.config import LakeConfig, RootConfig, S3Config
from alpha_lake.raw import archive, read_raw
from alpha_lake.serving import read_bars_asof

_PGHOST = os.environ.get("AL_CI_PGHOST", "postgres")
_RUSTFS_HOST = os.environ.get("AL_CI_RUSTFS_HOST", "rustfs")

pytestmark = pytest.mark.skipif(
    not shutil.which("docker"),
    reason="Docker required for stack mode test",
)


def _stack_available() -> bool:
    """Check if Docker compose stack is running."""
    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "--services", "--filter", "status=running"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        services = result.stdout.strip().split("\n")
        return "postgres" in services and "rustfs" in services
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False


@pytest.mark.skipif(not _stack_available(), reason="Docker stack (postgres+rustfs) not running")
def test_mode_parity_storage():
    """Verify embedded and stack modes produce identical data and raw lands in the right store."""
    # --- Test data ---
    ts = datetime(2026, 6, 18, 16, 0, tzinfo=UTC)
    df = pl.DataFrame(
        {
            "security_id": ["sec_parity"],
            "effective_date": [date(2026, 6, 18)],
            "available_at": [ts],
            "source_id": ["eodhd"],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [10000],
            "source_fetch_id": [""],
            "raw_payload_hash": [""],
            "ingestion_run_id": [""],
            "content_hash": [""],
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
    raw_data = b'{"test":"parity payload"}'

    # Set global config for archive()/read_raw() which use get_config()
    _alpha_lake_config._config = RootConfig(
        lake=LakeConfig(
            runtime="stack",
            catalog=(
                f"ducklake:postgres:dbname=lake_catalog "
                f"host={_PGHOST} port=5432 user=lake password=lake"
            ),
            canonical_data_path="s3://lake/",
            raw_archive_uri="s3://lake/raw/",
            calendar_version="4.13.2",
        ),
        s3=S3Config(
            endpoint=f"{_RUSTFS_HOST}:9000",
            url_style="path",
            use_ssl=False,
        ),
    )

    # --- 1. Embedded mode ---
    with tempfile.TemporaryDirectory() as tmpdir:
        embedded_cfg = RootConfig(
            lake=LakeConfig(
                runtime="embedded",
                catalog=f"ducklake:sqlite:{tmpdir}/lake.catalog",
                canonical_data_path=f"{tmpdir}/lake/",
                raw_archive_uri=f"{tmpdir}/lake/",
                calendar_version="4.13.2",
            )
        )
        embedded_hash = archive(raw_data)
        embedded_raw = read_raw(embedded_hash)

        con_emb = connect(embedded_cfg)
        n = write_bars(con_emb, df)
        assert n == 1
        embedded_bars = read_bars_asof(
            con_emb,
            ["sec_parity"],
            datetime(2026, 6, 18, 17, 0, tzinfo=UTC),
        )
        con_emb.close()

    # --- 2. Stack mode ---
    with tempfile.TemporaryDirectory() as tmpdir:
        stack_cfg = RootConfig(
            lake=LakeConfig(
                runtime="stack",
                catalog=(
                    f"ducklake:postgres:dbname=lake_catalog "
                    f"host={_PGHOST} port=5432 user=lake password=lake"
                ),
                canonical_data_path="s3://lake/",
                raw_archive_uri="s3://lake/raw/",
                calendar_version="4.13.2",
            ),
            s3=S3Config(
                endpoint=f"{_RUSTFS_HOST}:9000",
                url_style="path",
                use_ssl=False,
            ),
        )

        _bootstrap_catalog(stack_cfg)

        stack_hash = archive(raw_data)
        assert stack_hash == embedded_hash, "content_hash must match across modes"

        stack_raw = read_raw(stack_hash)

        con_stk = connect(stack_cfg)
        n = write_bars(con_stk, df)
        assert n == 1
        stack_bars = read_bars_asof(
            con_stk,
            ["sec_parity"],
            datetime(2026, 6, 18, 17, 0, tzinfo=UTC),
        )
        con_stk.close()

        # Verify raw blob is NOT on local disk (would indicate split-brain)
        assert not Path(tmpdir).glob("**/*.zst"), "stack mode: raw blob should NOT be on local disk"

    # --- 3. Compare ---
    assert embedded_raw == stack_raw, "raw payloads must be identical"
    assert embedded_bars["close"][0] == stack_bars["close"][0], "canonical close must match"
    assert embedded_bars["version_hash"][0] == stack_bars["version_hash"][0], (
        "version_hash must be deterministic across modes"
    )
