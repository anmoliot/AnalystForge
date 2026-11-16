# Known limitations

This file is maintained honestly throughout delivery. Items are removed only when verified fixed.

## Environment / verification

- The build host has no Docker Engine, so `docker compose up` and the Nginx/TimescaleDB containers
  could not be executed here. The native equivalent (uv + PostgreSQL 18 + Vite) is verified, and
  container images are built by CI. A full `make up` smoke test remains to be run on a
  Docker-capable host.
- GNU Make is absent on the build host; Makefile targets mirror the commands that were run natively.
- Local verification uses PostgreSQL 18.3; deployments pin PostgreSQL 16 + TimescaleDB. SQL is kept
  compatible with both. Hypertable-specific behaviour is not exercised locally.
- Redis is available locally (`redis-cli ping` returns PONG) and is used for caching and job queues.
  In-process/inline execution is used when Redis is unavailable; Redis-backed rate-limit and queue
  behaviour is covered by unit tests and CI services.
- Paid provider adapters (Alpha Vantage, Twelve Data, Polygon, FMP, NewsAPI) cannot be verified
  against live endpoints without keys. They are tested against recorded fixtures and are disabled
  unless configured.
- FinBERT / sentence-transformers model weights may not be downloadable in constrained
  environments; the documented lexical fallback is used and labelled in the UI.

## Data providers (Phase 1)

- The default price adapter is Yahoo's keyless chart API, which is unofficial. Yahoo's terms
  restrict redistribution and commercial use; a deployment must review them before serving data to
  third parties. Quotes may be delayed.
- Stooq currently answers non-browser clients with a JavaScript/browser challenge, so it cannot be
  used as a live fallback on this host. The failover path is implemented and tested, and the live
  challenge is recorded as a provider error rather than hidden.
- Yahoo's LSE history contains vendor OHLC anomalies: 15 instrument-level findings covering 27 bars,
  all reported as warnings with the raw values retained. `SHEL.L` on 2024-05-01, for example, has an
  open above its high. Verify against a primary source before using those bars in analysis.
- SEC XBRL coverage is limited to companies that file with the SEC and expose companyfacts. Phase 1
  verifies 20 US filers; non-US issuers rely on other fundamentals sources.
- News ingestion stores feed headlines, summaries and links from public RSS feeds. Full article
  bodies and passage-level citation are delivered with the Phase 9 research pipeline, subject to
  publisher terms.
- FRED and ECB data are keyless public sources. FRED series may originate with third parties; check
  each series' notes before redistribution.
- Provider API keys listed in `.env.example` are optional. Paid adapters are implemented against
  recorded fixtures and are enabled only when a key is present; they are not verified live here.

## Product scope

- This file is populated further as phases 2–12 are delivered.
