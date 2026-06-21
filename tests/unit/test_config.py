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
    assert cfg.fallback_base_url is None
    assert cfg.requires_key is True
    assert cfg.contact_email == ""
    assert cfg.rate_limit_per_min is None
    assert cfg.rate_limit_per_day is None


def test_source_config_with_limits():
    cfg = SourceConfig(
        rate_limit_per_sec=5.0,
        rate_limit_per_min=100,
        rate_limit_per_day=1000,
        fallback_base_url="https://fallback.example.com",
        requires_key=False,
        contact_email="test@example.com",
    )
    assert cfg.rate_limit_per_min == 100
    assert cfg.rate_limit_per_day == 1000
    assert cfg.fallback_base_url == "https://fallback.example.com"
    assert cfg.requires_key is False
    assert cfg.contact_email == "test@example.com"


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
