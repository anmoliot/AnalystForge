# Known limitations

Verified evidence is in PROGRESS.md. Historical delivery records describe earlier runs.

- Windows pytest passed with 95.52% quant branch coverage. Hosted Linux pytest passed with
  95.47%. Both images passed the hosted HIGH/CRITICAL Trivy gate. CI started the full Compose
  stack and checked readiness and the web response through Nginx. Release and GHCR publication
  remain unverified.
- Playwright passed against ephemeral SQLite locally and a separate PostgreSQL database in CI
  using historical AAPL/SEC fixtures. TimescaleDB and pgvector-specific behaviour remain unverified.
- Authenticated FRED/Groq tests skipped without keys. A separate live FRED public CSV check on
  2026-11-18 returned 23 DGS10 observations. Paid providers use recorded tests. Yahoo is unofficial,
  Stooq can return browser challenges, and provider redistribution rights need deployment review.
- API tests create metadata directly. Later model tables lack complete Alembic migrations, so a fresh
  migrated database can have schema gaps. Revision 0006 preserves older audit rows with null fields.
- Registration assigns ADMIN and can join an existing tenant by name. RBAC enforcement, refresh-family
  reuse revocation and scoped API keys require further work. See SECURITY.md before multi-tenant use.
- Linux strategy subprocesses have resource limits and AST restrictions. NumPy/Pandas capabilities
  require OS-level network/filesystem isolation before treating arbitrary strategies as untrusted.
  Windows execution is refused and Linux execution tests require a Linux runner.
- Reports now expose recorded closing-price metrics. Complete domain-specific report population still
  needs work. Excel formulas await sourced inputs. Advanced valuation methods accept JSON assumptions.
- Settings shows actual profile data. Key/TOTP management uses the API. Admin team/audit browsing
  is unavailable in the UI. Administrators can inspect the database.
- Redis fallback quotas apply per process, increasing aggregate allowance across workers. Independent
  audit writes can fail after a successful mutation. A counter/error event exposes that interval.
  Database administrator privileges currently allow audit-row edits.
- k6 smoke, load and stress passed against disposable SQLite with elevated quotas and recorded
  data. Deployment capacity still requires measurement with representative traffic and storage.
- Axe found no serious/critical violations on nine pages in both themes. Lower-impact findings are
  retained in docs/screenshots/wp10-accessibility.json. Dialogs, mobile navigation and all advanced
  controls need further review.
- Hosted npm audit passed the high gate with nine moderate findings after the picomatch
  advisory was withdrawn. Hosted pip-audit and Gitleaks passed. The local Bandit
  scan reported one medium and three low findings. See PROGRESS.md for the CI run.
- Backup scripts require Docker and Unix utilities. Upstream pipeline failure detection and restore
  rehearsal remain pending. A generated backup file alone does not prove recoverability.
- FinBERT and embedding-model downloads depend on available weights/network access. Lexical fallbacks
  label the selected backend. Forecast assumptions remain distinct from observed financial data.
- Real FinBERT inference passed on 2026-11-18 in an isolated uv environment with Transformers
  5.22.2 and CPU PyTorch 2.15.0. Default workspace dependencies still omit these optional packages.
  The Hugging Face client stalled during model retrieval on this host. A direct official snapshot
  download with SHA-256 verification succeeded, and inference used that local snapshot offline.
- Mailpit 1.33.1 delivery was verified natively on loopback ports 11025/18025, including plain text,
  HTML and attachment bytes. The hosted SMTP verifier also passed. Delivery through an external
  relay remains unverified.
- NSE/BSE live Yahoo adapter reads passed on 2026-11-18 for all four seeded listings. RELIANCE.NS,
  TCS.NS and TCS.BO returned six bars for the requested 2026-11-09 through 2026-11-17 interval.
  RELIANCE.BO returned three bars from November 13 onward. No application database was populated
  by this verification. Indian fundamentals remain unverified and have no SEC CIK mappings.
