# Alpha-Lake — Systems Design & Implementation Reference (v3.1 — stack-first)

A standalone, bitemporal, replayable **market-data lakehouse**. It ingests, archives, validates, and serves point-in-time-correct market facts to any consumer — notebooks, dashboards, backtests, ML, trading systems — and depends on none of them. It runs **stack-first** in its own self-contained Compose runtime: every dependency is pinned and vendored in-repo. A lightweight embedded mode exists only for fast tests, debugging, fixture generation, and golden replay — not as a separate product path.

> **Owns facts. Serves what was knowable as of a date. Knows nothing about strategy.**

**Current architectural decision:** Alpha-Lake is **stack-first**. The Compose stack is the v0.1 reference runtime. Embedded local execution is retained only for tests, debugging, fixture generation, and golden replay.

### How to read this document

Two registers, one source of truth:

- **Part I — Systems Design** (§0–6): the *what and why*. Architecture, principles, runtime model, the conceptual model. Read this to understand the system.
- **Part II — Implementation Reference** (§7–25): the *how*. Exact schemas, SQL, field specs, pipeline shapes, test specs. Read this to build it.
- **Part III — Governance** (§26–31): invariants, ADRs, build plan, stack, non-goals.

Section cross-references link the two registers (a concept in Part I points to its buildable spec in Part II).

---

# Part I — Systems Design

## 0. Scope

**In scope:** connectors; immutable raw archive; parse → neutral facts; validation + quarantine; security identity; **bitemporal** canonical datasets; corporate-action-aware adjusted *views*; versioning, lineage, time-travel; point-in-time serving; reconciliation; catalog; deterministic replay; data-health.

**Out of scope (v1):** strategy/decision logic; materialized strategy features (§14); intraday streaming; distributed compute; hosted multi-tenant service; ML online feature store; governance UI.

```
Alpha-Lake tells consumers what was knowable at a point in time.
Consumers decide what it means.
```

## 1. Principles

1. **Raw is immutable.** Archive every payload verbatim before parsing; fix bugs by replay, never rewrite. → §8
2. **Canonical is reproducible.** `canonical = f(raw, parser_version, schema_version, config, security_master)`. → §21
3. **Point-in-time correctness > convenience.** No consumer sees future data; every research read is knowledge-time bounded. → §11
4. **Tri-temporal, explicitly.** Valid / knowledge / system time are three clocks; conflating any two is a bug. → §4, §11
5. **Degrade, never corrupt.** Failure → explicit degraded state; bad data → quarantine with lineage. → §13
6. **Facts, not opinions.** Neutral transforms only; the lake never knows if a value is bullish or tradable. → §14
7. **Contracts are the API; layout is not.** Consumers bind to typed models and readers. → §18
8. **Self-contained & reproducible.** The reference runtime is a local Compose stack; all deps are pinned and vendorable. → §23
9. **Stack-first, not laptop-first.** The real catalog/object-store boundary is exercised from day one; embedded mode is only a test/replay harness. → §3, §28

## 2. Architecture

### 2.1 Context & containers

```mermaid
flowchart LR
  subgraph SRC[External sources]
    direction TB
    S1[Market data APIs]
    S2[Filings / insider]
    S3[Sentiment / calendar]
  end
  subgraph LAKE[Alpha-Lake]
    direction TB
    ING[httpx connectors]
    RAW[(Raw archive<br/>immutable)]
    CAN[(DuckLake canonical<br/>bitemporal)]
    SRV[Serving<br/>readers · panel · catalog · health]
  end
  subgraph STORE[Storage backends]
    direction TB
    CAT[(Catalog DB<br/>Postgres primary<br/>SQLite embedded tests)]
    OBJ[(Object store<br/>RustFS primary<br/>local FS embedded tests)]
  end
  CON[Consumers]
  S1 & S2 & S3 --> ING --> RAW --> CAN --> SRV --> CON
  CAN -. metadata .-> CAT
  CAN -. parquet .-> OBJ
```

The domain core (`models/`) has no I/O. Adapters implement the serving contracts; the serving layer is the only thing consumers import.

### 2.2 Layer rules (CI-enforced by `import-linter`, §17)

| Layer | May import | May not import |
|---|---|---|
| `models/` | stdlib, polars, patito | everything else |
| adapters (`connectors`, `canonical`, `quality`, `catalog`, `serving`) | `models/`, `storage/` | orchestration |
| `flows/`, `cli` | all above | — |

## 3. Runtime model & self-containment

Alpha-Lake is **stack-first**. The production-shaped runtime is the default from day one: Postgres catalog, S3-compatible object storage, DuckLake, OpenTelemetry, and optional Dagster. The goal is to exercise the real catalog/object-store boundary immediately, not after the data model is already built around a simplified local filesystem path.

The lightweight embedded path still exists, but only as a **test/debug/golden-replay harness**. It is not a first-class runtime and should not drive architectural decisions.

```mermaid
flowchart TB
  subgraph STACK["reference runtime — stack-first Compose"]
    direction LR
    J[just up] --> APP[alpha-lake app container]
    APP --> PG[(DuckLake catalog · Postgres)]
    APP --> S3[(Parquet data · RustFS/S3)]
    APP --> OTEL[OTel collector]
    DAG[Dagster optional] --> APP
  end
  subgraph EMBED["embedded harness — tests / replay only"]
    direction LR
    T[pytest / golden replay] --> SQL[(DuckLake catalog · SQLite)]
    T --> FS[(local filesystem data)]
  end
```

| | Reference stack | Embedded harness |
|---|---|---|
| Purpose | Normal development, integration, v0.1 validation | Fast tests, debugging, fixture generation, golden replay |
| Runtime | Docker Compose or Podman Compose | In-process Python / DuckDB |
| Catalog | Postgres container | SQLite file |
| Object store | RustFS S3-compatible container/binary | local filesystem |
| Orchestration | Typer CLI in app container; Dagster optional | pytest / replay runner |
| Observability | OTel → collector | OTel → console |
| Command shape | `just up`, `just bootstrap`, `just ingest`, `just health` | `just test`, `just replay` |
| Architectural status | **Primary path** | **Supporting harness only** |

The developer does not install Postgres, RustFS, Dagster, DuckDB extensions, or observability services locally. The only expected host tools are a container runtime, `just`, and optionally `uv` for local editing. The stack is started and stopped as one isolated namespace.

## 4. The temporal model (conceptual)

Three clocks, tracked independently. Buildable mechanics in §11.

```
valid time     effective_date   when the fact is true in the market
knowledge time available_at     when the lake could first serve it   ← the PIT boundary
system time    DuckLake snapshot when the lake physically committed   (audit / rollback)
```

- **`as_of` is a query parameter, never a canonical stored column.** Only `available_at` governs visibility. Rebuildable derived caches may store the requested `as_of` as cache-key metadata; that cache value is not canonical truth.
- **System time ≠ knowledge time.** They coincide at first ingest but diverge on backfill/replay. `available_at` is a stored domain fact; DuckLake snapshots are audit/reproducibility — never the PIT boundary.
- **Restatements are versions, not overwrites.** A correction mints a new `available_at` version; prior versions are retained.
- **Valid-time filtering is dataset-class-specific.** Historical observation reads exclude future effective dates; known-future event reads may return future `event_date`/`effective_date` rows when they were already knowable at `as_of`.
- **Timestamp/date policy.** All instants (`available_at`, `ingested_at`, `validated_at`, source publish times when precise) are stored UTC. `effective_date` is an exchange-local session date resolved through the pinned trading-calendar oracle, not the UTC calendar date.

## 5. Domain model overview

The lake's market models describe **facts**; operational datasets describe pipeline state and never participate in the research PIT read path. → full schemas §9.

| Market fact entities (lake) | Operational / metadata datasets | Forbidden here (consumer-owned) |
|---|---|---|
| `Security`, `BarFact`, `FundamentalFact`, `InsiderTransactionFact`, `NewsArticleFact`, `SocialPostFact`, `EntityMentionFact`, `SentimentAnnotationFact`, `AttentionMetricFact`, `CorporateActionFact`, `EarningsEventFact` | `DataQualityEvent`, `DatasetVersion`, `QuarantineRow`, `ReconciliationEvent`, `IngestionOutcome` | scores, ranks, signals, positions, fills, decisions, risk actions, journals |

**Eligibility test for anything the lake exposes** (§14–15): *its definition would be byte-identical for two consumers who completely disagree about market direction.*

## 6. Component flow

```mermaid
flowchart LR
  E[fetch · connector] --> R[(archive raw)] --> N[parse · Polars]
  N --> V[validate · Patito] --> Q{ok?}
  Q -- yes --> C[(canonicalize · DuckLake · bitemporal SCD2)]
  Q -- no --> X[(quarantine · lineage)]
  C --> D[derive views] --> S[serve · PIT readers / panel / catalog]
```

Each stage maps to a Part II section: fetch §7–8, parse/validate §13, canonicalize §9/§11/§17, derive §14, serve §18.

---

# Part II — Implementation Reference

## 7. Source registry (Zone 0)

All source behavior is data, not code. One source row drives connector mechanics; one dataset-source row drives dataset-specific precedence, freshness, parser, contract, and reconciliation behavior.

```
source_registry:
  source_id            stable id (e.g. "eodhd")
  source_name          human label
  source_type          rest | html | file
  auth_type            api_key | oauth | none
  api_key_env          env var name for the secret (never the secret)
  rate_limit_per_min   token-bucket budget
  retry_policy         max_attempts, backoff, jitter
  owner                accountable name
  enabled              bool

source_dataset_registry:
  dataset_id           canonical dataset id
  source_id            source_registry FK
  role                 primary | secondary | validation | enrichment
  priority             lower = higher precedence within this dataset
  cadence              daily | weekly | on_demand
  freshness_sla_days   max acceptable staleness for this dataset/source pair
  parser_version       current parser id for this dataset/source pair
  contract_version     dataset contract id served
  enabled              bool
```

### Data suppliers (per-dataset)

| Dataset | Primary Source | Secondary Source(s) |
|---------|---------------|---------------------|
| OHLCV bars — daily | EODHD or Tiingo EOD | Alpaca |
| OHLCV bars — intraday | Alpaca (deferred) | Tiingo IEX, EODHD |
| Fundamentals | SEC EDGAR Companyfacts | Tiingo, EODHD |
| Insider transactions | SEC EDGAR Forms 3/4/5 | commercial (future) |
| Earnings calendar | EODHD | — |
| news_articles | Tiingo News | Alpaca News, EODHD News |
| social_posts | Reddit API | Tiingo/EODHD enrichment |
| entity_mentions | inferred from source text (NLP) | SEC EDGAR (CIK to ticker mapping) |
| sentiment_annotations | vendor/ML model (FinBERT, LLM) | — |
| attention_metrics | derived from news_articles + social_posts | — |
| Corporate actions | EODHD or Tiingo splits-dividends | SEC filings (validation) |
| Security master | Alpha-Lake internal | OpenFIGI, EODHD, Tiingo, SEC |

Precedence and freshness are dataset-specific, not global source properties. A source can be primary for one dataset and secondary or validation-only for another. `source_dataset_registry.priority` drives §11 stage-2 source collapse. Dataset-level SLA and parser/contract versions live there because the same supplier can serve different datasets with different cadences, schemas, and authority.

Each connector is modeled as one issue per (dataset, supplier) pair on the project board. See the [Alpha-Lake Project Board](https://github.com/users/mblaauw/projects/4) for the full issue breakdown.

## 8. Connectors & raw archive

**Connectors** (custom `httpx`/`tenacity` functions, dispatched via `get_connector()` registry) build requests, enforce rate limits, apply retry, archive the raw response **before any parse**, emit fetch events, return fetch metadata. They must not interpret, write canonical, or hide partial failure.

**Raw archive** — immutable, content-addressed:

```
raw/source={id}/endpoint={ep}/year={yyyy}/month={mm}/day={dd}/{fetch_id}.zst
```

**Manifest row** (one per fetch):

```
fetch_id                sha256(source|endpoint|params|ingest_ts)[:16]
source_id  endpoint
request_params_hash     pinned canonicalization (sorted keys, normalized types)
request_params_json
ingest_ts  http_status
content_hash            sha256 of raw bytes — archive integrity / storage dedup
content_type  byte_size
parser_version_intended
```

**Archive integrity:** re-fetch with identical `content_hash` is a raw-storage no-op. Nothing in the archive is ever rewritten or deleted (I1).

**Semantic version identity (I9):** canonical versioning and restatement detection use `version_hash = sha256(canonicalized_records)`, not raw bytes. The canonicalization recipe is pinned per parser/normalizer version: sorted keys, normalized numeric precision, normalized dates, stable null handling, deterministic row ordering, and `normalization_version`. Non-deterministic API envelopes, response ordering, gzip framing, request IDs, and server timestamps must not mint a new semantic version when the canonical records are unchanged.

## 9. Canonical data model

Parquet tables managed by DuckLake. Every canonical row carries the **temporal columns** + the **lineage columns**.

**Temporal columns (every dataset):**

```
effective_date     valid time
available_at        knowledge time (PIT boundary)
source_published_at source's stated publish time (nullable)
ingested_at         raw fetch time
validated_at        passed-validation time
```

**Lineage columns (every dataset):**

```
security_id  source_id  schema_version  parser_version
source_fetch_id  raw_payload_hash  ingestion_run_id  content_hash  version_hash  quality_status
```

**Per-dataset business fields & keys:**

| Dataset | Business fields | Natural key | Version identity |
|---|---|---|---|
| `bars` | open, high, low, close, volume (**raw only**) | `security_id + effective_date + source_id` | natural + `available_at + version_hash` |
| `fundamentals` | fiscal_period, statement_type, line_item, value, currency | `… + fiscal_period + statement_type + line_item + source_id` | natural + `available_at + version_hash + parser_version` |
| `insider_tx` | filer_cik, issuer_cik, transaction_code, shares, price, value | `filer_cik + issuer_cik + transaction_date + transaction_code + shares + price + source_id` | natural + `available_at + version_hash` |
| `corp_actions` | action_type, ratio/amount, ex_date | `security_id + action_type + effective_date + source_id` | natural + `available_at + version_hash` |
| `news_articles` | article_id, title, description, url, text_hash, published_at, source_name | `article_id + source_id` | natural + `available_at + version_hash` |
| `social_posts` | platform, venue, post_id_hash, parent_id_hash, text_hash, published_at, engagement_json | `post_id_hash + source_id` | natural + `available_at + version_hash` |
| `entity_mentions` | mention_id, text_item_id, text_item_type (news_article / social_post), security_id, entity_name, entity_type, confidence, match_method | `mention_id` | natural + `available_at + version_hash` |
| `sentiment_annotations` | annotation_id, text_item_id, text_item_type, sentiment_score, sentiment_label (positive/neutral/negative), model_version, prompt_version, taxonomy_version, input_text_hash, source_dataset_version | `annotation_id` | natural + `available_at + version_hash + model_version` |
| `attention_metrics` | security_id, window_start, window_end, window_type (1d/3d/7d), article_count, mention_count, unique_source_count, unique_author_count, mean_sentiment, sentiment_std, positive_share, neutral_share, negative_share, velocity_score | `security_id + window_start + window_end + window_type` | natural + `available_at + version_hash` |
| `earnings_calendar` | report_date, session | `security_id + report_date + source_id` | natural + `available_at + version_hash` |

**Raw-only bars rule:** adjusted prices are *views* (§12), never stored facts; `price_mode` is a serve parameter, never part of identity.

**Hash canonicalization:** `version_hash` and any fallback hash (e.g. insider `normalized_hash` when CIK is absent) use the pinned recipe above or idempotency breaks across parser versions.

## 10. Security master & resolution

`symbol` is unstable (rename/reuse); `security_id` is canonical from row one and deterministic across replay.

**Model:**

```
security_id  symbol  exchange  name  cik  figi  isin  currency
valid_from  valid_to  status  source_id  available_at
```

**Deterministic minting:** `security_id` is minted from stable identifiers, never from a symbol and never from randomness. The minting input is the first available stable-key tuple in priority order: FIGI, then CIK, then ISIN, then a documented composite fallback (`exchange + source_native_id + first_listed_date`) only when no global identifier is available. The generated ID is a deterministic hash/ULID over the chosen tuple and `security_master_id_version`. If FIGI/CIK/ISIN disagree across sources, the row is quarantined for identity conflict unless an explicit mapping already exists in the security master. A brand-new security is minted only when no active or historical security record matches any stable identifier in the tuple.

**Point-in-time resolution** (itself bitemporal — cannot leak a future rename):

```sql
SELECT security_id FROM security_master
WHERE symbol = :symbol AND exchange = :exchange
  AND valid_from <= :as_of AND (valid_to IS NULL OR valid_to > :as_of)
  AND available_at <= :as_of
QUALIFY row_number() OVER (ORDER BY available_at DESC) = 1;
```

Canonical datasets are keyed by `security_id`; `symbol` is resolved only at the API edge (§18) for caller convenience.

## 11. The point-in-time read (mechanics)

Every research read applies `available_at <= :as_of`, then applies the dataset's valid-time rule and resolves to one value in **two stages**: newest knowledge-time version per source, then source precedence. The preferred implementation for stage 1 is DuckDB's native `ASOF JOIN` against the requested spine (newest version whose `available_at <= as_of`); window-function collapse is acceptable only for small/simpler paths or tests.

For historical observation datasets such as bars, the valid-time rule is `effective_date <= :as_of`. For known-future event datasets such as earnings calendars or announced corporate actions, readers may return future `event_date`/`effective_date` rows if `available_at <= :as_of`; the fact that an event is scheduled in the future can itself be knowable today.

```sql
WITH versioned AS (                              -- stage 1: newest version per (fact, source)
  SELECT *, row_number() OVER (
            PARTITION BY security_id, effective_date, source_id
            ORDER BY available_at DESC, version_hash) AS v_rn
  FROM bars
  WHERE security_id = :sid
    AND effective_date BETWEEN :start AND :end
    AND effective_date <= :as_of
    AND available_at <= :as_of)
SELECT * EXCLUDE (v_rn, s_rn) FROM (             -- stage 2: collapse sources by precedence
  SELECT *, row_number() OVER (
            PARTITION BY security_id, effective_date
            ORDER BY dataset_source_priority ASC) AS s_rn
  FROM versioned WHERE v_rn = 1)
WHERE s_rn = 1;
```

Stage 1 alone returns one row per source; stage 2 yields the single canonical answer. Dataset-specific source priority is registry data (§7).

**Restatement (worked example):**

```
security_id | effective_date | close  | available_at         | content_hash
sec_7f3a…   | 2026-06-01     | 195.10 | 2026-06-02T07:00:00Z | a1…
sec_7f3a…   | 2026-06-01     | 195.23 | 2026-06-10T07:00:00Z | b2…
```
`as_of=2026-06-05 ⇒ 195.10` · `as_of=2026-06-17 ⇒ 195.23`. Overwriting violates I4.

**Backfill:** a bar for `2024-01-05` ingested on `2026-06-17` gets `available_at=2026-06-17`. `as_of=2024-01-06` cannot see it; `as_of=2026-06-17` can. Backfills improve current knowledge; they never rewrite what was historically knowable.

**No-latest-by-default (I12):** research readers require `as_of`; the default is a loud sentinel, not `None` — a separately named `latest_*` path is the only route to unbounded reads.

`latest_*` results are explicitly marked PIT-unsafe (distinct return type or `pit_unsafe=True`) and still apply `available_at <= now()`; they must not silently flow into backtests or research APIs.

## 12. Corporate actions & adjusted views

Store raw facts; serve adjusted views computed from only the actions **knowable at `as_of`**.

**Adjustment rule:** for `price_mode=split_adjusted, as_of=A`, apply only
`corp_action WHERE effective_date <= A AND available_at <= A`.

**Required leakage test (one of the most important):**

```
raw price 2025-01-01; split effective 2025-06-01; split available_at 2025-06-02
  as_of 2025-05-30 ⇒ split NOT applied
  as_of 2025-06-03 ⇒ split MAY be applied
```

`price_mode ∈ {raw, split_adjusted, total_return_adjusted}`. Dividends are recorded; cash dividends do not restructure the raw OHLCV series. Adjustment is a pure function over the PIT action set.

## 13. Validation, quarantine, reconciliation

**Validation = Patito** (Polars-native pydantic): the fact model *is* the schema *is* the validator. Checks run on exit from normalize, before canonical write.

**Categories:**

- *Structural* — required fields, parseable types, valid enums/dates, non-empty PK.
- *Market sanity* — no zero/negative price; no impossible OHLC (`low ≤ open,close ≤ high`); `|return| > tol` requires a corp-action record; non-negative volume; deterministic dedup.
- *Freshness (per-dataset SLA)*:

  | Dataset | SLA |
  |---|---|
  | attention_metrics | ≤ 1d |
  | bars | available by next trading day |
  | earnings_calendar | ≤ 7d |
  | entity_mentions | ≤ 1d |
  | fundamentals | ≤ 30d (or source-specific) |
  | insider_tx | ≤ 3 trading days |
  | news_articles | ≤ 1d |
  | security_master | ≤ 7d |
  | sentiment_annotations | ≤ 2d |
  | social_posts | ≤ 1d |

- *Point-in-time* — no research read defaults to "latest".

**Failure levels:** `SOURCE_DEGRADED` (continue) · `DATA_QUARANTINED` (rows rejected, dataset continues) · `DATA_STALE` (SLA violated) · `DATA_HALT` (consumer-blocking, e.g. stale prices) · `SOFTWARE_HALT` (impossible state).

**Quarantine envelope** (a first-class product; every rejected row is replayable, no orphans — I11):

```
quarantine_id  dataset  reason_code  severity
security_id  source_id  effective_date  available_at
fetch_id  raw_payload_hash  parser_version  schema_version
record_payload  created_at  repair_status
```

**Reconciliation ≠ quarantine (I10).** A valid *primary* is never quarantined because a *secondary* disagrees. Quarantine = intrinsic defects (negative price, `high<low`, bad date, missing PK). Cross-source disagreement emits:

```
ReconciliationDisagreement{
  dataset  security_id  effective_date
  primary_source_id  secondary_source_id  field
  primary_value  secondary_value  difference  tolerance  severity  available_at }
```

Reconciliation disagreements are persisted as an append-only operational dataset parallel to quarantine:

```
reconciliation_events
  event_id  dataset_id  natural_key  security_id  effective_date
  primary_source_id  comparison_source_id  severity
  observed_at  available_at  ingestion_run_id
  field_diffs_json  tolerance_id  action  resolution_sla_at  resolved_at
```

Severity maps to action in configuration: `info` records only, `warn` increments health counters, `error` blocks freshness-green status for the dataset, and `data_halt` blocks canonical promotion for affected natural keys until resolved. Reconciliation disagreements do not halt a valid primary by default (I10), but configured `data_halt` cases do.

**Per-entity ingest outcomes:** multi-entity runs record one outcome per requested entity: `ok`, `empty`, `failed`, or `quarantined`. Run-level policy is partial commit with explicit outcome ledger unless the dataset contract requires all-or-nothing. Health surfaces counts and blocking reasons.

## 14. Derived technical indicator library

Alpha-Lake provides a broad, neutral technical-indicator library over PIT-safe daily bars.

These indicators are **not canonical market facts** and are not stored on the canonical `bars` table. They are deterministic, rebuildable, parameterized transforms over:

* raw OHLCV bars,
* corporate-action-aware adjusted bar views,
* known-at-`as_of` corporate actions,
* optionally benchmark/index bars where the indicator requires comparison.

The purpose is to prevent every downstream consumer from reimplementing common calculations while keeping strategy interpretation outside the lake.

```python
lake.indicators.sma(symbol="AAPL", window=50, as_of=A, price_mode="split_adjusted")
lake.indicators.macd(symbol="AAPL", fast=12, slow=26, signal=9, as_of=A)
lake.indicators.bollinger(symbol="AAPL", window=20, stddev=2.0, as_of=A)
```

### 14.1 Indicator design rules

* Indicators are **parameterized**; no hardcoded strategy windows.
* Indicators are **PIT-bounded**; inputs must satisfy `available_at <= as_of`.
* Indicators are **neutral**; no `buy`, `sell`, `bullish`, `bearish`, `rank`, `score`, or `signal`.
* Indicators are **derived views or cacheable outputs**, not canonical facts.
* Indicator outputs record input dataset versions, parameters, code version, and price mode.
* Consumers own interpretation, thresholds, ranking, portfolio logic, and trading decisions.

### 14.2 Indicator categories

Alpha-Lake may provide the following indicator families because they are mechanically derivable from daily OHLCV bars.

| Category                   | Examples |
| -------------------------- | -------- |
| Price transforms           | close, adjusted close view, typical price, median price, weighted close, OHLC average |
| Returns                    | simple return, log return, cumulative return, rolling return, gap return, overnight/intraday proxy return |
| Moving averages            | SMA, EMA, WMA, VWMA, SMMA/RMA, DEMA, TEMA, HMA, KAMA, ALMA, ZLEMA |
| Trend                      | MACD, PPO, ADX, DMI, Aroon, DPO, TRIX, Mass Index, Vortex Indicator |
| Momentum                   | RSI, Stochastic Oscillator, Stochastic RSI, ROC, Momentum, Williams %R, CCI, TSI, Ultimate Oscillator, KST |
| Volatility                 | True Range, ATR, NATR, rolling standard deviation, historical volatility, Parkinson volatility, Garman-Klass volatility, Rogers-Satchell volatility |
| Bands/channels             | Bollinger Bands, Keltner Channels, Donchian Channels, Price Channels, STARC Bands |
| Volume                     | volume SMA/EMA, volume z-score, OBV, Volume Price Trend, Accumulation/Distribution Line, Chaikin Money Flow, Chaikin Oscillator, Money Flow Index, Force Index, Ease of Movement, Negative/Positive Volume Index |
| Range/breakout             | rolling high/low, highest high, lowest low, breakout distance, channel position, close location value |
| Risk/statistics            | rolling beta, rolling correlation, rolling covariance, rolling Sharpe-like ratio, rolling drawdown, max drawdown, downside deviation, skew, kurtosis |
| Support/resistance helpers | pivot points, rolling support/resistance levels, distance to rolling high/low |
| Candlestick facts          | candle body, upper/lower wick, range, doji-like shape, engulfing-like shape, hammer-like shape |
| Relative strength          | relative return versus benchmark, ratio series, rolling relative momentum, rolling beta-adjusted return |
| Calendar/bar metadata      | trading-day index, month/quarter/year flags, day-of-week, month-end, quarter-end |

Candlestick pattern helpers are allowed only as neutral structural descriptions of OHLC shapes. They must not be named or exposed as trading advice.

### 14.3 Indicators that require caution

Some indicators can be derived from daily bars but need explicit semantics:

| Indicator type                | Rule |
| ----------------------------- | ---- |
| VWAP                          | Daily OHLCV cannot produce true intraday VWAP. Alpha-Lake may expose only an approximate period VWAP using typical price × volume. |
| Anchored VWAP                 | Allowed only when the anchor date is provided explicitly by the consumer. |
| Total-return indicators       | Allowed only when `price_mode="total_return_adjusted"` is explicitly requested. |
| Benchmark-relative indicators | Allowed only when the benchmark/index/security is explicitly provided. |
| Pattern recognition           | Allowed as neutral OHLC geometry, not as predictive labels. |

### 14.4 Recursive indicator warm-up/lookback

Recursive indicators (EMA, RSI, ATR, KAMA, SMMA/RMA, MACD, ADX, and similar) require history before the requested `start`. Each implementation must either fetch an explicit `available_at`-bounded lookback window before `start` or use a documented deterministic seed convention. `IndicatorResult` metadata records `lookback_bars_requested`, `lookback_bars_used`, `seed_policy`, `input_start`, and `output_start` so values are reproducible and stable regardless of the caller's visible window.

### 14.5 Optional materialized indicator cache

Frequently reused indicators may be cached, but the cache remains rebuildable derived state.

```
technical_indicator_cache
  security_id
  effective_date
  as_of
  price_mode
  indicator_name
  parameters_hash
  parameters_json
  value_json
  input_dataset_version
  input_snapshot_id
  code_version
  created_at
```

Cache rules:

1. Cache entries are invalidated when input bars, corporate actions, security master mappings, code version, or parameter definitions change.
2. Cache entries are not canonical truth.
3. Cache entries must be reproducible from canonical inputs.
4. Cache reads must preserve the same PIT guarantees as normal readers.
5. Cache misses compute on demand or fail explicitly, depending on caller policy.

### 14.6 Boundary with Alpha-Quant

Alpha-Lake may provide:

```text
sma(close, 50)
macd(close, 12, 26, 9)
bollinger(close, 20, 2)
rolling_return(close, 20)
atr(high, low, close, 14)
relative_strength(close, benchmark_close, 90)
```

Alpha-Lake must not provide:

```text
golden_cross_signal
macd_buy_signal
low_risk_entry
candidate_rank
trend_score
portfolio_weight
stop_loss_action
trade_decision
```

The lake computes neutral market-derived measurements. Alpha-Quant decides what they mean.



## 15. Derived news & social analytics layer

Alpha-Lake provides a neutral text-derived analytics layer for news and social data.

Canonical text datasets store source-grounded facts: article/post metadata, raw payload
lineage, publication time, availability time, source identity, and immutable text hashes.

Derived NLP outputs such as entity links, sentiment, topic labels, embeddings, summaries,
novelty measures, mention counts, and attention velocity are versioned derived datasets
or rebuildable caches, not source-grounded canonical truth. Every derived text annotation
must record the model version, prompt version, taxonomy version, input text hash, source
dataset version, and `as_of` boundary.

Alpha-Lake may measure attention and sentiment. It must not decide whether attention or
sentiment is bullish, bearish, tradable, risky, or actionable. That interpretation belongs
to Alpha-Quant or another consumer.

### 15.1 Text analytics design rules

1. **Source-grounded canonical layer** — `news_articles` and `social_posts` store raw text facts with full lineage.
2. **Versioned derived layer** — `entity_mentions`, `sentiment_annotations`, and `attention_metrics` are reproducible derived annotation/metric datasets, not source-provided truth.
3. **Annotated, not judged** — derived NLP outputs use neutral labels (sentiment score, topic,
   entity, embedding). No `bullish`, `bearish`, `risky`, `actionable`, `signal`.
4. **Versioned** — every annotation records `model_version`, `prompt_version`, `taxonomy_version`,
   `input_text_hash`, `source_dataset_version`.
5. **PIT-bounded** — all derived values satisfy `available_at <= as_of`.
6. **Rebuildable** — all derived values are reproducible from canonical text datasets.
7. **Erasure posture** — raw text remains immutable by default, but legally required takedown/erasure requests create a documented tombstone exception: raw bytes may be redacted or removed only through a governed deletion record that preserves lineage, hashes, reason, approver, and affected derived datasets. Derived annotations and caches referencing erased text are invalidated or tombstoned.

### 15.2 Canonical text datasets

| Dataset | Content | Grounding |
|---------|---------|-----------|
| `news_articles` | article_id, title, description, url, text_hash, published_at, source_name | Source-provided metadata; raw payload archived |
| `social_posts` | platform, venue, post_id_hash, parent_id_hash, text_hash, published_at, engagement_json | Source-provided metadata; raw payload archived |
| `entity_mentions` | mention_id, text_item_id, text_item_type, security_id, entity_name, entity_type, confidence, match_method | Versioned derived linkage via NLP + security master; confidence recorded |
| `sentiment_annotations` | annotation_id, text_item_id, text_item_type, sentiment_score, sentiment_label, model_version, prompt_version, taxonomy_version, input_text_hash, source_dataset_version | Versioned derived ML/vendor annotation; model/prompt/taxonomy pinned |
| `attention_metrics` | security_id, window_start, window_end, window_type, article_count, mention_count, unique_source_count, unique_author_count, mean_sentiment, sentiment_std, positive_share, neutral_share, negative_share, velocity_score | Rebuildable derived metrics from news_articles + social_posts + sentiment_annotations |

### 15.3 Derived metric categories

| Category | Examples |
|----------|----------|
| Volume | article count, mention count, unique source count, unique author count |
| Velocity | 1d/3d/7d mention change, news acceleration, abnormal volume z-score |
| Sentiment | mean sentiment, sentiment distribution, positive/neutral/negative share |
| Entity linkage | ticker mentions, company-name mentions, CIK/entity match confidence |
| Topic / event | topic labels, event clusters, earnings-related / news-related classification |
| Novelty | duplicate detection, first-seen story, repeated-story count |
| Engagement | Reddit score, comments, upvote ratio, engagement velocity |
| Source quality | source category, publisher reliability tier, official/company/regulatory/news/social |
| Co-mentions | company-company co-mentions, company-sector co-mentions |
| Text features | embeddings, keyword hits, named entities, summary, language |

### 15.4 Annotation recording rules

Every derived text annotation row must include:

```
model_version      pinned model identifier (e.g. "finbert-v2")
prompt_version     pinned prompt/recipe identifier (e.g. "sentiment-v3")
taxonomy_version   pinned label taxonomy version (e.g. "entity-taxonomy-v1")
input_text_hash    sha256 of the text string or canonical content_hash of the source row
source_dataset_version  version of the canonical dataset at time of annotation
as_of              PIT boundary that governed the computation
```

### 15.5 Boundary with Alpha-Quant

Alpha-Lake may provide:

```text
mention_count(AAPL, 2026-06-01, 2026-06-07)
mean_sentiment(AAPL, 2026-06-01, 2026-06-07)
article_velocity(AAPL, 7d)
unique_sources(AAPL, 2026-06-01, 2026-06-07)
entity_mentions(AAPL, "AAPL", "ticker")
topic_labels(article_id, "earnings")
novelty_score(article_id, 0.92)
engagement_velocity(post_id, 3d)
```

Alpha-Lake must not provide:

```text
bullish_news_signal
reddit_hype_score
buy_pressure_score
trade_candidate_rank
negative_catalyst_action
sentiment_signal = "bearish"
risk_flag = "avoid"
```

The lake measures attention and sentiment. It never decides what they mean.

### 15.6 Optional materialized text analytics cache

Frequently reused NLP outputs or aggregated metrics may be cached in a table analogous
to the indicator cache (§14.4). Cache rules are identical:

1. Cache entries are invalidated when source canonical text data, model version, prompt
   version, or taxonomy version change.
2. Cache entries are not canonical truth.
3. Cache entries must be reproducible from canonical inputs.
4. Cache reads must preserve the same PIT guarantees as normal readers.
5. Cache misses compute on demand or fail explicitly, depending on caller policy.

## 16. Storage — DuckLake + RustFS

**DuckLake v1.0** (`ducklake` DuckDB extension): the official DuckDB extension for the DuckLake lakehouse format. It manages ACID transactions, snapshots, time travel, schema evolution, and partitioning natively. Connection is a single ATTACH statement — the extension handles extension loading (httpfs, parquet, postgres, sqlite), catalog management, and S3 configuration internally.

The **reference attach path is stack-first**: Postgres catalog + RustFS/S3 data. The SQLite/local-FS attach path is kept only for embedded tests and golden replay.

DuckLake's ATTACH is preceded by explicit `INSTALL httpfs; LOAD httpfs` to ensure the HTTP/S3 filesystem extension is available before DuckLake loads data from S3. While DuckLake theoretically auto-loads httpfs, explicit loading eliminates race conditions during extension initialization.

```sql
-- attach (reference stack) — Postgres catalog + RustFS/S3 data
INSTALL ducklake; LOAD ducklake; INSTALL postgres; LOAD postgres;
INSTALL httpfs; LOAD httpfs;
ATTACH 'ducklake:postgres:host=postgres dbname=lake_catalog user=lake password=lake'
    AS lake_catalog (DATA_PATH 's3://lake/');
USE lake_catalog;

-- attach (embedded harness only) — tests / replay / debugging
INSTALL ducklake; LOAD ducklake; INSTALL sqlite; LOAD sqlite;
ATTACH 'ducklake:sqlite:data/lake.catalog'
    AS lake_catalog (DATA_PATH 'data/lake/');
USE lake_catalog;
```

**Tri-temporal mapping:** valid + knowledge time are *columns*; system time is the *DuckLake snapshot* — every committed transaction creates a snapshot, tagged by `snapshot_id`, giving audit trail + pinnable reproducibility (§21).

**Schema evolution:** additive (nullable columns) within a major via DuckLake; required-field/meaning/PK changes mint a new major (`bars.v2` coexists with `v1`); consumers declare supported versions.

**Patito-derived DDL — single source of schema truth:** Table definitions are no longer hardcoded SQL strings. Instead, `_generate_ddl(model_class, table_name)` reads Patito model annotations and generates DuckDB-compatible `CREATE TABLE` DDL. Each dataset is registered as a `Dataset` descriptor (`table`, `model`, `natural_keys`) in a `DATASETS` registry — no more parallel `_DATASET_KEYS` or `key_map` dictionaries. A single `write(con, dataset, df)` function handles all datasets (bars, corp_actions, fundamentals, insider, news, social, earnings, entity mentions, sentiment annotations, attention metrics), while backward-compatible `write_bars`, `write_corp_actions`, and `write_dataset` wrappers keep callers unchanged. See `src/alpha_lake/canonical/__init__.py`.

**Blob store abstraction (raw archive):** The raw archive subsystem uses a `BlobStore` ABC (`src/alpha_lake/storage/__init__.py`) instead of direct path/URI access. Two backends are registered:
- **`_LocalBlobStore`** — wraps `pathlib.Path` for local filesystem access (embedded harness).
- **`_S3BlobStore`** — wraps `s3fs.S3FileSystem` for S3-compatible object storage (reference stack).

The factory `get_blob_store(uri: str) -> BlobStore` selects the backend by URI scheme (`s3://` → S3, everything else → local). This eliminates the storage split-brain where stack-mode raw archive writes went to the container's ephemeral disk instead of RustFS. See [ADR-0022](docs/adr/0022-blob-store.md) for the full decision.

**Config split:** The old single `data_path` key is replaced by `canonical_data_path` (for DuckLake data) and `raw_archive_uri` (for the raw archive blob store), making the two storage domains explicit in both code and configuration.

**Canonical Parquet layout:** canonical bars partition by `effective_date` year/month via `ALTER TABLE lake_bars SET PARTITIONED BY (year(effective_date), month(effective_date))`. Target 128-512 MB Parquet files per data file. DuckLake's file-level zone maps enable partition pruning during PIT reads.

**Snapshot retention and compaction:** DuckLake provides built-in maintenance operations: `CALL lake_catalog.merge_files(...)`, `CALL lake_catalog.expire_snapshots(...)`, and `CALL lake_catalog.checkpoint(...)`. Compaction may rewrite physical Parquet files but preserves snapshot-to-data mappings. Retention is configurable per snapshot. See [ADR-0021](docs/adr/0021-snapshot-retention-compaction-reproducibility.md) for the full retention and compaction policy. See [operations.md](docs/operations.md) for monitoring thresholds and growth expectations.

## 17. Ingestion pipeline — connector dispatch

Connectors are registered per source in the connector registry (`src/alpha_lake/connectors/__init__.py`), then dispatched at runtime by `ingest_bars()` in `flows/__init__.py`:

```python
connector = get_connector(src, "bars_daily")
creds = has_api_key(src)
clock_now = get_clock().now()

if connector and creds:
    async def _run_all():
        for sid in security_ids:
            total += await _fetch_and_ingest(
                con, connector, sid, src, from_date, to_date, run_id, clock_now,
            )
    total = asyncio.run(_run_all())
else:
    for sid in security_ids:
        total += _ingest_synthetic(con, sid, src, from_date, to_date, run_id, clock_now)

# flow: connector fetch → archive raw (pre-parse) → Polars normalize → Patito validate
#       → DuckLake SCD2 write on knowledge time → snapshot tagged ingestion_run_id
```

**Connector contract:** connectors fetch and archive. They return a `RawFetch` with body + manifest metadata. They must not parse, validate, write canonical, or hide partial failure. Per-entity outcomes (`ok`, `empty`, `failed`, `quarantined`) are recorded as an outcome ledger, not dlt incremental state.

**Synthetic fallback:** when no API credentials are available (CI, offline), `_ingest_synthetic()` generates deterministic sample data that passes market sanity checks. This preserves end-to-end test coverage without live API access.

**Registry data drives behavior:** per-source auth type, rate limit, retry policy, and parser version come from `source_registry` data — not hardcoded in connector code. See `src/alpha_lake/source_registry.py`, `config/stack.toml`.

## 18. Serving API

```python
lake = MarketLake.open(config)

# readers — research readers REQUIRE as_of
bars = lake.bars(symbol="META", start=d1, end=d2, as_of=A, price_mode="split_adjusted")
fund = lake.fundamentals(symbol="AAPL", as_of=A)

# as-of panel — scalar as_of (whole panel as known at one instant)
panel = lake.panel(securities=[...], fields=["close","volume"], start=d1, end=d2, as_of=A)

# spine join — each row carries its own as_of (true point-in-time join, leakage-free)
panel = lake.asof_panel(spine=dates_df,            # (security_id, decision_date)
                        fields=["close","fund.debt_to_equity"], as_of_col="decision_date")

# catalog (control plane) + health
lake.catalog.datasets(); lake.health(as_of=A)
```

Readers return typed models / Arrow tables. **Catalog** answers *what exists + is it trustworthy* (schema version, freshness, row/quarantine/reconciliation counts, dataset versions = DuckLake snapshots, lineage) from the DuckLake catalog DB — no separate metadata service. **Remote (deferred):** Arrow Flight SQL / ADBC (zero-copy, not REST); DuckLake read-only HTTPS share for simple cases.

`latest_*` methods are explicitly non-research escape hatches. They return a distinct PIT-unsafe type or carry `pit_unsafe=True`, and still filter to `available_at <= now()`.

## 19. Orchestration — flow functions, thin shells

Pipeline logic lives once in `flows/`. Shells wrap the same flow functions with no duplicated logic. The **Typer CLI inside the app container is the first operational shell** because it is the simplest way to prove the vertical slice against the real stack. Dagster is added after the core ingestion and PIT reader are correct.

```mermaid
flowchart LR
  F[flows/*.py — pipeline logic] --> CLI[Typer CLI · app container]
  F --> REP[pytest / replay harness]
  F --> DAG[Dagster assets · optional stack service]
```

**CLI surface:** `bootstrap · ingest · validate · backfill · gap-fill · reparse · rebuild · replay · health · catalog · freeze-fixtures · compact`.

`reparse` with a new `parser_version` mints a new canonical version visible at `available_at = reparse_time`. Snapshots pinned to the old version still see old values; reparse never mutates a prior canonical row or raw archive object.

**Reference execution:** `just up` starts Postgres + RustFS + the app container; `just ingest ...` executes the CLI in the app container against the real stack.

**Dagster (optional stack service):** each dataset becomes a **partitioned asset** (date partitions = backfill UX); **asset checks** wrap the Patito gates. SQLMesh is the optional endstate for a growing derived layer; v1 uses DuckDB views. Dagster is a shell over `flows/`, not the owner of business logic.

## 20. Observability — OpenTelemetry

One SDK for logs + metrics + traces; exporters: **OTLP → collector** in the reference stack and **console** in the embedded harness. The reference collector exports metrics to a queryable backend (Prometheus in the local stack; file exporter acceptable for offline harnesses) and may also keep debug output for development. Spans wrap each flow/asset. Metrics: `ingestion_runs, fetch_{ok,fail}`, `source_latency`, `rows_written`, `quarantine_count`, `reconciliation_count`, `freshness_lag`, `snapshot_count`, `replay_duration`. Health per dataset: `latest_effective_date`, `latest_available_at`, `freshness_status`, `row_count`, `quarantine_count`, `reconciliation_count`, `ingest_outcome_counts`, `source_status`, `blocking_reason`.

## 21. Determinism & replay

**Contract:** `canonical = f(raw, parser_version, schema_version, config, security_master_snapshot)`. **Replay/rebuild use the recorded `available_at` from the manifest, never wall-clock** (I7) — else re-ingest is nondeterministic.

**Pinned reproducibility:** a consumer pins a DuckLake snapshot (`ingestion_run_id`) + `fixture_version` to reproduce an exact historical view. Compaction must preserve the logical snapshot mapping for pinned runs; snapshot retention policy is an explicit operational contract.

**Fixture bundle** (`freeze-fixtures`) freezes: raw payloads · canonical rows · `available_at` values · dataset versions · security-master snapshot · corporate actions · schema/parser versions · content hashes · quarantine + reconciliation events.

**Golden replay** compares **both** business output **and** bitemporal row visibility — a replay that drops knowledge time is not point-in-time faithful.

**Mode-parity guard:** `tests/integration/test_mode_parity.py` verifies that the embedded and stack runtimes produce identical canonical values after ingesting the same data, and that stack-mode raw archive blobs are *not* present on the local filesystem (they live in RustFS). This test is the structural guard against storage split-brain regressions. It runs only when the Docker stack is available; otherwise it skips.

## 22. Configuration & secrets

Configuration is explicit about runtime shape. `stack` is the default; `embedded` is accepted only for tests, replay, and debugging.

The `data_path` key is split into `canonical_data_path` (DuckLake canonical storage) and `raw_archive_uri` (raw blob store). This ensures stack-mode raw archive writes reach RustFS instead of going to ephemeral container disk.

```toml
[lake]
runtime   = "stack"                                # stack | embedded
catalog   = "ducklake:postgres:host=pg dbname=lake_catalog"
canonical_data_path = "s3://lake/"
raw_archive_uri     = "s3://lake/raw/"

[s3]
endpoint  = "rustfs:9000"
url_style = "path"
use_ssl   = false

[sources.eodhd]
enabled = true
api_key_env = "ALPHA_LAKE_EODHD_API_KEY"
rate_limit_per_minute = 60

[source_datasets.bars.eodhd]
role = "primary"
priority = 10
freshness_sla_days = 2
parser_version = "eodhd-bars-v1"
contract_version = "bars.v1"

[quality.bars]
max_staleness_days = 2
halt_on_stale_prices = true
```

Embedded harness override:

```toml
[lake]
runtime   = "embedded"
catalog   = "ducklake:sqlite:data/lake.catalog"
canonical_data_path = "data/lake/"
raw_archive_uri     = "data/lake/"
```

Secrets via env or git-ignored local config — **never** written to raw, canonical, manifests, events, fixtures, snapshots. Connector logs redact `api_key/token/secret/authorization/cookie`.

## 23. Self-containment, Compose runtime & vendoring

The repo runs end-to-end with no external service or network. The reference runtime is a local **Docker Compose / Podman Compose** stack; Kubernetes is a future deployment target, not the v0.1 development substrate.

```mermaid
flowchart TB
  subgraph HOST[Developer host]
    J[just]
    CR[Docker or Podman]
  end
  subgraph PIN[Pinned & vendored in-repo]
    direction TB
    PY[uv.lock + vendor/wheelhouse/ — Python deps]
    IMG[vendor/images/*.tar — digest-pinned containers]
    BIN[vendor/bin/rustfs — optional static binary]
    CFG[.stack/ — service configs]
    NIX[flake.nix — devShell]
  end
  J --> CR
  CR --> IMG
```

- **Python:** `uv.lock` committed; `uv export` → `vendor/wheelhouse/` for offline `uv sync --offline` inside the app image or embedded harness.
- **App container:** the Alpha-Lake CLI runs inside a pinned app image so developers do not install Postgres, RustFS, DuckDB extensions, or service dependencies on the host.
- **Services:** `compose.yaml` pins **image digests** for Postgres, RustFS, the Alpha-Lake app, and optional Dagster/OTel collector. `just vendor` runs `docker save`/`podman save` into `vendor/images/` for air-gap transfer + load into an internal registry. RustFS may instead be the vendored static binary in `vendor/bin/`.
- **Developer convenience (devShell):** `flake.nix` provides a `nix develop` shell with Python 3.14 and uv pre-configured. It is a development convenience, not the reproducibility guarantee — the OCI image + uv.lock + vendored wheelhouse serve that role. Compose + uv remains the pragmatic default.

**Air-gapped workflow:** `just vendor` (online) → copy `vendor/` → `just up --offline` (air-gapped). Nothing reaches the internet at run time.

**Core `just` recipes:** `up · down · reset · logs · bootstrap · ingest · health · vendor · test · replay`. The old idea of `solo` as a primary command is replaced by explicit `test` and `replay` harness commands.

## 24. Repo layout

```
alpha-lake/
├── pyproject.toml  uv.lock  flake.nix  justfile
├── compose.yaml  Dockerfile                            # reference stack runtime
├── config/
│   ├── stack.toml                                      # Postgres + RustFS default
│   ├── embedded.toml                                   # tests / replay only
│   └── settings schema generated from Pydantic models
├── contracts/                                          # dataset contract YAML, e.g. bars.v1.yaml
├── vendor/{wheelhouse,images,bin}/                     # offline deps
├── .stack/{rustfs,postgres,dagster,otel}/              # pinned service configs
├── src/alpha_lake/
│   ├── models/                                         # pure core
│   ├── connectors/ raw/ normalize/ quality/ canonical/ # ingest path
│   ├── security_master/ corp_actions/ derived/         # facts
│   ├── catalog/ storage/ serving/ replay/ fixtures/
│   ├── flows/                                           # pipeline logic (truth)
│   ├── obs.py  config.py  cli.py                        # OTel · settings · Typer
│   └── assets.py                                        # Dagster (thin over flows)
└── tests/{unit,integration,contract,replay,boundary}/
```

## 25. CI, contracts, versioning

**Dataset contracts:** `contracts/<name>.vN.yaml` — PK, partition key, required/nullable fields, point-in-time columns, freshness SLA, allowed quality statuses, backward-compat rules. CI validates live data against the contract. Phase 1 ships `contracts/bars.v1.yaml` plus the contract schema.

**Configuration schema:** config loading uses Pydantic Settings models and validates `[source_datasets.<dataset>.<source>]` nesting at boot.

**Required checks:** ruff · ty · unit · connector-contract (recorded fixtures) · golden replay (raw→canonical hash) · bitemporal-visibility · property-based temporal invariants · adjusted-price leakage · `security_id` resolution · idempotency/duplicate · fixture-hash stability · `import-linter` boundary (incl. no-strategy rule).

**SemVer ↔ schema:** a breaking schema major forces a package major; consumers pin a range. **Distribution (air-gapped):** publish wheels to an internal index/mirror or vendor a pinned wheel; `uv build` yields a self-contained wheel.

---

# Part III — Governance

## 26. System invariants

- **I1** Raw payloads, manifests, fixtures are immutable.
- **I2** Every canonical row carries lineage + maps to a DuckLake snapshot.
- **I3** No strategy/decision semantics anywhere (no scores, ranks, flags).
- **I4** Corrections are new `available_at` versions, never overwrites.
- **I5** No research read returns `available_at > as_of`; valid-time filtering follows the dataset class, so historical observations exclude future effective dates while known-future events may expose future event dates already knowable at `as_of`.
- **I6** Adjusted views apply only corp actions known at `as_of`.
- **I7** Replay is deterministic; uses recorded `available_at`, never wall-clock.
- **I8** Canonical keyed by `security_id`; `symbol` resolved point-in-time.
- **I9** Raw `content_hash` proves archive integrity; canonical `version_hash` drives semantic idempotency and restatement identity.
- **I10** A reconciliation disagreement never halts a valid primary.
- **I11** Quarantined rows retain full raw-archive traceability.
- **I12** Serving exposes no "latest" default to research callers.
- **I13** The repo runs end-to-end offline from vendored dependencies.
- **I14** The reference runtime is stack-first Compose; embedded mode is only for tests, debugging, fixture generation, and golden replay.
- **I15** Dates are exchange-session dates resolved via the pinned trading calendar; all instants are stored UTC.

## 27. ADR log

`docs/adr/README.md` is the single source of truth for ADR numbering, titles, and statuses. This design document links to ADRs by section where relevant but does not maintain a second numbered ADR table.

## 28. Build plan (from scratch, stack-first, vertical-slice, oracle-gated)

Each phase ships only when the golden replay hash is stable and boundary tests are green. The hardest integration risks — DuckLake + Postgres catalog + S3/RustFS object storage + app-container execution — are exercised immediately.

- **Phase 0 — stack skeleton.** Compose stack with Postgres catalog, RustFS object store, Alpha-Lake app container, config loading, DuckLake attach, `models/`, import-linter, OTel collector, `just up/down/health`. No dataset work is accepted until the real stack can boot and pass a health check.
- **Phase 1 — bars vertical slice against the real stack.** Connector fetch → raw archive on RustFS → Polars parse → Patito `BarFact` → SCD2 bitemporal write to DuckLake/Postgres catalog → PIT reader. Prove restatement (§11), leakage (§12), idempotency, and visibility tests. This single slice exercises every hard part.
- **Phase 2 — embedded replay harness.** Add SQLite/local-FS only for pytest, fixture generation, golden replay, and debugging. This harness must prove equivalence with the stack path for frozen fixtures, but it must not become a separate runtime architecture.
- **Phase 3 — identity & actions.** security master (§10) + corporate actions + adjusted views (bars adjustment depends on them), still running through the reference stack.
- **Phase 4 — remaining datasets.** fundamentals → insider → news_articles + social_posts → entity_mentions + sentiment_annotations + attention_metrics → earnings_calendar, each repeating the Phase-1 vertical pattern.
- **Phase 5 — serving surface.** as-of panel / spine join; catalog; health; explicit `latest_*` non-research paths; technical indicator library serving (§14); text analytics serving (§15).
- **Phase 6 — orchestration hardening.** Add Dagster assets over the already-proven `flows/`; asset checks wrap Patito gates; date partitions improve backfill UX. Dagster is not allowed to own business logic.
- **Phase 7 — packaging and air-gap.** Digest-pinned images, `vendor/images`, `vendor/wheelhouse`, optional `vendor/bin/rustfs`, offline `just up --offline`, fixture bundles, and reproducibility docs.
- **Phase 8 — hardening.** dataset contracts + schema versioning; SQLMesh derived layer; Arrow Flight/ADBC serving; Kubernetes deployment target; RustFS clustering only when GA and genuinely needed.

## 29. Tech stack

| Concern | Choice |
|---|---|
| Language / packaging | Python ≥3.12 · uv (lockfile + offline wheelhouse); development currently targets 3.14 |
| Reference runtime | Docker Compose / Podman Compose, driven by `just` |
| Lakehouse | DuckLake 1.0 (Parquet + SQL catalog) |
| Catalog DB | PostgreSQL reference path; SQLite embedded harness only |
| Object store | RustFS S3-compatible reference path; local FS embedded harness only |
| Engine | DuckDB |
| Ingestion | httpx + tenacity (per-source connector registry + synthetic fallback) |
| Dataframes + models + validation | Polars + Patito |
| Transform | DuckDB SQL ▸ SQLMesh |
| Orchestration | Typer CLI in app container first; Dagster optional over `flows/` |
| Observability | OpenTelemetry (OTLP collector in stack; console in embedded harness) |
| Remote serving | Arrow Flight SQL / ADBC (deferred) |
| Lint/format · types · tests · boundaries | ruff · ty · pytest · import-linter |
| Raw archive blob store | `s3fs` (S3) / `pathlib.Path` (local) via BlobStore ABC |

One dataframe lib (Polars), one SQL engine (DuckDB) — never both for the same job; they share Arrow. All dependencies open-source; no managed service required. Kubernetes remains a later deployment target, not a v0.1 design dependency.

## 30. Non-goals (v1)

Strategy logic; materialized features; intraday/streaming; distributed compute; hosted multi-tenant service; ML online feature store; governance UI; Kubernetes platformization; RustFS clustering. Design the seams (object storage, Postgres catalog, Flight serving, Dagster/SQLMesh, Kubernetes deployment, clustering); do not build the distributed platform in v1.

## 31. Summary

```mermaid
flowchart LR
  A[fetch · connector] --> B[archive raw] --> C[parse · Polars] --> D[validate · Patito]
  D --> E[reconcile] --> F[(canonicalize · DuckLake · bitemporal)] --> G[serve · DuckDB/Arrow · PIT]
```

The lake owns bitemporal, source-aware, replayable facts. Consumers own interpretation. It installs nothing it doesn't carry, and it runs stack-first in its own self-contained Compose space. The embedded path exists only to make tests, fixtures, and golden replay fast and deterministic.
