# Contributing

Use Python 3.12, Node 22 and uv. Run `uv sync --all-packages`, then `npm ci` in apps/web.
Run `python scripts/gen_env.py` to generate the ignored development environment. Configure a
local PostgreSQL connection before running Alembic or ingestion. See README.md for startup.

Required Python gates are `uv run ruff check .`, `uv run ruff format --check .`,
`uv run mypy packages/quant/src` and
`uv run pytest --cov=analystforge.quant --cov-branch --cov-report=term-missing --cov-fail-under=95`.
In apps/web run `npm run lint`, `npm run typecheck`, `npm test -- --run`, `npm run build`
and `npm run test:e2e`. Install Chromium using `npx playwright install chromium` first.
Browser tests start their own isolated API and Vite servers. See tests/load/README.md for k6.

Tests must assert real behaviour. Never remove or weaken a test to make a gate pass.
External integrations use recorded responses or explicit opt-in live tests. Keep synthetic inputs
confined to labelled tests/user-defined assumptions. Production analysis must report missing data.
Demo mode defaults off. Do not commit secrets or print provider credentials.

Use conventional commits such as feat, fix, docs or test. Keep work packages reviewable.
The root pyproject.toml version is authoritative. Update package/API/web mirrors together and run
`uv run python scripts/check_version.py`. Regenerate docs/API.md with
`uv run python scripts/generate_api_docs.py` after endpoint changes. Record executed evidence and
unverified checks in docs/PROGRESS.md.
