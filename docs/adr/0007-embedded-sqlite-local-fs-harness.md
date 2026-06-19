# ADR-0007: Embedded SQLite/local-fs harness for testing

**Status:** Accepted

**Context:**
Tests must run quickly and hermetically without Docker or network access. The full Postgres + RustFS stack is too heavy for unit and integration tests.

**Decision:**
Build an embedded test harness that replaces:
- PostgreSQL → SQLite (same schema, dialect-compatible DDL)
- RustFS/S3 → Local filesystem
- OTel collector → Console exporter

The harness is a pytest fixture that sets up and tears down the environment per test session or per test.

**Consequences:**
- Positive: Fast, hermetic tests without Docker
- Positive: Same code paths as production (port abstraction via dependency injection)
- Negative: SQLite dialect differences may mask Postgres-specific issues
- Negative: Not suitable for performance or scale testing

**References:**
- DESIGN.md §2, §21, §28

**Date:** 2026-06-18
