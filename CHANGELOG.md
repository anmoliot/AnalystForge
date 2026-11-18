# Changelog

Changes follow the Keep a Changelog structure. Versions use semantic versioning.

## [Unreleased]

## [0.1.0] - 2026-11-17

### Added

- WP0 provider configuration and integration diagnostics.
- WP2 valuation models, scenario calculations and formula exports.
- WP3 portfolio attribution, rolling risk, factor regression and allocation tools.
- WP4 rule-driven backtests, strategy subprocess controls, walk-forward analysis and parameter sweeps.
- WP5 screens, alerts, watchlists, notes and expiring share links.
- WP6 filing/news retrieval and research answers with citations and explicit refusals.
- WP7 report formats and Python SDK methods.
- WP8 secondary market-data provider adapters and coverage diagnostics.
- NSE/BSE reference entries for Reliance and TCS with INR currency and Yahoo listing mappings.
- WP9 worker schedules and operational cleanup.
- WP10 Redis/local quotas, mutation audits, security headers, browser/axe verification, load profiles
  and dependency/history/container scan jobs.
- WP11 generated API reference, operations/security/contributor documentation and tag release workflow.

### Changed

- WP1 unavailable data handling replaces fabricated analysis results.
- Removed fixed company figures from automatic valuations and report output.
- Corrected frontend theme contrast and form names. Added recorded browser screenshots.
- Enforced 95% quant branch coverage in CI and mirrored-version validation before release.

### Fixed

- Windows imports of the Unix strategy sandbox and explicit refusal of unsupported execution.
- Failed-login audit persistence and nullable screener CSV exports.

### Known limitations

- Container execution, Trivy results and GHCR publication remain unverified locally.
- Migration coverage, registration/RBAC restrictions, OS-level sandbox isolation and current live
  provider coverage require further work described in docs/KNOWN_LIMITATIONS.md and SECURITY.md.
