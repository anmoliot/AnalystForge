# Architecture decision record

Each entry records the decision, context and consequences. Decisions are immutable; a later ADR
supersedes an earlier one rather than rewriting it.

## ADR-001 — Python 3.12 target, uv workspace packaging

**Status:** Accepted

**Context:** The brief specifies Python 3.12, a monorepo with several installable Python packages
and reproducible builds. The development machine has Python 3.13 and 3.12 available but no Docker.

**Decision:** Target Python 3.12 (`requires-python >=3.12,<3.14`) and use a uv workspace with a
single lockfile. All packages live under the `analystforge` namespace. Docker images pin
`python:3.12-bookworm-slim`; local development uses the 3.12 launcher.

**Consequences:** One `uv sync --all-packages` installs the whole backend, dependency resolution is
checked into `uv.lock`, and CI and Docker share the same install path. Divergence between the
developer's default Python and the target is handled by the launcher and by CI.

## ADR-002 — Arq instead of Celery

**Status:** Accepted

**Context:** Background ingestion, scheduled screens, alerts and report rendering need a queue.
The brief permits Celery or Arq. The codebase is async-first (SQLAlchemy async, httpx), and Celery's
Windows support and sync worker model add friction.

**Decision:** Use Arq with Redis. Job services remain plain async functions so a development
`InlineTaskQueue` can execute them without Redis. Production configuration requires Redis.

**Consequences:** Simpler async-native workers and one dependency model. Celery-specific features
(routing, chords) are unavailable; job orchestration is kept deliberately simple. Every run is
persisted in `job_runs` for status APIs and audit.

## ADR-003 — PostgreSQL 16 + TimescaleDB in deployments; PostgreSQL for tests

**Status:** Accepted

**Context:** Time-series storage benefits from Timescale hypertables and continuous aggregates. The
development machine has PostgreSQL 18 but no TimescaleDB or Docker.

**Decision:** Production and Docker Compose use `timescale/timescaledb:2.17.2-pg16`. The schema and
queries remain compatible with plain PostgreSQL; the Timescale migration is guarded and logs a
warning when the extension is absent. Integration tests run against plain PostgreSQL 16 in CI and
against the local PostgreSQL instance here. SQLite is supported only for isolated unit tests, not
as a production mode.

**Consequences:** No hard vendor lock for correctness; hypertable benefits are available where the
image is used. Timescale-specific features must not leak into quant logic. The local verification
environment differs from Docker in Postgres major version (18 vs 16), which is documented in
KNOWN_LIMITATIONS.

## ADR-004 — Shared reference data is global; user-owned data is tenant-scoped

**Status:** Accepted

**Context:** The brief requires a tenant id on every table. Market prices, filings and macro series
are identical for all tenants; duplicating them per tenant wastes storage, complicates ingestion
and multiplies provider licensing calls.

**Decision:** Treat reference data (`instruments`, `price_bars`, `corporate_actions`, `filings`,
`financial_facts`, `macro_*`, `news_articles`) as a shared, read-mostly dataset with provenance.
Everything a tenant creates or configures carries `tenant_id` with repository-enforced filtering.
Tenant-specific overlays (watchlists, notes, models) reference shared entities by id.

**Consequences:** Efficient ingestion and storage. Any future tenant-specific reference data must
be modelled as an overlay table rather than mutating the shared tables. IDOR tests focus on the
tenant-owned surface.

## ADR-005 — Money is Decimal; statistics are floats

**Status:** Accepted

**Context:** Binary floating point is unsuitable for currency totals and accounting identities;
statistical computations (volatility, regression, optimisation) are naturally floating point.

**Decision:** All accounting/valuation entry points accept `Decimal` and return `Decimal`, with
explicit quantisation at currency boundaries. Risk/statistical functions use `float` arrays and
document that they are statistical estimates, never ledger totals. Conversion happens in one
module with tested rounding (`ROUND_HALF_EVEN` for reporting, `ROUND_HALF_UP` for tax-style
display only where documented).

**Consequences:** Correct currency arithmetic and testable rounding. Quant functions must not mix
types implicitly; mypy and tests enforce the boundary.

## ADR-006 — Provider ports with failover, fixtures and explicit unavailability

**Status:** Accepted

**Context:** Free data sources are unreliable and paid keys are optional. The platform must remain
honest when data is missing.

**Decision:** Define `MarketDataProvider`, `FundamentalsProvider`, `FilingsProvider`, `MacroProvider`,
`NewsProvider`, `FxProvider` protocols in `packages/providers`. Each adapter declares capabilities
and required credentials. A registry selects adapters by configuration and health, retries
transient failures with exponential backoff, and never invents a response. Recorded fixtures test
adapters without network access; adapters requiring keys are enabled only when the key exists.

**Consequences:** Swappable providers and demonstrable failover. Some adapters cannot be verified
live without keys; their fixtures and request tests are part of the suite and this is disclosed.

## ADR-007 — JWT access tokens with rotating refresh cookies

**Status:** Accepted

**Context:** A browser SPA needs stateless access checks but revocable sessions and 2FA.

**Decision:** Short-lived (15 min) signed JWT access tokens; 30-day opaque refresh tokens stored
hashed server-side, rotated on each use, with reuse detection revoking the token family. Cookies are
`httpOnly`, `SameSite=Lax`, `Secure` in production. CSRF protection relies on same-site cookies plus
a double-submit token for state-changing cookie-authenticated routes.

**Consequences:** Revocation and reuse detection work, access checks stay cheap, and tokens are not
readable by JavaScript. Requires careful clock and rotation handling, covered by security tests.

## ADR-008 — Custom UI kit in the shadcn/ui idiom, no CLI dependency

**Status:** Accepted

**Context:** The brief specifies shadcn/ui. The shadcn CLI fetches component code at build time and
assumes a particular setup; the design needs a dense, terminal-like system with a custom palette.

**Decision:** Implement local components (`Button`, `Badge`, `Panel`, dialogs, tables) using the
shadcn composition conventions (Tailwind + CSS variables + Radix primitives where needed) rather
than vendoring generated files. Tokens are CSS variables supporting dark/light themes.

**Consequences:** Full control over density and accessibility, no runtime dependency on a generator.
Components must be maintained in-repo and tested; a future migration to generated shadcn components
would be straightforward because the token structure matches.

## ADR-009 — ReportLab and openpyxl/XlsxWriter for exports

**Status:** Accepted

**Context:** The brief allows WeasyPrint or ReportLab. WeasyPrint requires GTK/Pango native
libraries that are fragile on Windows and add image size. Excel exports must preserve formulas.

**Decision:** Use ReportLab for PDF tear sheets, python-pptx for PowerPoint, XlsxWriter for
formula-bearing Excel exports, and openpyxl for reading/validating workbooks. Templates are code
(Jinja for HTML fragments where useful), not binary artefacts.

**Consequences:** Deterministic, lightweight builds. ReportLab layout is more verbose than HTML/CSS;
the report service isolates layout code and snapshot-tests output dimensions and key text.

## ADR-010 — Local embeddings with a disclosed lexical fallback

**Status:** Accepted

**Context:** The brief specifies sentence-transformers + pgvector. Torch and model weights are large
and may be unavailable in CI or constrained environments.

**Decision:** Define an `EmbeddingProvider` port. When sentence-transformers and the configured
model are available, use it and store vectors in pgvector. Otherwise use a deterministic lexical
retriever (BM25-style scoring over stored chunks) and report the degraded mode in the API/UI. The
assistant never claims semantic retrieval when running lexical.

**Consequences:** The research assistant works offline and in CI; retrieval quality is lower in
fallback mode and clearly labelled. pgvector remains the production path.

## ADR-011 — API error envelope and pagination

**Status:** Accepted

**Context:** Clients (web, SDK, Excel add-in) need a stable contract.

**Decision:** Errors always return
`{"error": {"code", "message", "details?", "request_id"}}`. Lists use cursor pagination
(`limit`, `cursor`, `next_cursor`) except small reference lists. Mutating imports accept an
`Idempotency-Key` header and persist the response hash.

**Consequences:** Predictable client handling and traceable failures. All endpoints must use the
shared helpers; tests assert the envelope for 4xx/5xx.

## ADR-012 — Local verification uses PostgreSQL 18 without Docker

**Status:** Accepted

**Context:** The build environment has no Docker engine or GNU Make, but has Node 22, Python 3.12
and a running PostgreSQL 18 server. Blocking delivery on a Docker install would prevent verification.

**Decision:** Ship Docker Compose as the supported one-command deployment, and verify functionality
natively against PostgreSQL 18 with `uv` and `npm`. Docker images are built in CI. Compose-specific
behaviour (TimescaleDB, Redis, Nginx, container healthchecks) is documented as verified by CI/build
where it cannot be executed locally.

**Consequences:** Real API/database/UI integration is tested locally; container orchestration has
build-level verification plus a documented manual checklist. This is recorded in
KNOWN_LIMITATIONS until a Docker-capable host runs the full path.
