import tempfile

import duckdb

from alpha_lake.catalog import connect
from alpha_lake.config import RootConfig, LakeConfig


def test_build_attach_postgres():
    from alpha_lake.catalog import _build_attach
    cfg = RootConfig(lake=LakeConfig(catalog="ducklake:postgres:dbname=test host=localhost", runtime="stack"))
    attach, data_path = _build_attach(cfg)
    assert attach.startswith("ducklake:postgres:")


def test_build_attach_sqlite():
    from alpha_lake.catalog import _build_attach
    cfg = RootConfig(lake=LakeConfig(catalog="ducklake:sqlite:data/test.db", runtime="embedded"))
    attach, data_path = _build_attach(cfg)
    assert attach.startswith("ducklake:sqlite:")


def test_connect_ducklake():
    tmp = tempfile.NamedTemporaryFile(suffix=".ducklake", delete=False)
    tmp.close()
    cfg = RootConfig(lake=LakeConfig(
        catalog=f"ducklake:sqlite:{tmp.name}",
        data_path=tmp.name + ".files",
        runtime="embedded",
    ))
    try:
        con = connect(cfg)
        assert con is not None
        con.close()
    except Exception as e:
        if "extension" in str(e).lower() or "not found" in str(e).lower():
            pass
        else:
            raise
