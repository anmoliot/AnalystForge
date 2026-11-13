# Progress

Updated at the end of every phase. Status is evidence-based: a phase is complete only when its
exit criteria were executed, not merely written.

| Phase | Scope | Status | Evidence |
|---|---|---|---|
| 0 | Foundations: repo, tooling, Docker, config, health, CI | Complete | 17 backend tests, 7 web tests, ruff/format/mypy clean, Alembic applied to PostgreSQL 18 and `alembic check` reports no drift, live `/health` `/ready` `/api/v1/meta` `/docs` `/metrics`, `npm run build`, dark/light screenshots in `docs/screenshots/` |
| 1 | Data layer, migrations, providers | Not started | |
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

## Environment notes

- Build host: Windows 11, Python 3.12/3.13, Node 22.20, PostgreSQL 18.3 running locally.
- uv 0.13.8 installed from the official standalone Windows build (`%USERPROFILE%\.local\bin`);
  `pip install uv` stalled on this host and was abandoned.
- Docker Engine, GNU Make and Redis are not installed on the build host. Native verification uses
  PostgreSQL directly; Docker/Make deliverable is validated by CI builds where possible.
- Playwright Chromium 1254 installed; `npm test`, typecheck, lint and build are green on Node 22.
