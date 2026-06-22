def pytest_addoption(parser):
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="run live API integration tests (skipped by default)",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-live"):
        return
    skip_live = pytest.mark.skip(reason="use --run-live to run live API tests")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


import pytest  # noqa: E402 (needed for the skip marker above)
