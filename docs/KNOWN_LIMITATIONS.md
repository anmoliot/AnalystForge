# Known limitations

Verified evidence is in PROGRESS.md. Historical delivery records describe earlier runs.

- Windows gates pass with 95.52% quant branch coverage. Docker Engine and GNU Make are absent.
  Compose, Nginx, Trivy images, the release workflow and GHCR publication remain unexecuted
  for this change. CI success is not claimed.
- Browser verification uses ephemeral SQLite and historical AAPL/SEC fixtures. CI configures
  a separate PostgreSQL database. That path remains unverified. TimescaleDB and pgvector-specific
  behaviour were not exercised locally.
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
- k6 smoke passed against disposable SQLite with elevated quotas. Load/stress profiles remain
  unexecuted. The smoke measurement does not establish production capacity.
- Axe found no serious/critical violations on nine pages in both themes. Lower-impact findings are
  retained in docs/screenshots/wp10-accessibility.json. Dialogs, mobile navigation and all advanced
  controls need further review.
- npm audit passes the high gate with nine moderate findings. pip-audit found no known Python
  vulnerabilities during verification. Advisory results can change.
- Backup scripts require Docker and Unix utilities. Upstream pipeline failure detection and restore
  rehearsal remain pending. A generated backup file alone does not prove recoverability.
- FinBERT and embedding-model downloads depend on available weights/network access. Lexical fallbacks
  label the selected backend. Forecast assumptions remain distinct from observed financial data.
- Real FinBERT inference passed on 2026-11-18 in an isolated uv environment with Transformers
  5.22.2 and CPU PyTorch 2.15.0. Default workspace dependencies still omit these optional packages.
  The Hugging Face client stalled during model retrieval on this host. A direct official snapshot
  download with SHA-256 verification succeeded, and inference used that local snapshot offline.
- Mailpit 1.33.1 delivery was verified natively on loopback ports 11025/18025, including plain text,
  HTML and attachment bytes. Compose and external SMTP relay behaviour remain unverified. The
  default ports 1025/8025 had no existing service. CI now includes the real Mailpit verifier.
- NSE/BSE live Yahoo adapter reads passed on 2026-11-18 for all four seeded listings. RELIANCE.NS,
  TCS.NS and TCS.BO returned six bars for the requested 2026-11-09 through 2026-11-17 interval.
  RELIANCE.BO returned three bars from November 13 onward. No application database was populated
  by this verification. Indian fundamentals remain unverified and have no SEC CIK mappings.
