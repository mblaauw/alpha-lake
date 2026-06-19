from datetime import date, datetime, timezone

import duckdb
import polars as pl

from alpha_lake.canonical import write_corp_actions
from alpha_lake.models.corp_action_fact import CorpActionFact
from alpha_lake.normalize.corp_actions import dividends_from_json, parse_ratio, splits_from_json


def test_parse_ratio():
    assert parse_ratio("2:1") == (2.0, 1.0)
    assert parse_ratio("1/5") == (1.0, 5.0)
    assert parse_ratio("") == (1.0, 1.0)


def test_splits_from_json():
    raw = [{"date": "2025-06-01", "splitRatio": "2:1"}]
    ts = datetime(2025, 6, 2, 8, 0, tzinfo=timezone.utc)
    df = splits_from_json(raw, "sec_test", "eodhd_splits", "f1", "r1", "c1", ts)
    assert df.height == 1
    validated = CorpActionFact.validate(df)
    assert validated["action_type"][0] == "split"
    assert validated["ratio_numerator"][0] == 2.0


def test_dividends_from_json():
    raw = [{"date": "2025-06-01", "dividend": 0.25, "currency": "USD"}]
    ts = datetime(2025, 6, 2, 8, 0, tzinfo=timezone.utc)
    df = dividends_from_json(raw, "sec_test", "eodhd_dividends", "f1", "r1", "c1", ts)
    assert df.height == 1
    validated = CorpActionFact.validate(df)
    assert validated["action_type"][0] == "dividend"
    assert validated["dividend_amount"][0] == 0.25


def test_write_corp_actions():
    con = duckdb.connect()
    ts = datetime(2025, 6, 2, 8, 0, tzinfo=timezone.utc)
    raw = [{"date": "2025-06-01", "splitRatio": "2:1"}]
    df = splits_from_json(raw, "sec_test", "eodhd_splits", "f1", "r1", "c1", ts)
    count = write_corp_actions(con, df)
    assert count == 1
    result = con.execute("SELECT action_type, ratio_numerator FROM corp_actions").fetchone()
    assert result[0] == "split"
    assert result[1] == 2.0
    con.close()
