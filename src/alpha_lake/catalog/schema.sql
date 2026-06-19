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
    ingest_ts TIMESTAMP NOT NULL,
    http_status INT,
    content_hash VARCHAR NOT NULL,
    content_type VARCHAR,
    byte_size INT,
    parser_version_intended INT
);
