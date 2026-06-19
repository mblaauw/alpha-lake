from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import polars as pl


def canonical_hash(data: list[dict[str, Any]]) -> str:
    canonical = json.dumps(data, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def freeze_output(df: pl.DataFrame, path: Path) -> str:
    rows = json.loads(df.write_json())
    h = canonical_hash(rows)
    (path / "output_hash.txt").write_text(h)
    df.write_parquet(str(path / "output.parquet"))
    return h


def load_golden_hash(path: Path) -> str:
    return (path / "output_hash.txt").read_text().strip()


def load_golden_output(path: Path) -> pl.DataFrame:
    return pl.read_parquet(str(path / "output.parquet"))


def check_replay(path: Path, actual: pl.DataFrame) -> bool:
    golden_hash = load_golden_hash(path)
    rows = json.loads(actual.write_json())
    actual_hash = canonical_hash(rows)
    return actual_hash == golden_hash
