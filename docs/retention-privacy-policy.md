# News/Social Retention, Privacy & Upstream Terms

**Status:** Accepted
**Last updated:** 2026-06-19

## Retention

| Dataset | Retention | Rationale |
|---------|-----------|-----------|
| Source-grounded text (news_articles, social_posts) | 3 years rolling | Sufficient for research; limits storage cost and liability |
| Derived annotations (entity_mentions, sentiment, attention) | 5 years rolling | Valuable for longitudinal studies; no raw text stored |
| Raw payloads (content-addressed archive) | 1 year rolling | Enough for replay verification; raw text not exposed via readers |
| Canonical rows without text (bars, fundamentals, etc.) | Indefinite (SCD2) | Immutable market facts have no privacy concerns |

## Privacy

- Raw text (`title`, `description`, `text_hash`) is stored only in the raw archive and canonical `news_articles`/`social_posts` tables.
- The `text_hash` is SHA-256 of the raw text, not the text itself. Re-identification requires access to the original source text.
- Derived tables (`entity_mentions`, `sentiment_annotations`, `attention_metrics`) store only entity names, scores, and metadata — never raw text.
- Social `post_id_hash` is SHA-256 of the platform-native post ID, not the user's identifier.
- No PII (personally identifiable information) is intentionally collected or stored.

## Upstream Terms

| Source | Key Restriction |
|--------|----------------|
| Alpha Vantage | API key restricted. Free tier: 25 calls/day, 5 calls/min. Refer to AV terms |
| Reddit API | No commercial use without approval. Rate-limited to 100 requests/min |
| Tiingo News | Attribution required. Rate-limited |
| SEC EDGAR | Public domain. Rate-limiting enforced by SEC |
| EODHD | API key restricted. Refer to EODHD terms of service |
| Alpaca | API key restricted. Non-display use permitted |

## Enforcement

- Retention policy is enforced by scheduled cleanup jobs (not yet implemented — tracked separately).
- Rate limits are configured in `config/stack.toml` per source.
- Privacy constraints are enforced by the data model: derived tables never store raw text.
