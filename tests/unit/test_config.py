from alpha_lake.config import LakeConfig, RootConfig, load_config, SourceConfig


def test_load_config_embedded():
    cfg = load_config("config/embedded.toml")
    assert cfg.lake.runtime == "embedded"
    assert cfg.lake.catalog.startswith("ducklake:")


def test_config_defaults():
    cfg = RootConfig(lake=LakeConfig())
    assert cfg.s3.endpoint == "rustfs:9000"
    assert cfg.lake.runtime == "stack"


def test_source_config_defaults():
    cfg = SourceConfig()
    assert cfg.api_key == ""
    assert cfg.rate_limit_per_sec == 10.0
