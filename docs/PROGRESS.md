# Progress

Updated at the end of every phase. Status is evidence-based: a phase is complete only when its
exit criteria were executed, not merely written.

| Phase | Scope | Status | Evidence |
|---|---|---|---|
| 0 | Foundations: repo, tooling, Docker, config, health, CI | Complete | 17 backend tests, 7 web tests, ruff/format/mypy clean, Alembic applied to PostgreSQL 18 and `alembic check` reports no drift, live `/health` `/ready` `/api/v1/meta` `/docs` `/metrics`, `npm run build`, dark/light screenshots in `docs/screenshots/` |
| 1 | Data layer, migrations, providers | Complete | Migration `2b389a02be3a` applied; 50 instruments across LSE/NASDAQ/XETRA with 126,324 daily bars (2016-11-14 → 2026-11-13), 539,942 XBRL facts and 800 filings for 20 US companies, 9 FRED series/8,464 observations, 12,800 FX rates/5 pairs and 60 news articles loaded live; failover test plus live CLI run (stooq browser-challenge error → yahoo ok, persisted in `provider_health`); quality report 0 errors/15 vendor-anomaly warnings; 90 backend + 9 web tests pass; ruff/format/mypy/eslint/tsc clean; dark/light screenshots captured |
| 2 | Quant core library | Not started | |
| 3 | Auth, tenancy, RBAC, audit | Not started | |
| 4 | Company and financials APIs/UI | Not started | |
| 5 | Valuation workbench | Not started | |
| 6 | Portfolio and risk | Not started | |
| 7 | Backtesting | Not started | |
| 8 | Screener, macro, alerts | Not started | |
| 9 | News, filings, AI | Not started | |
| 10 | Reporting, SDK, public API | Not started | |
| 11 | Hardening and performance | Not started | |
| 12 | Documentation and release | Not started | |

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
