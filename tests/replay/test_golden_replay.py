from pathlib import Path

import polars as pl

from alpha_lake.replay import check_replay, freeze_output, load_golden_hash


def test_freeze_and_check(tmp_path: Path):
    df = pl.DataFrame({"x": [1, 2, 3], "y": ["a", "b", "c"]})
    freeze_output(df, tmp_path)
    assert load_golden_hash(tmp_path)
    assert check_replay(tmp_path, df) is True


def test_replay_fails_on_mismatch(tmp_path: Path):
    df = pl.DataFrame({"x": [1, 2, 3], "y": ["a", "b", "c"]})
    freeze_output(df, tmp_path)
    df2 = pl.DataFrame({"x": [1, 2, 4], "y": ["a", "b", "c"]})
    assert check_replay(tmp_path, df2) is False
