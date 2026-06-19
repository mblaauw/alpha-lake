import hashlib
import json
from datetime import datetime

import polars as pl
import pytest

from alpha_lake.canonical import write_bars
from alpha_lake.harness import EmbeddedHarness
from alpha_lake.replay import canonical_hash
from alpha_lake.serving import read_bars_asof
from tests.fixtures import sample_bars_df, sample_bars_restated


def _visibility_hash(df: pl.DataFrame) -> str:
    vis = df.select(["security_id", "effective_date", "available_at", "version_hash", "source_id"])
    rows = json.loads(vis.write_json())
    raw = json.dumps(rows, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


@pytest.fixture
def harness():
    h = EmbeddedHarness()
    h.start()
    yield h
    h.stop()


def test_hash_deterministic(harness: EmbeddedHarness):
    h1 = _run_and_hash(harness)
    h2 = _run_and_hash(harness)
    assert h1 == h2, "re-running with same inputs must produce identical hash"


def test_hash_changes_on_restatement(harness: EmbeddedHarness):
    h_original = _run_and_hash(harness)

    bars = sample_bars_restated()
    write_bars(harness.conn, bars)

    result = read_bars_asof(harness.conn, ["sec_aap"], datetime(2026, 1, 7, 12, 0, 0))
    rows = json.loads(result.write_json())
    h_restated = canonical_hash(rows)
    assert h_restated != h_original, "restated data must produce different hash"


def test_hash_covers_visibility(harness: EmbeddedHarness):
    bars = sample_bars_df()
    write_bars(harness.conn, bars)

    read_t1 = read_bars_asof(harness.conn, ["sec_aap"], datetime(2026, 1, 5, 17, 0, 0))
    bars2 = sample_bars_restated()
    write_bars(harness.conn, bars2)

    read_t2 = read_bars_asof(harness.conn, ["sec_aap"], datetime(2026, 1, 7, 12, 0, 0))
    nvh1 = _visibility_hash(read_t1)
    nvh2 = _visibility_hash(read_t2)
    assert nvh1 != nvh2, "different as_of must produce different visibility hash"


def _run_and_hash(harness: EmbeddedHarness) -> str:
    bars = sample_bars_df()
    write_bars(harness.conn, bars)
    result = read_bars_asof(harness.conn, ["sec_aap"], datetime(2026, 1, 5, 17, 0, 0))
    rows = json.loads(result.write_json())
    return canonical_hash(rows)
