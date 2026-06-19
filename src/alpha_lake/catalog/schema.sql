CREATE TABLE IF NOT EXISTS source (
    source_id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    description VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS source_dataset (
    source_id VARCHAR NOT NULL,
    dataset VARCHAR NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    parser_version INT DEFAULT 1,
    PRIMARY KEY (source_id, dataset)
);

CREATE TABLE IF NOT EXISTS ingestion_run (
    run_id VARCHAR PRIMARY KEY,
    source_id VARCHAR NOT NULL,
    dataset VARCHAR NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'pending',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    rows_ingested INT DEFAULT 0,
    error_count INT DEFAULT 0
);

CREATE TABLE IF NOT EXISTS manifest (
    fetch_id VARCHAR PRIMARY KEY,
    source_id VARCHAR NOT NULL,
    endpoint VARCHAR NOT NULL,
    ingest_ts TIMESTAMPTZ NOT NULL,
    http_status INT,
    content_hash VARCHAR NOT NULL,
    content_type VARCHAR,
    byte_size INT,
    parser_version_intended INT
);

CREATE TABLE IF NOT EXISTS security_master (
    security_id VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    name VARCHAR,
    exchange VARCHAR,
    figi VARCHAR,
    cik VARCHAR,
    effective_start DATE NOT NULL,
    effective_end DATE,
    available_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (security_id, symbol, effective_start)
);

CREATE TABLE IF NOT EXISTS reconciliation_event (
    event_id VARCHAR PRIMARY KEY,
    dataset VARCHAR NOT NULL,
    security_id VARCHAR NOT NULL,
    effective_date DATE NOT NULL,
    source_id_primary VARCHAR NOT NULL,
    source_id_secondary VARCHAR NOT NULL,
    field_name VARCHAR NOT NULL,
    value_primary DOUBLE,
    value_secondary DOUBLE,
    diff_pct DOUBLE,
    severity VARCHAR NOT NULL DEFAULT 'warn',
    action VARCHAR NOT NULL DEFAULT 'log',
    sla_hours INT,
    resolution VARCHAR,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS corp_actions (
    security_id VARCHAR NOT NULL,
    effective_date DATE NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    source_id VARCHAR NOT NULL,
    action_type VARCHAR NOT NULL,
    ratio_numerator DOUBLE,
    ratio_denominator DOUBLE,
    dividend_amount DOUBLE,
    dividend_currency VARCHAR,
    source_fetch_id VARCHAR,
    raw_payload_hash VARCHAR,
    ingestion_run_id VARCHAR,
    content_hash VARCHAR,
    version_hash VARCHAR,
    schema_version INT DEFAULT 1,
    parser_version INT DEFAULT 1,
    quality_status VARCHAR DEFAULT 'valid'
);

CREATE TABLE IF NOT EXISTS ingest_outcome (
    outcome_id VARCHAR PRIMARY KEY,
    run_id VARCHAR NOT NULL,
    source_id VARCHAR NOT NULL,
    dataset VARCHAR NOT NULL,
    entity_id VARCHAR NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'ok',
    error_message VARCHAR,
    rows_ingested INT DEFAULT 0,
    occurred_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lake_bars (
    security_id VARCHAR NOT NULL,
    effective_date DATE NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    source_id VARCHAR NOT NULL,
    source_published_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ,
    validated_at TIMESTAMPTZ,
    open DOUBLE NOT NULL,
    high DOUBLE NOT NULL,
    low DOUBLE NOT NULL,
    close DOUBLE NOT NULL,
    volume BIGINT NOT NULL,
    source_fetch_id VARCHAR,
    raw_payload_hash VARCHAR,
    ingestion_run_id VARCHAR,
    content_hash VARCHAR,
    version_hash VARCHAR,
    normalization_version INT DEFAULT 1,
    schema_version INT DEFAULT 1,
    parser_version INT DEFAULT 1,
    quality_status VARCHAR DEFAULT 'valid'
);

-- Dataset tables (Phase 4) --
CREATE TABLE IF NOT EXISTS fundamentals (
    security_id VARCHAR NOT NULL, effective_date DATE NOT NULL,
    available_at TIMESTAMPTZ NOT NULL, source_id VARCHAR NOT NULL,
    fiscal_period VARCHAR NOT NULL, statement_type VARCHAR NOT NULL,
    line_item VARCHAR NOT NULL, value DOUBLE NOT NULL,
    currency VARCHAR DEFAULT 'USD', unit VARCHAR DEFAULT 'raw',
    source_fetch_id VARCHAR, raw_payload_hash VARCHAR, ingestion_run_id VARCHAR,
    content_hash VARCHAR, version_hash VARCHAR,
    schema_version INT DEFAULT 1, parser_version INT DEFAULT 1,
    quality_status VARCHAR DEFAULT 'valid'
);

CREATE TABLE IF NOT EXISTS insider_tx (
    security_id VARCHAR NOT NULL, effective_date DATE NOT NULL,
    available_at TIMESTAMPTZ NOT NULL, source_id VARCHAR NOT NULL,
    filer_cik VARCHAR NOT NULL, issuer_cik VARCHAR NOT NULL,
    transaction_code VARCHAR NOT NULL, shares DOUBLE, price DOUBLE, value DOUBLE,
    source_fetch_id VARCHAR, raw_payload_hash VARCHAR, ingestion_run_id VARCHAR,
    content_hash VARCHAR, version_hash VARCHAR,
    schema_version INT DEFAULT 1, parser_version INT DEFAULT 1,
    quality_status VARCHAR DEFAULT 'valid'
);

CREATE TABLE IF NOT EXISTS earnings_calendar (
    security_id VARCHAR NOT NULL, effective_date DATE NOT NULL,
    available_at TIMESTAMPTZ NOT NULL, source_id VARCHAR NOT NULL,
    report_date DATE NOT NULL, session VARCHAR DEFAULT 'regular',
    source_fetch_id VARCHAR, raw_payload_hash VARCHAR, ingestion_run_id VARCHAR,
    content_hash VARCHAR, version_hash VARCHAR,
    schema_version INT DEFAULT 1, parser_version INT DEFAULT 1,
    quality_status VARCHAR DEFAULT 'valid'
);

CREATE TABLE IF NOT EXISTS news_articles (
    article_id VARCHAR NOT NULL, effective_date DATE NOT NULL,
    available_at TIMESTAMPTZ NOT NULL, source_id VARCHAR NOT NULL,
    title VARCHAR, description VARCHAR, url VARCHAR, text_hash VARCHAR,
    published_at TIMESTAMPTZ, source_name VARCHAR,
    source_fetch_id VARCHAR, raw_payload_hash VARCHAR, ingestion_run_id VARCHAR,
    content_hash VARCHAR, version_hash VARCHAR,
    schema_version INT DEFAULT 1, parser_version INT DEFAULT 1,
    quality_status VARCHAR DEFAULT 'valid'
);

CREATE TABLE IF NOT EXISTS social_posts (
    post_id_hash VARCHAR NOT NULL, effective_date DATE NOT NULL,
    available_at TIMESTAMPTZ NOT NULL, source_id VARCHAR NOT NULL,
    platform VARCHAR, venue VARCHAR, parent_id_hash VARCHAR,
    text_hash VARCHAR, published_at TIMESTAMPTZ, engagement_json VARCHAR,
    source_fetch_id VARCHAR, raw_payload_hash VARCHAR, ingestion_run_id VARCHAR,
    content_hash VARCHAR, version_hash VARCHAR,
    schema_version INT DEFAULT 1, parser_version INT DEFAULT 1,
    quality_status VARCHAR DEFAULT 'valid'
);

CREATE TABLE IF NOT EXISTS entity_mentions (
    mention_id VARCHAR NOT NULL, effective_date DATE NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    text_item_id VARCHAR, text_item_type VARCHAR, security_id VARCHAR,
    entity_name VARCHAR, entity_type VARCHAR, confidence DOUBLE,
    match_method VARCHAR,
    source_fetch_id VARCHAR, raw_payload_hash VARCHAR, ingestion_run_id VARCHAR,
    content_hash VARCHAR, version_hash VARCHAR,
    schema_version INT DEFAULT 1, parser_version INT DEFAULT 1,
    quality_status VARCHAR DEFAULT 'valid'
);

CREATE TABLE IF NOT EXISTS sentiment_annotations (
    annotation_id VARCHAR NOT NULL, effective_date DATE NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    text_item_id VARCHAR, text_item_type VARCHAR,
    sentiment_score DOUBLE, sentiment_label VARCHAR,
    model_version VARCHAR, prompt_version VARCHAR, taxonomy_version VARCHAR,
    input_text_hash VARCHAR, source_dataset_version VARCHAR,
    source_fetch_id VARCHAR, raw_payload_hash VARCHAR, ingestion_run_id VARCHAR,
    content_hash VARCHAR, version_hash VARCHAR,
    schema_version INT DEFAULT 1, parser_version INT DEFAULT 1,
    quality_status VARCHAR DEFAULT 'valid'
);

CREATE TABLE IF NOT EXISTS attention_metrics (
    security_id VARCHAR NOT NULL, effective_date DATE NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    window_start DATE, window_end DATE, window_type VARCHAR,
    article_count INT DEFAULT 0, mention_count INT DEFAULT 0,
    unique_source_count INT DEFAULT 0, unique_author_count INT DEFAULT 0,
    mean_sentiment DOUBLE, sentiment_std DOUBLE,
    positive_share DOUBLE, neutral_share DOUBLE, negative_share DOUBLE,
    velocity_score DOUBLE,
    source_fetch_id VARCHAR, raw_payload_hash VARCHAR, ingestion_run_id VARCHAR,
    content_hash VARCHAR, version_hash VARCHAR,
    schema_version INT DEFAULT 1, parser_version INT DEFAULT 1,
    quality_status VARCHAR DEFAULT 'valid'
);
