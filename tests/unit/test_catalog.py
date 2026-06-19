from alpha_lake.catalog import _build_connect_path
from alpha_lake.config import RootConfig, LakeConfig


def test_build_connect_path_postgres():
    cfg = RootConfig(lake=LakeConfig(catalog="ducklake:postgres:host=localhost dbname=test user=u password=p"))
    result = _build_connect_path(cfg)
    assert result == "postgres://host=localhost dbname=test user=u password=p"


def test_build_connect_path_sqlite():
    cfg = RootConfig(lake=LakeConfig(catalog="ducklake:sqlite:data/test.db"))
    result = _build_connect_path(cfg)
    assert result == "data/test.db"


def test_build_connect_path_unknown():
    cfg = RootConfig(lake=LakeConfig(catalog="direct:memory"))
    result = _build_connect_path(cfg)
    assert result == "direct:memory"
