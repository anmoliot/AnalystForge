# Browser test provenance

The AAPL daily bars were exported read-only from the local ingested market database on
2026-11-17. Each row retains the provider, daily timestamp and ingestion timestamp.
The file contains 45 consecutive recorded observations from 2016-11-14 00:00:00+00:00 through 2017-01-19 00:00:00+00:00.
SEC facts use the existing recorded companyfacts fixture under packages/providers/tests/fixtures.
The isolated test API uses the ordinary application, database models and services.
No browser request interception supplies financial results.
Test accounts and the single-share portfolio transaction are created exclusively in the test database.
DCF inputs are explicit reviewer assumptions and are labelled REVIEWER_ASSUMPTIONS.
These screenshots demonstrate recorded historical coverage and unavailable states.
They do not attest to current provider availability or complete financial-statement coverage.
