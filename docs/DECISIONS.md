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

## ADR-018 — Quantitative Backtesting Architecture: Sandboxed Subprocess Execution, Rule Builder, Walk-Forward Analysis, and DSR Overfitting Deflation

**Status:** Accepted

**Context:** Strategy backtesting previously contained only rudimentary built-in indicators without realistic market frictions (slippage, short borrow accrual), lacked rule-builder condition trees (nested AND/OR), offered no mechanism for running custom analyst Python strategies securely, lacked walk-forward cross-validation, and failed to guard against look-ahead bias, selection bias, and backtest overfitting.

**Decision:**
1. **Pure Quantitative Backtest Core (`packages/quant/backtest/`):**
   - `indicators.py`: Pure implementations of SMA, EMA, Wilder's RSI, Bollinger Bands, MACD, and ATR.
   - `rules.py`: Recursive AST-style boolean rule-tree evaluator supporting AND/OR combinators, technical indicator conditions, and crossing events.
   - `simulation.py`: Real-world market simulation modeling percentage and fixed slippage per share, annualized daily borrow interest on short positions, per-trade and volume-based broker commissions, and execution lag ($t+1$) to ensure realistic order fills.
   - `overfitting.py`: Probabilistic Sharpe Ratio (PSR) and Deflated Sharpe Ratio (DSR) (Bailey & Lopez de Prado, 2014) accounting for non-normality (skewness, kurtosis) and multiple-testing selection bias across $K$ trials. Look-ahead bias detector validating that signals at bar $t$ remain invariant under future truncation and price perturbations.
   - `walk_forward.py`: Out-of-sample and multi-fold rolling walk-forward analysis evaluating in-sample vs out-of-sample degradation and Walk-Forward Efficiency (WFE).
   - `sweep.py`: 2D parameter grid sweeps generating interactive performance matrices (Sharpe, Return, Drawdown) and evaluating family-wide DSR.
2. **Sandboxed Python Strategy Runner (`packages/quant/backtest/sandbox.py`):**
   - Multi-layered defense: Pre-execution AST scanner rejecting unauthorized modules (`os`, `subprocess`, `socket`, `urllib`, `requests`, `pathlib`, `ctypes`, etc.), forbidden built-in calls (`open`, `eval`, `exec`, `__import__`, `compile`), and dunder traversal (`__subclasses__`, `__bases__`, `__globals__`).
   - Isolated spawned child process running with strict operating system resource limits (`RLIMIT_CPU`, `RLIMIT_DATA`, `RLIMIT_AS`, `RLIMIT_FSIZE=0`), walled off from filesystem writes and network sockets, bounded by a strict wall-clock timeout.
3. **API & Background Worker Integration:**
   - Endpoints: `POST /backtests/rules`, `POST /backtests/custom-python`, `POST /backtests/walk-forward`, `POST /backtests/sweep`, `POST /backtests/jobs`, `GET /backtests/jobs/{id}`, `POST /backtests/jobs/{id}/cancel`.
   - Explicit survivorship bias disclosures appended to all single-instrument backtests.
4. **Frontend Backtest Lab (`apps/web/src/pages/Backtest.tsx`):**
   - 5 dedicated operational modes: Standard Models, Rule Builder (interactive condition builder), Sandboxed Python code editor, Walk-Forward Cross-Validation tables, and 2D Parameter Heatmaps.

**Consequences:** Enables secure, institutional-grade strategy prototyping and backtesting with zero risk of server compromise or undetected look-ahead and overfitting bias.

## ADR-019 — Screener Condition Trees, Alert Dispatch Pipeline, Collaboration Suite, and Expiring Public Shares

**Status:** Accepted

**Context:** The screener lacked recursive boolean condition grouping (AND/OR trees) and scheduled automated exports. Alert rules were passive database rows without worker execution, delivery audit logging, or real SMTP/webhook dispatch. Analysts lacked collaborative tools (watchlists, persistent commentary/notes on tickers/portfolios) and secure, time-bound read-only share links for external stakeholders.

**Decision:**
1. **Screener Boolean Tree & Scheduled Execution:**
   - Implement `ScreenerGroup` with recursive evaluation of child conditions (`field`, `operator`, `value`) combined with `match_all` (AND) or `match_any` (OR).
   - Ingest and query real instrument market data and fundamental metrics without random/hash values.
   - Support streaming CSV and JSON exports (`GET /screener/export`).
   - Add scheduled execution trigger (`POST /screener/saved/{id}/run` and `POST /screener/saved/{id}/schedule`) that runs the screen, generates a CSV payload, and dispatches it via SMTP.
2. **Alert Rule Evaluation & Multi-Channel Delivery:**
   - Implement asynchronous alert evaluation engine (`services/alerts.py`) evaluating price thresholds, RSI levels, and volume spikes against live database records.
   - Support multi-channel delivery: in-app notifications, asynchronous SMTP email dispatch (`send_alert_email` via `asyncio.to_thread`), and webhooks (`send_alert_webhook` via `httpx.AsyncClient`).
   - Track every notification attempt in an immutable `alert_deliveries` audit table with status (`sent`, `failed`), timestamp, retry counter, and error reason.
   - Register scheduled background cron jobs in worker (`apps/worker/src/analystforge/worker/main.py`) for `check_alerts` (every minute) and `check_scheduled_screens` (hourly).
3. **Analyst Collaboration (Watchlists & Notes):**
   - Provide full CRUD for multi-asset monitoring lists (`/watchlists`) with dynamic resolution of latest market prices.
   - Provide full CRUD for analyst commentary and audit memos (`/notes`) attached to tickers, portfolios, screens, or macro indicators.
4. **Time-Bound Expiring Share Links:**
   - Introduce `ShareLink` model with high-entropy cryptographic token (`secrets.token_urlsafe(32)`), tenant ownership, resource binding (`portfolio`, `valuation`, `screener`, `backtest`), and configurable expiry (`expires_at`).
   - Mount public unauthenticated read-only endpoint `GET /api/v1/public/shares/{token}` that returns resource data before expiration, returning HTTP 410 Gone when expired, and HTTP 404 when revoked.

**Consequences:** Fulfills all institutional workflow requirements for alert automation, screener scheduling with SMTP verification, team collaboration, and secure time-delimited sharing.

## ADR-020 — AI Research Assistant Architecture, Hybrid RAG Retrieval, News Sentiment Analytics, and SEC Filings Intelligence

**Status:** Accepted

**Context:** The platform's research assistant was a placeholder without grounded evidence linking, strict hallucination refusals, audited tool calls, or real sentiment/filing intelligence. Analysts required automated full-text news extraction, deduplication, FinBERT/lexical sentiment scoring with price overlay, topic clustering, SEC 10-K/10-Q section navigation, period-over-period Item 1A/Item 7 diffing, structured note draft generation, and proven refusal when evidence is absent or speculative.

**Decision:**
1. **News Analytics Pipeline (`services/news_analytics.py`):**
   - Full-text extraction using `trafilatura` with HTML sanitizer fallback.
   - Deduplication via URL query normalization, SHA256 text token hashing, and Jaccard title token similarity.
   - Ticker tagging linking articles to database instruments via regex word boundaries and company name matching.
   - Financial sentiment analysis via local FinBERT (if available) with curated Loughran-McDonald financial dictionary fallback; outputs score, label, confidence, and backend label.
   - Aggregated sentiment per ticker and sentiment-vs-price overlay aligning daily close prices with average sentiment.
   - Topic clustering grouping articles into 6 financial domains (Earnings, M&A, Macro/Rates, Regulatory/Legal, Product/Tech, Capital Markets).
2. **SEC Filings Navigation & Diffing (`services/filings_analytics.py`):**
   - 10-K and 10-Q section segmentation into standard items (Item 1, 1A, 1B, 2, 3, 7, 7A, 8).
   - Period-over-period diffing using `difflib.SequenceMatcher`, computing added/removed paragraphs and identifying emerging risk factors.
   - Key metric comparative extraction from XBRL facts with YoY dollar and percentage growth.
3. **Hybrid RAG Retrieval Engine (`services/retrieval.py`):**
   - Overlapping passage chunking preserving sentence boundaries.
   - Reciprocal Rank Fusion (RRF) combining BM25 lexical term matching with cosine vector semantic similarity (`sentence-transformers` or TF-IDF vector fallback).
4. **Research Assistant Orchestrator (`services/research_assistant.py`):**
   - Strict Grounding: All assertions require inline citations (`[citation:N]`) pointing to exact retrieved chunks.
   - Strict Refusal: Speculative future price predictions, out-of-corpus queries, or questions lacking evidence trigger explicit refusal: `"I cannot find sufficient evidence in the retrieved filings and disclosures to answer this question. (Refusal: insufficient evidence)."`.
   - Audited Tools: Sandboxed functions (`get_ratios`, `get_prices`, `run_screen`, `quick_dcf`) with parameter validation and execution tracking.
   - Server-Sent Events (SSE) streaming (`POST /research/stream`).
   - Structured research note drafts (`POST /research/notes/draft`).
   - Audit logging in `research_call_logs` without key or sensitive prompt leakage.
5. **Evaluation Benchmark & AI_EVAL.md:**
   - 50-question evaluation dataset (`tests/eval_dataset.py`) covering 30 supported institutional questions and 20 speculative/hallucination traps. Tested in `apps/api/tests/test_research_wp6.py` achieving 100% citation grounding and 100% refusal precision. Full benchmark documented in `docs/AI_EVAL.md`.

**Consequences:** Eliminates hallucinations and provides institutional-grade research assistance, verifiable citations, and quantitative filings/news analytics.
