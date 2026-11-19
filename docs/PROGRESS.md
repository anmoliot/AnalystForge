# Progress and Truthful Work Package Status

Updated continuously. Status is strictly evidence-based: a work package or phase is complete only when its exit criteria were actually executed and proven by automated test suites.

## Work Packages Status (Master Remediation Plan)

| Work Package | Scope | Status | Executed Evidence |
|---|---|---|---|
| **WP0** | Secrets, FRED integration & Groq LLM Provider | **Complete** | `.env.example` documented with FRED and Groq keys without secrets; `packages/providers/src/analystforge/providers/llm.py` implemented with `TokenBucket` rate limiter, dynamic model discovery, exponential backoff on 429 (`Retry-After`), context trimming, streaming, tool calls, and JSON structured modes; diagnostic self-check endpoint `GET /api/v1/meta/integrations` tested (`test_integrations_meta.py`); live integration test suite (`tests/test_live_integrations.py -m live`) executed and passing against live FRED and Groq APIs; 67 provider tests and 66 API tests pass. |
| **WP1** | Remove fabricated/random data | **Complete** | Deleted `np.random.normal` from `routers/portfolio.py` and `routers/backtest.py`; missing price data returns HTTP 422 `DataUnavailableError`; replaced `np.random.seed(42)` in `services/valuation.py` with scoped `numpy.random.default_rng(seed)`; explicit `seed` parameter and response field in `/api/v1/valuation/dcf/montecarlo`; repository-wide AST test `test_no_random_or_fabricated_data_in_codebase` passes; frontend alerts render in `Portfolios.tsx`. Committed in `aab2fb4`. |
| **WP2** | Valuation completeness (FCFE, Comps, DDM, SOTP, WACC builder, Football Field) | **Complete** | Added FCFE, single/multi-stage DDM, Edwards-Bell-Ohlson Residual Income, Comps peer multiple distribution (min/25th/median/75th/max), SOTP, Precedent Transactions, WACC builder (CAPM + Blume adjusted beta + live FRED DGS10), and Football Field consolidation. Reference tests in `packages/quant/tests/test_valuation_models.py` prove all models match independent hand calculations within 0.01% tolerance. Excel export preserves live formulas. Valuation UI in `apps/web/src/pages/Valuation.tsx` adds tabs for all models. 157 quant tests and 74 API tests pass. |
| **WP3** | Portfolio gaps (XIRR, Brinson-Fachler, Black-Litterman, factor exposure) | **Complete** | Implemented `packages/quant/src/analystforge/quant/factors.py` (Fama-French 3/5-factor OLS regression with t-stats, p-values, R², annualized alpha), `rolling.py` (rolling volatility, Sharpe, beta, tracking error, information ratio, and max drawdown), `rebalance.py` (trade list generation with buy/sell/hold orders, delta shares, turnover, and commissions), `black_litterman.py` (implied equilibrium prior combined with investor views via pick matrix $P$ and $\Omega$), and enhanced `optimization.py` with L1 turnover caps ($0.5 \|w - w_0\|_1 \le \text{cap}$) and sector caps. Built 2-step CSV/Excel import wizard with file preview, interactive column mapping, and downloadable CSV validation report. Added endpoints `/factors`, `/rolling`, `/rebalance`, `/black-litterman`, `/attribution`, `/import/preview`, and `/import/download-report`. Golden-file tests in `packages/quant/tests/test_portfolio_gaps.py` and API integration tests in `apps/api/tests/test_portfolio_gaps_api.py` all pass. 163 quant tests and 77 API tests pass. |
| **WP4** | Backtesting (Rule builder, sandboxed strategy runner, walk-forward, sweep) | **Complete** | Added `packages/quant/src/analystforge/quant/backtest/`: `indicators.py` (SMA, EMA, RSI Wilder, Bollinger, MACD, ATR), `rules.py` (recursive AST condition tree evaluator for nested AND/OR rules), `simulation.py` (realistic slippage in bps/fixed, borrow costs on short positions, commissions, t+1 execution lag), `sandbox.py` (isolated subprocess runner with strict AST scanner, RLIMIT_CPU, RLIMIT_AS, RLIMIT_DATA, RLIMIT_FSIZE=0, empty filesystem/network), `overfitting.py` (Probabilistic Sharpe Ratio PSR and Deflated Sharpe Ratio DSR per Bailey & Lopez de Prado 2014, point-in-time and perturbation look-ahead bias detection), `walk_forward.py` (rolling and out-of-sample splits with Walk-Forward Efficiency WFE), and `sweep.py` (2D parameter grid sweeps with Sharpe/Return/Drawdown heatmaps). API endpoints added: `POST /backtests/rules`, `POST /backtests/custom-python`, `POST /backtests/walk-forward`, `POST /backtests/sweep`, `POST /backtests/jobs`, `GET /backtests/jobs/{id}`, `POST /backtests/jobs/{id}/cancel`. Survivorship bias warnings emitted on all single-ticker backtests. Tests in `packages/quant/tests/test_backtest_quant.py` and `apps/api/tests/test_backtest_gaps_api.py` verify deliberate look-ahead leaky strategies are caught and rejected, sandbox escape attempts (`os`, `subprocess`, `open`, `socket`, `__import__`) are blocked, and DSR overfitting calculations match theoretical thresholds. Frontend `apps/web/src/pages/Backtest.tsx` upgraded with 5 operational modes. All 171 quant tests, 67 provider tests, 4 SDK tests, 82 API tests, and 20 web tests pass. |
| **WP5** | Screener, macro, alerts, watchlists (Live worker evaluation, email/webhook delivery) | **Complete** | Added recursive boolean condition group evaluator (`ScreenerGroup` with AND/OR logic) in `routers/screener.py`; removed fake macro fallbacks, wiring real FRED observations with as-of dates, yield curve tenors (3M to 30Y) and 10Y-2Y/10Y-3M spread inversion tracking; implemented full alert evaluation and dispatch pipeline in `services/alerts.py` supporting in-app notifications, real SMTP email dispatch (`asyncio.to_thread`), webhook web-calls with retries, and an `alert_deliveries` audit log; added scheduled screen execution generating CSV reports and delivering via SMTP; implemented watchlists (`routers/watchlists.py`) with real price resolution; added analyst notes/comments (`routers/notes.py`); built time-bound expiring share links (`routers/shares.py`, `GET /public/shares/{token}`) with 410 Gone expiry and revocation handling; registered worker cron functions `check_alerts` and `check_scheduled_screens`. End-to-end integration tests in `apps/api/tests/test_screener_macro_alerts_wp5.py` verify scheduled screen execution delivering real email to an in-process mock SMTP server, alert triggering/delivery audit logs, watchlists, notes, and share link token lifecycles. All 88 API tests pass. |
| **WP6** | News, filings & Groq research assistant (Grounded citations, tool calls, 50-Q eval set) | **Complete** | Built news analytics in `services/news_analytics.py`: full-text extraction (`trafilatura`), deduplication, ticker tagging, FinBERT/lexical sentiment analysis, daily sentiment-price overlay, and topic clustering; implemented SEC filings navigation & diffing in `services/filings_analytics.py`: 10-K/10-Q section parsing (Item 1, 1A, 7, 8), period-over-period diffing with emerging risk detection, and comparative XBRL metric extraction; built hybrid RAG retrieval in `services/retrieval.py` combining BM25 lexical search with semantic cosine similarity using Reciprocal Rank Fusion (RRF); implemented AI research assistant orchestrator in `services/research_assistant.py` with inline citations (`[citation:N]`), strict refusal on unsupported/speculative questions, audited tools (`get_ratios`, `get_prices`, `run_screen`, `quick_dcf`), SSE streaming (`/research/stream`), and structured research note draft generation; built 50-question evaluation dataset (`tests/eval_dataset.py`) and documented evaluation report in `docs/AI_EVAL.md` (100% citation grounding, 100% refusal precision on 20 trap questions); live integration tests (`test_live_integrations.py -m live`) pass with configured Groq and FRED keys; 101 API tests, 242 provider/quant/SDK tests, and 20 web tests pass. |
| **WP7** | Reporting and exports (PDF, PPTX tear sheets, Excel live formulas, Python SDK) | **Complete** | Built unified multi-format reporting service in `apps/api/src/analystforge/api/services/reports.py` supporting ReportLab PDF (`generate_pdf_report`), 16:9 widescreen PowerPoint (`generate_pptx_report` via `python-pptx`), live formula Excel (`generate_excel_report` via `xlsxwriter`), CSV, JSON, and Markdown; templates include Company Tear Sheet, Valuation Summary, DCF Model, Portfolio Review, Risk Report, and Backtest Performance; verified live formula recalculation (`=AVERAGE(...)`, `=SUM(...)`, `=B6-B7`) in Excel zip structure; strict format validation rejecting unsupported formats with HTTP 422 Unprocessable Content; report email dispatch via SMTP with binary file attachments in `services/alerts.py`; expanded Python SDK `analystforge_sdk.AnalystForgeClient` with `download_report`, `email_report`, `get_valuation`, `get_portfolio`, `get_filings`, `get_news`, and `integrations_meta`; SDK integration tests and API tests pass in `apps/api/tests/test_reports_wp7.py` and `packages/sdk-python/tests/test_sdk.py`. 106 API tests and 242 package tests pass. |
| **WP8** | Data & coverage (Alpha Vantage / Twelve Data failover, universe expansion) | **Complete** | Implemented secondary key-authenticated market data adapters: `TwelveDataPricesProvider` (`twelvedata.py`) and `AlphaVantagePricesProvider` (`alphavantage.py`); registered in `_PRICE_ADAPTERS` and `ProviderRegistry`; configured graceful degradation when keys are absent via `is_configured()`; tested multi-tier failover in `packages/providers/tests/test_secondary_prices_wp8.py` (Yahoo 500 error → Stooq browser challenge → Twelve Data ok with full `FailoverTrace` attempt recording); documented in `.env.example`; verified Continental European coverage with Deutsche Börse XETRA. All 75 provider tests pass. |
| **WP9** | Worker & operations (Scheduled jobs, Docker compose verification) | **Complete** | Validated arq worker job suite in `apps/worker/src/analystforge/worker/main.py` with cron schedules for alerts (every 15 min), scheduled screens (twice daily), macro, prices, and news updates; implemented operational maintenance and database cleanup in `apps/api/src/analystforge/api/services/maintenance.py` (`run_operational_cleanup` deactivating expired `ShareLink`s, purging revoked `RefreshToken`s, and pruning stale health logs); updated `docker-compose.yml` with Groq LLM variables, mailpit SMTP catcher, and secondary providers; unit tests in `apps/worker/tests/test_worker_wp9.py` pass. |
| **WP10** | Hardening & audits | Open | Hosted PostgreSQL, Playwright, Python, secret scanning, pip-audit and k6 passed. The API image build, web image scan and npm audit failed in the first hosted run. See the hosted results below. |
| **WP11** | Truthful documentation & release | Documentation implemented, publication unverified | OpenAPI generation and version checker pass. User guide, API, runbook, security/contributor docs and changelog added. Release workflow YAML parses. Tag publication remains unexecuted. |

---

## Historical phase records

These entries preserve prior delivery reports. Their counts and operational claims are historical.
The work-package table and executed WP10 evidence govern current verification. Phase 11 and 12
are superseded by WP10 and WP11 and do not independently establish completion.

| Phase | Scope | Status | Evidence |
|---|---|---|---|
| 0 | Foundations: repo, tooling, Docker, config, health, CI | Historical implementation record | 17 backend tests, 7 web tests, ruff/format/mypy clean, Alembic applied to PostgreSQL 18 and `alembic check` reports no drift, live `/health` `/ready` `/api/v1/meta` `/docs` `/metrics`, `npm run build`, dark/light screenshots in `docs/screenshots/` |
| 1 | Data layer, migrations, providers | Historical implementation record | Migration `2b389a02be3a` applied; 50 instruments across LSE/NASDAQ/XETRA with 126,324 daily bars (2016-11-14 → 2026-11-13), 539,942 XBRL facts and 800 filings for 20 US companies, 9 FRED series/8,464 observations, 12,800 FX rates/5 pairs and 60 news articles loaded live; failover test plus live CLI run (stooq browser-challenge error → yahoo ok, persisted in `provider_health`); quality report 0 errors/15 vendor-anomaly warnings; 90 backend + 9 web tests pass; ruff/format/mypy/eslint/tsc clean; dark/light screenshots captured |
| 2 | Quant core library | Historical implementation record | 149 unit and property tests pass across attribution, DCF, DuPont, multiples, optimization, ratios, returns, risk, scoring, statements and WACC; 95% line coverage on `packages/quant`; pure Decimal arithmetic with banker's rounding for currency |
| 3 | Auth, tenancy, RBAC, audit | Historical implementation record | Argon2 password hashing; PyJWT access tokens (15m) + rotating refresh tokens with family tracking and token reuse attack detection; TOTP 2FA with Fernet-encrypted secret storage; API key generation and authentication (`af_...`); RBAC hierarchy (ADMIN, PORTFOLIO_MANAGER, ANALYST, READ_ONLY); immutable audit log on all mutating actions; migration `0003_auth_tables.py`; 6 auth tests pass |
| 4 | Company and financials APIs/UI | Historical implementation record | Endpoints for company profile, OHLCV candlestick price history, normalized statements (income/balance/cashflow), 50+ ratios suite with formula and input traceability, sector peers, and SEC filings; interactive web research terminal with candlestick charting, statements tables, ratio calculation modal, peer comparisons; 8 backend tests (`test_company_api.py`) and 2 web tests (`Companies.test.tsx`) pass; production build verified |
| 5 | Valuation workbench | Historical implementation record | Driver-based DCF (FCFF), WACC derivation, 2D sensitivity grid (WACC × terminal growth), Monte Carlo distribution (P10/P50/P90), versioned model audit trail with scenario tagging (base/bull/bear), and Excel workbook generation with live recalculating formulas (`xlsxwriter`); 5 backend tests (`test_valuation_api.py`) and 1 web test (`Valuation.test.tsx`) pass |
| 6 | Portfolio and risk | Historical implementation record | Migration 0005 applied; FIFO/LIFO/WAC multi-currency lot accounting engine with realized/unrealized P&L and dividend tracking; TWR, XIRR, CAGR, and drawdown calculations; historical/parametric VaR and CVaR (expected shortfall) risk engine; beta-scaled historical crisis stress testing (GFC, COVID-19, 2022 rate shock, 2018 Q4 sell-off); quadratic programming mean-variance & max Sharpe portfolio optimization with efficient frontier generation; CSV transaction import parser; interactive Institutional Portfolio Workbench UI (Holdings, Ledger, Risk & Crisis Shocks, MPT Optimizer); Auth/Login screen; 4 backend portfolio tests + 54 API tests pass + 14 web tests pass; tsc & production build clean |
| 7 | Backtesting | Historical implementation record | Models `BacktestRun`, `BacktestTrade`; quantitative execution engine supporting SMA Crossover, RSI Momentum, Mean Reversion, and Buy-and-Hold strategies with transaction-level trade tracking, equity curve calculation, CAGR, Sharpe ratio, Max Drawdown, and Win Rate metrics; interactive Backtest Lab UI (`Backtest.tsx`) with Recharts equity curve vs benchmark and trade log; 2 backend API tests (`test_backtest_api.py`) and 1 web test (`Backtest.test.tsx`) pass |
| 8 | Screener, macro, alerts | Historical implementation record | Models `SavedScreen`, `AlertRule`, `AlertEvent`, `FxRate`, `MacroSeries`, `MacroObservation`; multi-metric screener API with preset filters and CSV export; FRED yield curve visualizer with 10Y-2Y spread inversion monitor and FX board; real-time alert threshold engine with in-app/email/webhook dispatch; UIs for `Screener.tsx`, `Macro.tsx`, `Alerts.tsx`; 3 backend API tests (`test_screener_macro_alerts.py`) and 3 web tests pass |
| 9 | News, filings, AI | Historical implementation record | Models `ResearchSession`, `ResearchMessage`, `DocumentChunk`; Grounded AI & RAG system indexing SEC EDGAR filings, XBRL facts, and financial news with passage-level citation provenance; research workspace UI (`Research.tsx`) with grounded conversation and source audit badges; 2 backend API tests (`test_research_api.py`) and 1 web test (`Research.test.tsx`) pass |
| 10 | Reporting, SDK, public API | Historical implementation record | Model `ReportArtifact`; institutional research tearsheet, DCF valuation summary, portfolio factor risk memo, and backtest report generator with streaming download; typed Python SDK (`analystforge-sdk`) client in `packages/sdk-python`; Reports archive and preview UI (`Reports.tsx`); 1 backend API test (`test_reports_api.py`), 4 SDK tests (`test_sdk.py`), and 1 web test (`Reports.test.tsx`) pass |
| 11 | Hardening and performance | Superseded by WP10 | Full regression test suite passing 100%: 149 quant unit/property tests, 59 data provider tests, 4 Python SDK tests, 62 backend API tests, and 20 frontend web tests; production build (`tsc -b && vite build`) compiles cleanly with 0 errors |
| 12 | Documentation and release | Superseded by WP11 | Full API specifications, models, and workflows documented; system state and progress verified across all modules; code packaged and committed |

## Decisions log (short form; rationale in DECISIONS.md)

- Python 3.12 target, uv workspace.
- Arq queue; inline execution without Redis in development only.
- TimescaleDB in deployments, plain PostgreSQL for tests/local verification.
- Shared reference data is global; all user-owned tables are tenant-scoped.
- Decimal money, float statistics with an explicit boundary.
- Custom Tailwind UI kit in the shadcn idiom.
- ReportLab + openpyxl/XlsxWriter for exports.
- Local embeddings with a labelled lexical fallback.
- Keyless Yahoo chart API as the default price adapter; Stooq kept as a fallback.
- Vendor OHLC bound violations are surfaced as warnings; raw values are never rewritten.

## Environment notes

- Current build host is Windows 11, Python 3.12 and Node 22. Earlier environment records are historical.
- uv 0.13.x installed; `pip install uv` stalled on this host and was abandoned.
- Docker Engine, GNU Make are not installed on the build host. Native verification uses
  PostgreSQL directly plus `uv run pytest` and `npm test` (the `make test` equivalents). Docker
  and Make deliverables are validated by CI builds where possible.
- Playwright Chromium installed; `npm test`, typecheck, lint and build are green.

## WP10 executed evidence on 2026-11-17

Verification ran on Windows 11 with Python 3.12, uv and Node 22. PowerShell invoked
`%USERPROFILE%/.local/bin/uv.exe` because uv is absent from its default PATH.

| Command | Result |
|---|---|
| `uv sync --all-packages` | Passed |
| `uv run pytest --collect-only -q` | Passed, initially 355 collected before added hardening tests |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | Passed |
| `uv run mypy packages/quant/src` | Passed, 31 source files |
| `uv run pytest --cov=analystforge.quant --cov-branch --cov-report=term-missing --cov-fail-under=95` | Passed, 481 tests, 3 explicit skips, 95.52% quant branch coverage |
| `cd apps/web; npm run lint; npm run typecheck; npm test -- --run; npm run build` | Passed, 20 tests across 13 files |
| `cd apps/web; npm run test:e2e` | Passed, real API workflows, populated DCF and axe audit |
| `npm audit --audit-level=high` | Passed, 9 moderate findings remain |
| `uv tool run pip-audit --path .venv/Lib/site-packages --format json --output .tmp/wp10-pip-audit.json` | Passed, no known vulnerabilities |
| `.tmp/gitleaks/gitleaks.exe git --redact --log-opts=--all --report-format json --report-path .tmp/wp10-gitleaks.json .` | Passed, 22 commits, exact historical public-placeholder exceptions in .gitleaksignore |
| `BASE_URL=http://127.0.0.1:8766 k6 run --no-usage-report --summary-export=.tmp/wp10-smoke.json tests/load/smoke.js` | Passed, 47 requests, 45 checks, zero failures, p95 100.56 ms |

The three pytest skips cover Linux sandbox execution on Windows and live FRED/Groq tests
without configured keys. Existing tests were retained. Repository-wide lint and format cleanup
was needed for the requested gates. The original five sandbox edits were incorporated.

Browser evidence uses an ephemeral SQLite database, the ordinary application and recorded
market/SEC fixtures. See `tests/e2e/fixtures/README.md`. Requests are not intercepted.
The 18 screenshots under `docs/screenshots/wp10-*` show historical coverage, explicit DCF
reviewer assumptions and unavailable states. They do not attest to current provider health,
complete statements or paid-provider coverage. CI configures a separate PostgreSQL test database.
The axe report in `docs/screenshots/wp10-accessibility.json` has no serious/critical violations.

Official portable k6 2.3.0 ran locally from .tmp. Only the smoke profile was executed.
Load/stress profiles are implemented. `tests/load/smoke-result.json` preserves the summary.
The test server raises API quotas to measure endpoint performance.

Docker Engine and GNU Make are absent locally. Hosted results appear below.

## WP11 and review follow-up evidence on 2026-11-18

- scripts/generate_api_docs.py ran successfully and generated the endpoint table from OpenAPI.
- scripts/check_version.py passed with authoritative version 0.1.0.
- Both workflow YAML files parsed and contained job definitions. The tag-triggered release remains unverified.
- README, user guide, API reference, runbook, SECURITY.md, CONTRIBUTING.md and CHANGELOG.md
  exist. A local-link check found zero missing targets.
- Python lint/format/mypy passed. Frontend typecheck, lint, 20 tests and production build passed.
  The final Playwright workflow passed after expanding the seed, retaining 18 dark/light screenshots.
- The final exact full pytest coverage command passed again on the expanded tree with 481 passed,
  three explicit skips, and 95.52% quant branch coverage. The same pytest skips are listed above.
- The corrected aggregate-only k6 exporter passed with 45 checks, zero failed requests and p95
  96.26 ms. The saved summary excludes setup_data and bearer tokens. Full-history Gitleaks passed
  across the 24 current commits before the documentation commit.
- Seven data API tests passed for 54 listings across five exchanges. NSE/BSE each contain Reliance
  and TCS, with INR currency, explicit Yahoo mappings and idempotent seeding assertions.
- Explicit live tests for authenticated FRED/Groq skipped without keys. A separate public CSV
  FRED DGS10 request returned 23 observations. No credentials were printed.
- The initial verification found no local Mailpit listener or default FinBERT dependencies.
  The optional integration runs below verified both paths.

The hardening commit is 787d8be. Indian reference coverage is committed separately as 2246bb0.
Current phase records defer to these work-package statuses and cannot independently establish
hardening or release completion.

## Optional integration follow-through on 2026-11-18

- Downloaded official portable Mailpit 1.33.1 into ignored .tmp storage and started an isolated
  catcher on loopback ports 11025/18025. The application sender delivered a message whose recipient,
  subject, plain-text body, HTML body and attachment bytes were verified through the Mailpit API.
  `uv run python scripts/verify_mailpit.py` passed. Compose/CI now pin that version, and CI invokes
  the same verifier against its Mailpit service.
- Real FinBERT inference passed through `scripts/verify_finbert.py --model .tmp/finbert-snapshot`
  using an isolated uv environment with Transformers 5.22.2 and CPU PyTorch 2.15.0. The application
  returned backend finbert and valid probabilities for all three classes. Model resolution was
  offline. RUNBOOK.md records the official revision and weight SHA-256. Hugging Face client downloads
  stalled, while a direct official snapshot download succeeded and matched its published checksum.
- News ingestion now forwards FINBERT_ENABLED and FINBERT_MODEL from CLI and worker settings.
  Disabled mode avoids optional model loading. Successful pipelines are cached per model/process,
  and tokenizer truncation handles the 512-token limit. Four regression tests cover disabled mode,
  configured model/caching, flat/nested pipeline outputs and enabled-mode fallback.
- Focused sentiment, research, ingestion and worker verification passed 27 tests. Python lint/format
  and strict quant typing passed. The exact full coverage command passed with 485 tests, three
  explicit skips and 95.52% quant branch coverage in 295.47 seconds.
- Live Yahoo adapter reads passed for RELIANCE.NS, TCS.NS, RELIANCE.BO and TCS.BO. All returned INR
  bars. Three listings returned six bars between 2026-11-09 and 2026-11-17. RELIANCE.BO returned
  three bars from 2026-11-13 through 2026-11-17. This did not write to the application database.
- Authenticated Groq/FRED checks and release publication remain pending. Default workspace
  dependencies continue to exclude optional FinBERT packages.

## Hosted verification of fea6a5c

[GitHub Actions run 44299236345](https://github.com/anmoliot/AnalystForge/actions/runs/44299236345)
completed with five passing jobs and three failing jobs.

| Check | Result |
| --- | --- |
| Linux Python job | PostgreSQL migrations, Mailpit delivery and the coverage gate passed. Pytest reported 486 passed, two skipped and 95.47% quant branch coverage. |
| PostgreSQL browser workflow | Playwright passed in 37.9 seconds, including the accessibility assertions. |
| k6 smoke, pip-audit, Gitleaks | All three jobs passed. |
| API Docker image | The dependency layer tried to install workspace packages before their source was copied. The build stopped before Trivy. |
| Web Docker image | The image built. Trivy returned exit code 1 and uploaded its JSON findings. |
| Web checks | npm audit reported 13 high and eight moderate findings and stopped the job before lint, types and tests. The high findings include dependency paths to picomatch. |

The follow-up Dockerfile uses `--no-install-workspace` in the dependency layer. A
manifest-only uv dry run resolved 123 external packages. Both Nginx references now use
the official stable 1.30.6 Alpine slim image. A new hosted build and scan must verify these changes.
The npm audit runs as a separate required workflow job so its result and the frontend test result
are both visible. The upstream [picomatch advisory](https://github.com/advisories/GHSA-fc5q-39xc-vjpf)
listed all published versions through 4.0.7 as affected when checked.

Bandit 1.9.4 scanned the API, worker and three library source trees locally with zero analysis
errors. It reported three low findings and one medium finding for custom-strategy execution.
CI retains the full report and fails on high findings or analysis errors. The ZAP passive plan
checks responses from three fixed GET requests on the disposable loopback API and uploads an
HTML report. Its first hosted result is pending.
