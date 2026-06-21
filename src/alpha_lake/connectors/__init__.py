from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from alpha_lake.connectors.alpaca_bars import fetch_daily_bars as _alpaca_bars
from alpha_lake.connectors.corp_actions_eodhd import fetch_splits as _eodhd_splits
from alpha_lake.connectors.corp_actions_tiingo import fetch_splits as _tiingo_splits
from alpha_lake.connectors.eodhd import fetch_bars_daily as _eodhd_bars
from alpha_lake.connectors.eodhd_earnings import fetch_earnings_calendar as _eodhd_earnings
from alpha_lake.connectors.eodhd_fundamentals import fetch_fundamentals as _eodhd_fundamentals
from alpha_lake.connectors.eodhd_news import fetch_news as _eodhd_news
from alpha_lake.connectors.fmp import fetch_economic_calendar as _fmp_econ
from alpha_lake.connectors.fred import fetch_macro_series as _fred_macro
from alpha_lake.connectors.reddit import fetch_subreddit as _reddit
from alpha_lake.connectors.sec_edgar import fetch_companyfacts as _sec_edgar
from alpha_lake.connectors.sec_insider import fetch_insider_transactions as _sec_insider
from alpha_lake.connectors.tiingo import fetch_bars_daily as _tiingo_bars
from alpha_lake.connectors.tiingo_fundamentals import fetch_fundamentals as _tiingo_fundamentals
from alpha_lake.connectors.tiingo_news import fetch_news as _tiingo_news

if TYPE_CHECKING:
    from alpha_lake.connectors.base import RawFetch

ConnectorFn = Callable[..., Awaitable["RawFetch"]]

_REGISTRY: dict[tuple[str, str], ConnectorFn] = {}


def register(source_id: str, dataset: str, fn: ConnectorFn) -> None:
    _REGISTRY[(source_id, dataset)] = fn


def get_connector(source_id: str, dataset: str) -> ConnectorFn | None:
    return _REGISTRY.get((source_id, dataset))


def has_api_key(source_id: str) -> bool:
    from alpha_lake.source_registry import get_source

    try:
        cfg = get_source(source_id)
        return bool(cfg.api_key)
    except KeyError:
        return False


register("alpaca", "bars_daily", _alpaca_bars)
register("eodhd", "bars_daily", _eodhd_bars)
register("eodhd", "earnings_calendar", _eodhd_earnings)
register("eodhd", "fundamentals", _eodhd_fundamentals)
register("eodhd", "news", _eodhd_news)
register("eodhd", "corp_actions", _eodhd_splits)
register("fmp", "economic_calendar", _fmp_econ)
register("fred", "macro_series", _fred_macro)
register("reddit", "social_posts", _reddit)
register("sec", "fundamentals", _sec_edgar)
register("sec", "insider_tx", _sec_insider)
register("tiingo", "bars_daily", _tiingo_bars)
register("tiingo", "fundamentals", _tiingo_fundamentals)
register("tiingo", "news", _tiingo_news)
register("tiingo", "corp_actions", _tiingo_splits)
