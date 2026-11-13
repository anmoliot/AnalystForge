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
- Redis is absent locally; development uses an in-process cache and inline job execution. Queue and
  rate-limit behaviour backed by Redis is covered by unit tests with fakeredis and by CI services.
- Paid provider adapters (Alpha Vantage, Twelve Data, Polygon, FMP, NewsAPI) cannot be verified
  against live endpoints without keys. They are tested against recorded fixtures and are disabled
  unless configured.
- FinBERT / sentence-transformers model weights may not be downloadable in constrained
  environments; the documented lexical fallback is used and labelled in the UI.

## Product scope

- This file is populated further as phases 1–12 are delivered.
