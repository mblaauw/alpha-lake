from alpha_lake.config import (
    DatasetPostureConfig,
    LakeConfig,
    RootConfig,
    SourceConfig,
    load_config,
)


def test_load_config_embedded():
    cfg = load_config("config/embedded.toml")
    assert cfg.lake.runtime == "embedded"
    assert cfg.lake.catalog.startswith("ducklake:")


def test_config_defaults():
    cfg = RootConfig(lake=LakeConfig())
    assert cfg.s3.endpoint == "rustfs:9000"
    assert cfg.lake.runtime == "stack"
    assert cfg.datasets == {}


def test_source_config_defaults():
    cfg = SourceConfig()
    assert cfg.api_key == ""
    assert cfg.rate_limit_per_sec == 10.0


def test_dataset_posture_defaults():
    cfg = DatasetPostureConfig()
    assert cfg.tier == "core"
    assert cfg.supported is True
    assert cfg.sla is False


def test_stack_dataset_tiers():
    cfg = load_config("config/stack.toml")
    assert cfg.datasets["lake_bars"].tier == "core"
    assert cfg.datasets["technical_indicators"].tier == "convenience"
    assert cfg.datasets["news_articles"].tier == "experimental"
    assert cfg.datasets["news_articles"].supported is False
    assert cfg.datasets["social_posts"].supported is False
    assert cfg.reconcile["fundamentals"].cross_source_enabled is True
    assert cfg.reconcile["fundamentals"].numeric_diff_pct == 1.0
    assert cfg.reconcile["corp_actions"].cross_source_enabled is True
    assert cfg.reconcile["corp_actions"].strict_event_match is True
