# Operations runbook

Run commands from the repository root. Native development uses Python 3.12, uv, Node 22 and
PostgreSQL. Containers additionally require Docker Engine and Compose. See KNOWN_LIMITATIONS.md
for checks that remain unexecuted.

## Migrations

Take a verified backup before changing a populated database. Stop writers during schema maintenance.
Set DATABASE_URL through the environment or the ignored .env file, then execute
`uv run alembic -c apps/api/alembic.ini current` and
`uv run alembic -c apps/api/alembic.ini upgrade head`.
Revision 0006 adds nullable audit request/status fields and preserves older rows.
Use `uv run alembic -c apps/api/alembic.ini check` to inspect metadata drift. Several later models
have no complete migration history, so a fresh production database requires additional migration work.
The browser harness creates its isolated schema through metadata and does not validate that history.

## Backups and restore

`sh scripts/backup.sh` dumps the running Compose database under var/backups as gzipped SQL with a
SHA-256 checksum. It requires Docker, gzip, sha256sum and the ignored .env file. Verify the dump
by restoring to a separate disposable database. The shell pipeline does not guarantee detection
of an upstream pg_dump failure, so do not treat file existence as a successful backup.

`CONFIRM_RESTORE=yes sh scripts/restore.sh var/backups/FILE.sql.gz` targets the configured Compose
database, checks a companion checksum when present and enables ON_ERROR_STOP. Restore writes
into the existing schema and is not an automatic clean-database replacement. Review the target
and stop application writers before running it. Recheck migrations, row counts and readiness afterward.
Native deployments can use pg_dump and psql with their secure local connection configuration.
Backup/restore scripts have not been exercised on this Windows host.

## Providers

Inspect `/api/v1/providers/health`, `/api/v1/data/coverage` and `/api/v1/data/quality`.
PRICE_PROVIDERS selects configured adapters in order. Missing keys disable optional providers.
Failures/cooldowns remain visible. Use `uv run analystforge-data prices --tickers AAPL --years 1`
or the relevant fundamentals/macro/fx/news command after diagnosing a provider. Keep SEC_USER_AGENT
set to a real contact identity. Inspect licensing before redistributing data.

## Redis and worker recovery

Check Redis availability and its persistence volume, then restart Redis and the Arq worker using
`docker compose restart redis worker` when running Compose. Native worker startup is
`uv run arq analystforge.worker.main.WorkerSettings`. Check worker logs and job_runs before retrying
failed ingestion. Avoid duplicate external notifications when replaying alert/screen delivery jobs.
API quotas fall back to local counters during Redis failure and retry Redis after five seconds.
Production readiness reports Redis failure. Development can run without Redis.

## Health and incidents

`/health` reports process liveness. `/ready` checks database, Redis and writable storage.
`/metrics` exposes Prometheus metrics. Nginx restricts metrics to private addresses, while direct
API access still needs a network boundary. Monitor HTTP failures/latency and
`analystforge_audit_write_failures_total`.

During an incident, preserve request IDs and UTC times, inspect readiness and service logs,
check migration/schema state and provider health, and scope affected tenants/resources.
Verify Redis fallback and audit-write metrics. Restrict the affected ingress or job path as needed.
After recovery, verify a representative read, authenticated mutation, audit row, calculation and
report download. Record the cause, recovery action and any missing audit interval.

## Optional integration verification

The SMTP verifier uses the application's sender and checks the raw message captured by Mailpit,
including the recipient, subject, plain-text body, HTML body and attachment bytes. It sends a
verification message to example.invalid through a loopback catcher.

On Windows, download the official portable Mailpit release into the ignored .tmp directory and
start it in a separate terminal. Version 1.33.1 is the version used for native verification and
the Compose/CI service pin.

```powershell
.tmp/mailpit/mailpit.exe --smtp 127.0.0.1:11025 --listen 127.0.0.1:18025 --database .tmp/mailpit-verification.db --disable-version-check
uv run python scripts/verify_mailpit.py
```

For the Compose ports use `uv run python scripts/verify_mailpit.py --smtp-port 1025 --http-port 8025`.
CI runs that command against its Mailpit service. Native verification does not establish Compose
startup or external SMTP relay behaviour. [Official Mailpit releases](https://github.com/axllent/mailpit/releases).

FinBERT is optional. News ingestion respects FINBERT_ENABLED and FINBERT_MODEL, caches successfully
loaded pipelines per model/process and applies tokenizer truncation at 512 tokens. With the flag
disabled it uses the labelled lexical path without loading Transformers. Enabled model failures
log an exception class and use that fallback.

```powershell
uv run --with transformers==5.22.2 --with torch==2.15.0 python scripts/verify_finbert.py
```

The verifier requires real model inference and fails if the application returns a fallback. The
extra packages are installed into an isolated uv environment. They are not default workspace
dependencies. Model weights require a download and several hundred MB of disk/memory. A verified
local snapshot can be selected with `--model .tmp/finbert-snapshot`. Model identifiers or paths for
normal ingestion are configured through FINBERT_MODEL. [Official model](https://huggingface.co/ProsusAI/finbert).

The verified optional environment used Transformers 5.22.2 and CPU PyTorch 2.15.0. The official
snapshot revision was `0bc2ac10dda6929bcb1f77ccc43c7ec5c424f031`. Its model.safetensors file was
437,965,908 bytes with SHA-256 `e5897858ff819aad7629b96ce521ae5477952d03634ef5dd30ed2d76357a9f00`.
The snapshot directory also contains config.json, tokenizer_config.json, special_tokens_map.json
and vocab.txt from the same revision. This host downloaded those files directly from the official
repository after its Hugging Face client stalled. Model resolution was offline during inference.
