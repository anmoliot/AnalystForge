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

## ADR-013 — Keyless provider defaults and normalisation on write

**Status:** Accepted

**Context:** Phase 1 must load real prices, fundamentals, macro, FX and news without requiring paid
keys. Candidate free sources differ in reliability, currency conventions and response shape. Stooq
was initially the intended keyless price source but its CSV endpoint now returns a browser
challenge to non-browser clients. Yahoo's chart endpoint remains keyless and returns adjusted bars
for LSE, NASDAQ and XETRA listings, but quotes LSE stocks in pence.

**Decision:** Default to the Yahoo chart API for prices, SEC EDGAR companyfacts/submissions for
fundamentals, FRED CSV for macro, ECB reference rates for FX and public RSS feeds for news. Keep
Stooq as a secondary price adapter and demonstrate failover when the primary errors. Normalise on
write: vendor `GBp`/`GBX` quotes and dividends are multiplied by `0.01` and stored as `GBP`; daily
bars are stored at midnight UTC; missing provider values remain `NULL` rather than zero. All writes
are idempotent upserts on natural keys. Incremental price runs refetch from the latest stored bar
minus seven days to absorb late vendor corrections; `--full` explicitly refetches the configured
history window.

**Consequences:** The platform works out of the box without keys and can prove failover with a
second adapter. Yahoo and Stooq are unofficial and their terms constrain redistribution
(DATA_LICENSING). The seven-day overlap adds a small amount of repeated work but avoids permanent
gaps from late corrections. Currency scaling happens once at ingestion, so analysis and reporting
never mix pence and pounds.

## ADR-014 — Data-quality severity and vendor anomalies

**Status:** Accepted

**Context:** Live vendor data is imperfect. During Phase 1 verification, 27 LSE bars in the Yahoo
payload violated OHLC bounds (for example, the 2024-05-01 SHEL.L bar had `open=2875.0` but
`high=2817.5`). Rewriting or dropping those bars would silently alter source data; treating every
anomaly as fatal would make the honest data set unusable.

**Decision:** Quality checks report structural failures (missing instruments, stale coverage,
missing fundamentals, absent price history) as `error` and cause a `fail` status. Vendor OHLC bound
violations are reported as `warning` with the affected instrument and first day, and the raw bars
are retained unchanged. Warnings never flip the overall status to `fail`; errors do. Every finding
carries a code, severity, message, instrument and optional day so the UI and API can explain it.

**Consequences:** Analysts see exactly which vendor rows are suspect and can verify them against a
primary source. The platform never fabricates a correction or hides an anomaly. A future
provider-specific repair workflow must be explicit and auditable rather than silently normalising
vendor errors.

## ADR-015 — Elimination of synthetic data fallbacks and strict DataUnavailable reporting

**Status:** Accepted

**Context:** Several analytics paths (e.g. portfolio risk, mean-variance optimizer, backtest engine, valuation monte carlo) previously fell back to `np.random.normal` or global seed generation (`np.random.seed(42)`) when market price series or aligned returns were missing. This violated the core mandate against fabricated or random numbers in analysis paths.

**Decision:**
1. Completely remove synthetic and random fallback generators from all analysis and backtesting routers.
2. In `services/valuation.py`, replace global `np.random.seed` with scoped `numpy.random.default_rng(seed)`, accept `seed` as an explicit request parameter, and include it in response metadata.
3. Return HTTP 422 with typed `DataUnavailableError` envelope (`{"error": {"code": "data_unavailable", "message": ..., "details": ...}}`) when price history or inputs are insufficient.
4. Establish repository-wide AST/source test `test_no_random_or_fabricated_data_in_codebase` guarding against unauthorized random calls.

**Consequences:** The analysis engine strictly reports missing data rather than fabricating numbers. The UI displays informative data-unavailable states with missing ticker details.

## ADR-016 — FRED and Groq OpenAI-Compatible LLM Provider Integration

**Status:** Accepted

**Context:** The platform requires macroeconomic data integration (US Treasury yield curve tenors, CPI, unemployment, GDP, policy rates, credit spreads) via FRED, and an intelligent research assistant using high-throughput OpenAI-compatible LLM endpoints (specifically Groq free/paid tiers). The integration must remain resilient against rate limits and dynamic model decommissioning while never leaking credentials.

**Decision:**
1. Upgrade `FredProvider` to read `FRED_API_KEY` from configuration / environment while preserving the public CSV download as an unauthenticated fallback. Macro dashboard endpoints report explicit `"FRED key not configured"` or `"No yield curve data ingested yet"` states with as-of observation timestamps.
2. Introduce `LLMProvider` abstraction with ports for `none`, `openai-compatible` (Groq, OpenAI, vLLM, Ollama), `anthropic`, and `DeterministicFakeLLMProvider` (for deterministic unit/CI testing).
3. Implement `TokenBucket` rate limiter tracking `LLM_REQUESTS_PER_MINUTE` and exponential backoff honoring `429` with `Retry-After` headers, returning clear `"LLM rate limited, retry in N s"` feedback.
4. Implement dynamic model discovery via `GET {base}/models` at startup to verify `LLM_MODEL`, falling back to `LLM_FALLBACK_MODEL` or active chat models, filtering out guardrail/embedding models.
5. Bound retrieved context using `_trim_messages` capped to `LLM_MAX_INPUT_TOKENS`, preserving system directives and recent queries while pruning intermediate retrieved passages.
6. Provide diagnostic self-check endpoint `GET /api/v1/meta/integrations` reporting connectivity and resolved models without exposing keys.
7. Maintain offline CI compatibility using deterministic fake fixtures, while offering marked `pytest -m live` suite for real key verification.

**Consequences:** Seamless Groq and FRED support with zero key exposure, strict rate limit compliance, and zero test breakage across offline CI environments.

## ADR-017 — Portfolio Suite Completeness, Optimization Constraints, and Import Wizard

**Status:** Accepted

**Context:** Portfolio analytics lacked systematic multi-factor regression (Fama-French 3/5 factor), moving-window statistical tracking (rolling volatility, Sharpe, beta, tracking error, information ratio, drawdown), Black-Litterman subjective view incorporation, trade rebalancing with transaction cost and turnover accounting, and robust column-mapping transaction import wizards with downloadable validation reports.

**Decision:**
1. Implement pure quantitative functions under `packages/quant`:
   - `factors.py`: OLS regression for Fama-French multi-factor exposure models with t-statistics, p-values, R², and annualized Jensen's alpha.
   - `rolling.py`: Rolling window analytics for volatility, Sharpe, beta, tracking error, information ratio, and peak-to-trough drawdowns.
   - `rebalance.py`: Rebalance trade list generator computing current vs target shares, cash delta, one-way turnover, and estimated broker commissions.
   - `black_litterman.py`: Implied equilibrium prior returns combined with investor views via pick matrix $P$ and view uncertainty matrix $\Omega$ (using He-Litterman proportional formulation), yielding posterior expected returns and covariance.
   - `optimization.py`: Extend quadratic CLARABEL and SLSQP programs to accept convex L1 turnover caps ($0.5 \|w - w_0\|_1 \le \text{cap}$) and linear sector caps.
2. Build 2-step CSV/Excel import wizard supporting `.csv`, `.xlsx`, and `.xls` with header inspection, preview rows, interactive column mapping, and downloadable CSV validation reports.
3. Expose dedicated API endpoints under `/portfolios/{id}` for `/factors`, `/rolling`, `/rebalance`, `/black-litterman`, `/attribution`, and `/import/preview`.
4. Surface interactive tabs in frontend `Portfolios.tsx` for rebalance order execution, factor exposures, and rolling metrics.

**Consequences:** The platform provides institutional-grade portfolio risk, rebalance execution, and multi-factor analytics while preserving zero-fabricated-data guarantees.
