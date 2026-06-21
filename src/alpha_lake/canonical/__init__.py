from __future__ import annotations

import dataclasses
import hashlib
import json

import duckdb
import patito as pt
import polars as pl

from alpha_lake.interop import generate_ddl, polars_to_duckdb
from alpha_lake.models.analyst_estimate_fact import AnalystEstimateFact
from alpha_lake.models.bar_fact import BarFact
from alpha_lake.models.congress_trade_fact import CongressTradeFact
from alpha_lake.models.corp_action_fact import CorpActionFact
from alpha_lake.models.dataset_models import (
    EarningsEventFact,
    EntityMentionFact,
    FundamentalFact,
    InsiderTxFact,
    NewsArticleFact,
    SentimentAnnotationFact,
    SocialAttentionFact,
    SocialPostFact,
)
from alpha_lake.models.economic_calendar_fact import EconomicCalendarFact
from alpha_lake.models.macro_fact import MacroSeriesFact
from alpha_lake.models.market_breadth_fact import MarketBreadthFact
from alpha_lake.models.relative_strength_fact import RelativeStrengthFact
from alpha_lake.models.technical_fact import TechnicalIndicatorFact
from alpha_lake.models.vol_term_structure_fact import VolTermStructureFact

NORMALIZATION_VERSION: int = 1


@dataclasses.dataclass(frozen=True)
class Dataset:
    table: str
    model: type[pt.Model]
    natural_keys: tuple[str, ...]


_ANALYST_KEYS = ("security_id", "effective_date", "source_id")
_BARS_KEYS = ("security_id", "effective_date", "source_id")
_CONGRESS_KEYS = ("transaction_id",)
_CORP_KEYS = ("security_id", "action_type", "effective_date", "source_id")
_FUND_KEYS = ("security_id", "fiscal_period", "statement_type", "line_item", "source_id")
_INSIDER_KEYS = (
    "security_id",
    "filer_cik",
    "issuer_cik",
    "transaction_code",
    "effective_date",
    "source_id",
)
_EARN_KEYS = ("security_id", "report_date", "source_id")
_SOCIAL_KEYS = ("security_id", "effective_date", "cohort", "source_id")
_SENT_KEYS = ("annotation_id",)
_MACRO_KEYS = ("series_id", "effective_date", "source_id")
_ECON_CAL_KEYS = ("event_id", "effective_date", "source_id")
_TECH_KEYS = ("security_id", "effective_date", "source_id")
_RS_KEYS = ("security_id", "effective_date", "window")
_VOL_TERM_KEYS = ("series_id", "effective_date", "source_id")
_BREADTH_KEYS = ("metric_id", "effective_date")

DATASETS: dict[str, Dataset] = {
    "analyst_estimates": Dataset("analyst_estimates", AnalystEstimateFact, _ANALYST_KEYS),
    "congress_trades": Dataset("congress_trades", CongressTradeFact, _CONGRESS_KEYS),
    "lake_bars": Dataset("lake_bars", BarFact, _BARS_KEYS),
    "corp_actions": Dataset("corp_actions", CorpActionFact, _CORP_KEYS),
    "fundamentals": Dataset("fundamentals", FundamentalFact, _FUND_KEYS),
    "insider_tx": Dataset("insider_tx", InsiderTxFact, _INSIDER_KEYS),
    "news_articles": Dataset("news_articles", NewsArticleFact, ("article_id", "source_id")),
    "social_posts": Dataset("social_posts", SocialPostFact, ("post_id_hash", "source_id")),
    "earnings_calendar": Dataset("earnings_calendar", EarningsEventFact, _EARN_KEYS),
    "entity_mentions": Dataset("entity_mentions", EntityMentionFact, ("mention_id",)),
    "sentiment_annotations": Dataset("sentiment_annotations", SentimentAnnotationFact, _SENT_KEYS),
    "attention_metrics": Dataset("attention_metrics", SocialAttentionFact, _SOCIAL_KEYS),
    "macro_series": Dataset("macro_series", MacroSeriesFact, _MACRO_KEYS),
    "economic_calendar": Dataset("economic_calendar", EconomicCalendarFact, _ECON_CAL_KEYS),
    "technical_indicators": Dataset("technical_indicators", TechnicalIndicatorFact, _TECH_KEYS),
    "relative_strength": Dataset("relative_strength", RelativeStrengthFact, _RS_KEYS),
    "market_breadth": Dataset("market_breadth", MarketBreadthFact, _BREADTH_KEYS),
    "vol_term_structure": Dataset("vol_term_structure", VolTermStructureFact, _VOL_TERM_KEYS),
}


def compute_version_hash(df: pl.DataFrame) -> pl.DataFrame:
    float_cols = [
        c for c in df.columns if c != "version_hash" and df[c].dtype in (pl.Float32, pl.Float64)
    ]
    hash_input = df.with_columns(pl.col(float_cols).round(10))
    hash_input = hash_input.select([c for c in hash_input.columns if c != "version_hash"])
    hash_expr = pl.struct(hash_input.columns).map_elements(
        lambda row: hashlib.sha256(
            json.dumps(row, sort_keys=True, default=str, separators=(",", ":")).encode()
        ).hexdigest(),
        return_dtype=pl.String,
    )
    return df.with_columns(
        hash_expr.alias("version_hash"),
        pl.lit(NORMALIZATION_VERSION).alias("normalization_version"),
    )


def ensure_schema(con: duckdb.DuckDBPyConnection, dataset: Dataset) -> None:
    con.execute(generate_ddl(dataset.model, dataset.table))


def write(con: duckdb.DuckDBPyConnection, dataset: Dataset, df: pl.DataFrame) -> int:
    df = compute_version_hash(df)
    ensure_schema(con, dataset)
    dedup_keys = list(dataset.natural_keys) + ["available_at", "version_hash"]
    return _merge_into(con, dataset.table, dedup_keys, df)


def write_bars(con: duckdb.DuckDBPyConnection, df: pl.DataFrame) -> int:
    return write(con, DATASETS["lake_bars"], df)


def write_corp_actions(con: duckdb.DuckDBPyConnection, df: pl.DataFrame) -> int:
    return write(con, DATASETS["corp_actions"], df)


def write_dataset(con: duckdb.DuckDBPyConnection, table: str, df: pl.DataFrame) -> int:
    return write(con, DATASETS[table], df)


def _merge_into(
    con: duckdb.DuckDBPyConnection,
    table: str,
    dedup_keys: list[str],
    df: pl.DataFrame,
) -> int:
    cols = ", ".join(df.columns)

    con.execute("DROP TABLE IF EXISTS _staging")
    polars_to_duckdb(con, df, "_staging")

    ddl = generate_ddl(DATASETS[table].model, table)
    con.execute(ddl)

    join_on = " AND ".join(f"target.{k} = source.{k}" for k in dedup_keys)
    con.execute(f"""
        MERGE INTO {table} target
        USING (SELECT {cols} FROM _staging) source
        ON ({join_on})
        WHEN NOT MATCHED THEN INSERT ({cols}) VALUES ({cols})
    """)

    count = con.execute("SELECT COUNT(*) FROM _staging").fetchone()
    con.execute("DROP TABLE IF EXISTS _staging")
    return count[0] if count else 0
