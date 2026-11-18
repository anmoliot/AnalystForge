# Load verification

Start the isolated test API with `uv run python tests/e2e/server.py`. Run
`k6 run tests/load/smoke.js`, `k6 run tests/load/load.js` or `k6 run tests/load/stress.js`.
Each profile checks health, metadata, a recorded company, a user-defined DCF calculation and the screener.
Thresholds require p95 below 500 ms, request failures below 1% and successful checks above 99%.
The DCF inputs are explicit load-test assumptions. Prices come from the recorded fixture.
The test server uses an ephemeral database and raises API quotas to 12,000/minute.
`BASE_URL` overrides the server URL. Use a disposable database because setup registers an account.
The custom summary contains aggregate metrics only. K6_SUMMARY_PATH selects its output path.
Avoid k6's --summary-export option because its setup_data includes the temporary access token.
