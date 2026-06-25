# Promotion Gates

Checklist for promoting a dataset from ``experimental`` to ``convenience``
(or ``convenience`` to ``core``).

## Requirements

Every promotion requires a dedicated PR with documented evidence of all
three requirements below.

### 1. Revision / PIT Replay Proof

- [ ] Golden replay test covering at least one revision scenario.
- [ ] Test proves that an old ``as_of`` returns the correct historical view.
- [ ] Test proves that a later ``as_of`` picks up revised data.

### 2. Freshness SLA Evidence

- [ ] The dataset meets its ``[quality.<dataset>].max_staleness_days``.
- [ ] A freshness check (``SELECT MAX(effective_date) FROM <table>`` against
  production data) shows the gap is within SLA.

### 3. Contract at Appropriate Version

- [ ] ``contracts/<dataset>.vN.yaml`` exists with version >= 1.
- [ ] Required fields, PIT columns, and lineage columns are documented.
- [ ] Quality status values are documented.

## Candidate Datasets

### macro_series → core

- [ ] Revision-replay test (ingest two vintages of one series)
- [ ] 45-day freshness SLA check
- [ ] Contract at v1

### economic_calendar → convenience

- [ ] Known-future PIT test (future event invisible to early as_of)
- [ ] 7-day freshness SLA check
- [ ] Contract at v1

### analyst_estimates → convenience

- [ ] Multi-source precedence failover test (Finnhub empty → FMP)
- [ ] 14-day freshness SLA check
- [ ] Contract at v1

### insider_transactions → convenience

- [ ] PIT-leak test (transaction visible only after its transaction_date)
- [ ] 3-day freshness SLA check
- [ ] Contract at v1

### institutional_holdings → convenience

- [ ] Quarterly snapshots not confused with stale data
- [ ] 30-day freshness SLA check
- [ ] Contract at v1

### top_movers → convenience

- [ ] Daily snapshot correctly deduplicates
- [ ] 1-day freshness SLA check
- [ ] Contract at v1

## Procedure

1. Open a PR titled ``promotion: <dataset> → <target-tier>``.
2. Add the checklist above to the PR description, tick the completed items.
3. Attach evidence (test output, query results) in the PR.
4. Update ``config/stack.toml``:
   - Set ``enabled = true``
   - Set ``supported = true``
   - Set ``tier`` to the target tier
5. Update the dataset contract if needed.
6. Request review.
7. Merge and verify in production.
