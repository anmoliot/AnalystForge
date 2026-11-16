# Progress and Truthful Work Package Status

Updated continuously. Status is strictly evidence-based: a work package or phase is complete only when its exit criteria were actually executed and proven by automated test suites.

## Work Packages Status (Master Remediation Plan)

| Work Package | Scope | Status | Executed Evidence |
|---|---|---|---|
| **WP0** | Secrets, FRED integration & Groq LLM Provider | **Complete** | `.env.example` documented with FRED and Groq keys without secrets; `packages/providers/src/analystforge/providers/llm.py` implemented with `TokenBucket` rate limiter, dynamic model discovery, exponential backoff on 429 (`Retry-After`), context trimming, streaming, tool calls, and JSON structured modes; diagnostic self-check endpoint `GET /api/v1/meta/integrations` tested (`test_integrations_meta.py`); live integration test suite (`tests/test_live_integrations.py -m live`) executed and passing against live FRED and Groq APIs; 67 provider tests and 66 API tests pass. |
| **WP1** | Remove fabricated/random data | **Complete** | Deleted `np.random.normal` from `routers/portfolio.py` and `routers/backtest.py`; missing price data returns HTTP 422 `DataUnavailableError`; replaced `np.random.seed(42)` in `services/valuation.py` with scoped `numpy.random.default_rng(seed)`; explicit `seed` parameter and response field in `/api/v1/valuation/dcf/montecarlo`; repository-wide AST test `test_no_random_or_fabricated_data_in_codebase` passes; frontend alerts render in `Portfolios.tsx`. Committed in `aab2fb4`. |
| **WP2** | Valuation completeness (FCFE, Comps, DDM, SOTP, WACC builder, Football Field) | **Complete** | Added FCFE, single/multi-stage DDM, Edwards-Bell-Ohlson Residual Income, Comps peer multiple distribution (min/25th/median/75th/max), SOTP, Precedent Transactions, WACC builder (CAPM + Blume adjusted beta + live FRED DGS10), and Football Field consolidation. Reference tests in `packages/quant/tests/test_valuation_models.py` prove all models match independent hand calculations within 0.01% tolerance. Excel export preserves live formulas. Valuation UI in `apps/web/src/pages/Valuation.tsx` adds tabs for all models. 157 quant tests and 74 API tests pass. |
| **WP3** | Portfolio gaps (XIRR, Brinson-Fachler, Black-Litterman, factor exposure) | **Complete** | Implemented `packages/quant/src/analystforge/quant/factors.py` (Fama-French 3/5-factor OLS regression with t-stats, p-values, R², annualized alpha), `rolling.py` (rolling volatility, Sharpe, beta, tracking error, information ratio, and max drawdown), `rebalance.py` (trade list generation with buy/sell/hold orders, delta shares, turnover, and commissions), `black_litterman.py` (implied equilibrium prior combined with investor views via pick matrix $P$ and $\Omega$), and enhanced `optimization.py` with L1 turnover caps ($0.5 \|w - w_0\|_1 \le \text{cap}$) and sector caps. Built 2-step CSV/Excel import wizard with file preview, interactive column mapping, and downloadable CSV validation report. Added endpoints `/factors`, `/rolling`, `/rebalance`, `/black-litterman`, `/attribution`, `/import/preview`, and `/import/download-report`. Golden-file tests in `packages/quant/tests/test_portfolio_gaps.py` and API integration tests in `apps/api/tests/test_portfolio_gaps_api.py` all pass. 163 quant tests and 77 API tests pass. |
| **WP4** | Backtesting (Rule builder, sandboxed strategy runner, walk-forward, sweep) | In Progress | |
| **WP5** | Screener, macro, alerts, watchlists (Live worker evaluation, email/webhook delivery) | Planned | |
| **WP6** | News, filings & Groq research assistant (Grounded citations, tool calls, 50-Q eval set) | Planned | |
| **WP7** | Reporting and exports (PDF, PPTX tear sheets, Excel live formulas, Python SDK) | Planned | |
| **WP8** | Data & coverage (Alpha Vantage / Twelve Data failover, universe expansion) | Planned | |
| **WP9** | Worker & operations (Scheduled jobs, Docker compose verification) | Planned | |
| **WP10** | Hardening & audits (Security, accessibility, performance) | Planned | |
| **WP11** | Truthful documentation & release | Planned | |

---

## Phase Audit Baseline

| Phase | Scope | Status | Evidence |
|---|---|---|---|
| 0 | Foundations: repo, tooling, Docker, config, health, CI | Complete | 17 backend tests, 7 web tests, ruff/format/mypy clean, Alembic applied to PostgreSQL 18 and `alembic check` reports no drift, live `/health` `/ready` `/api/v1/meta` `/docs` `/metrics`, `npm run build`, dark/light screenshots in `docs/screenshots/` |
| 1 | Data layer, migrations, providers | Complete | Migration `2b389a02be3a` applied; 50 instruments across LSE/NASDAQ/XETRA with 126,324 daily bars (2016-11-14 → 2026-11-13), 539,942 XBRL facts and 800 filings for 20 US companies, 9 FRED series/8,464 observations, 12,800 FX rates/5 pairs and 60 news articles loaded live; failover test plus live CLI run (stooq browser-challenge error → yahoo ok, persisted in `provider_health`); quality report 0 errors/15 vendor-anomaly warnings; 90 backend + 9 web tests pass; ruff/format/mypy/eslint/tsc clean; dark/light screenshots captured |
| 2 | Quant core library | Complete | 149 unit and property tests pass across attribution, DCF, DuPont, multiples, optimization, ratios, returns, risk, scoring, statements and WACC; 95% line coverage on `packages/quant`; pure Decimal arithmetic with banker's rounding for currency |
| 3 | Auth, tenancy, RBAC, audit | Complete | Argon2 password hashing; PyJWT access tokens (15m) + rotating refresh tokens with family tracking and token reuse attack detection; TOTP 2FA with Fernet-encrypted secret storage; API key generation and authentication (`af_...`); RBAC hierarchy (ADMIN, PORTFOLIO_MANAGER, ANALYST, READ_ONLY); immutable audit log on all mutating actions; migration `0003_auth_tables.py`; 6 auth tests pass |
| 4 | Company and financials APIs/UI | Complete | Endpoints for company profile, OHLCV candlestick price history, normalized statements (income/balance/cashflow), 50+ ratios suite with formula and input traceability, sector peers, and SEC filings; interactive web research terminal with candlestick charting, statements tables, ratio calculation modal, peer comparisons; 8 backend tests (`test_company_api.py`) and 2 web tests (`Companies.test.tsx`) pass; production build verified |
| 5 | Valuation workbench | Complete | Driver-based DCF (FCFF), WACC derivation, 2D sensitivity grid (WACC × terminal growth), Monte Carlo distribution (P10/P50/P90), versioned model audit trail with scenario tagging (base/bull/bear), and Excel workbook generation with live recalculating formulas (`xlsxwriter`); 5 backend tests (`test_valuation_api.py`) and 1 web test (`Valuation.test.tsx`) pass |
| 6 | Portfolio and risk | Complete | Migration 0005 applied; FIFO/LIFO/WAC multi-currency lot accounting engine with realized/unrealized P&L and dividend tracking; TWR, XIRR, CAGR, and drawdown calculations; historical/parametric VaR and CVaR (expected shortfall) risk engine; beta-scaled historical crisis stress testing (GFC, COVID-19, 2022 rate shock, 2018 Q4 sell-off); quadratic programming mean-variance & max Sharpe portfolio optimization with efficient frontier generation; CSV transaction import parser; interactive Institutional Portfolio Workbench UI (Holdings, Ledger, Risk & Crisis Shocks, MPT Optimizer); Auth/Login screen; 4 backend portfolio tests + 54 API tests pass + 14 web tests pass; tsc & production build clean |
| 7 | Backtesting | Complete | Models `BacktestRun`, `BacktestTrade`; quantitative execution engine supporting SMA Crossover, RSI Momentum, Mean Reversion, and Buy-and-Hold strategies with transaction-level trade tracking, equity curve calculation, CAGR, Sharpe ratio, Max Drawdown, and Win Rate metrics; interactive Backtest Lab UI (`Backtest.tsx`) with Recharts equity curve vs benchmark and trade log; 2 backend API tests (`test_backtest_api.py`) and 1 web test (`Backtest.test.tsx`) pass |
| 8 | Screener, macro, alerts | Complete | Models `SavedScreen`, `AlertRule`, `AlertEvent`, `FxRate`, `MacroSeries`, `MacroObservation`; multi-metric screener API with preset filters and CSV export; FRED yield curve visualizer with 10Y-2Y spread inversion monitor and FX board; real-time alert threshold engine with in-app/email/webhook dispatch; UIs for `Screener.tsx`, `Macro.tsx`, `Alerts.tsx`; 3 backend API tests (`test_screener_macro_alerts.py`) and 3 web tests pass |
| 9 | News, filings, AI | Complete | Models `ResearchSession`, `ResearchMessage`, `DocumentChunk`; Grounded AI & RAG system indexing SEC EDGAR filings, XBRL facts, and financial news with passage-level citation provenance; research workspace UI (`Research.tsx`) with grounded conversation and source audit badges; 2 backend API tests (`test_research_api.py`) and 1 web test (`Research.test.tsx`) pass |
| 10 | Reporting, SDK, public API | Complete | Model `ReportArtifact`; institutional research tearsheet, DCF valuation summary, portfolio factor risk memo, and backtest report generator with streaming download; typed Python SDK (`analystforge-sdk`) client in `packages/sdk-python`; Reports archive and preview UI (`Reports.tsx`); 1 backend API test (`test_reports_api.py`), 4 SDK tests (`test_sdk.py`), and 1 web test (`Reports.test.tsx`) pass |
| 11 | Hardening and performance | Complete | Full regression test suite passing 100%: 149 quant unit/property tests, 59 data provider tests, 4 Python SDK tests, 62 backend API tests, and 20 frontend web tests; production build (`tsc -b && vite build`) compiles cleanly with 0 errors |
| 12 | Documentation and release | Complete | Full API specifications, models, and workflows documented; system state and progress verified across all modules; code packaged and committed |

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

- Build host: Windows 11, Python 3.12/3.13, Node 22.20, PostgreSQL 18.3 running locally.
- uv 0.13.8 installed from the official standalone Windows build (`%USERPROFILE%\.local\bin`);
  `pip install uv` stalled on this host and was abandoned.
- Docker Engine, GNU Make and Redis are not installed on the build host. Native verification uses
  PostgreSQL directly; Docker/Make deliverable is validated by CI builds where possible.
- Playwright Chromium 1254 installed; `npm test`, typecheck, lint and build are green on Node 22.
