CREATE TABLE IF NOT EXISTS source (
    source_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS source_dataset (
    source_id TEXT NOT NULL,
    dataset TEXT NOT NULL,
    enabled BOOLEAN DEFAULT true,
    parser_version INTEGER DEFAULT 1,
    PRIMARY KEY (source_id, dataset)
);

CREATE TABLE IF NOT EXISTS ingestion_run (
    run_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    dataset TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    rows_ingested INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS manifest (
    fetch_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    ingest_ts TIMESTAMPTZ NOT NULL,
    http_status INTEGER,
    content_hash TEXT NOT NULL,
    content_type TEXT,
    byte_size INTEGER,
    parser_version_intended INTEGER
);

CREATE TABLE IF NOT EXISTS security_master (
    security_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    name TEXT,
    exchange TEXT,
    figi TEXT,
    cik TEXT,
    effective_start DATE NOT NULL,
    effective_end DATE,
    available_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (security_id, symbol, effective_start)
);

CREATE TABLE IF NOT EXISTS reconciliation_event (
    event_id TEXT PRIMARY KEY,
    dataset TEXT NOT NULL,
    security_id TEXT NOT NULL,
    effective_date DATE NOT NULL,
    source_id_primary TEXT NOT NULL,
    source_id_secondary TEXT NOT NULL,
    field_name TEXT NOT NULL,
    value_primary DOUBLE PRECISION,
    value_secondary DOUBLE PRECISION,
    diff_pct DOUBLE PRECISION,
    severity TEXT NOT NULL DEFAULT 'warn',
    action TEXT NOT NULL DEFAULT 'log',
    sla_hours INTEGER,
    resolution TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS ingest_outcome (
    outcome_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    dataset TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ok',
    error_message TEXT,
    rows_ingested INTEGER DEFAULT 0,
    occurred_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);


-- Dataset tables (Phase 4) --







