# Alpha-Lake

Stack-first bitemporal market-data lakehouse. Ingests, archives, validates, and serves point-in-time-correct market facts.

> **Owns facts. Serves what was knowable as of a date. Knows nothing about strategy.**

## Quick start

```bash
just up        # start the reference stack (Postgres + RustFS + app)
just bootstrap # initialize the catalog
just ingest    # ingest market data
just health    # check dataset freshness and status
```

## Design

See [docs/DESIGN.md](docs/DESIGN.md) for the full systems design and implementation reference.

## Principles

- **Raw is immutable** — every payload archived verbatim before parsing
- **Point-in-time correctness** — no consumer sees future data
- **Tri-temporal** — valid time, knowledge time, system time tracked independently
- **Facts, not opinions** — neutral transforms only; strategy belongs to consumers
- **Stack-first** — Compose reference runtime from day one; embedded only for tests/replay

## License

Apache 2.0
