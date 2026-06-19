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
