"""Smoke tests — verify core modules import without error."""


def test_cli_imports():
    from alpha_lake.cli import app
    assert app.info.name == "alpha-lake"


def test_config_imports():
    from alpha_lake.config import RootConfig, load_config
    assert RootConfig is not None
    assert load_config is not None


def test_obs_imports():
    from alpha_lake.obs import tracer, setup_otel
    assert tracer is not None
    assert setup_otel is not None
