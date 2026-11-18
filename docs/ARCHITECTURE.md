# Architecture

AnalystForge 0.1.0 is a uv workspace containing FastAPI, React 19/Vite, an Arq worker,
provider adapters, a quantitative library and a Python SDK.

## Requests and storage

Nginx routes the web bundle and /api/v1 requests. Routers validate input and invoke services.
Both routers and services issue SQLAlchemy queries. Providers retrieve external data with
provider identity and dates. PostgreSQL stores application data. Tests create metadata with
SQLite. Deployment migrations target PostgreSQL, with later schema gaps tracked in KNOWN_LIMITATIONS.md.
The quant package uses Decimal for valuation/accounting and floats for statistical models.
Custom Python strategies require Unix resource limits and still need an OS isolation audit.

## Authentication and request controls

Access JWTs and API keys use Authorization bearer headers. Rotating refresh tokens use httpOnly
cookies and hashed database records. High-entropy API keys use SHA-256 hashes. Fernet protects
TOTP secrets. Central role/tenant dependencies exist, with incomplete route enforcement.
SECURITY.md documents registration, authorization and refresh-family limitations.

Versioned API requests share per-key/user/IP fixed-window quotas. Redis increments and expiration
execute atomically in Lua. A bounded local fallback applies during outages. Authentication
mutations have stricter quotas. Probes remain independently available.

Mutation middleware records outcomes in independent audit transactions. Authentication attaches
verified actor/tenant identities. Audit rows contain resource identities where available, request
IDs, status and UTC time without bodies or secrets. Write failures preserve responses and increment
a metric. Database administrators retain edit privileges.

## Providers, research and workers

Provider registries route configured prices, fundamentals, macro, FX, news and LLM operations.
Failover attempts and health remain visible. Missing inputs surface unavailable states.
Research retrieval uses lexical and configured embedding paths with citations and refusal handling.
Live/model coverage depends on keys, network access and model weights.

Arq schedules ingestion, alerts, saved screens and cleanup through Redis. Selected development
operations run inline. Cache/queue/readiness behaviour depends on configuration. Load/stress
verification is required before making deployment capacity claims.

## Delivery and observability

Request IDs correlate errors, logs and audit rows. Prometheus exposes HTTP/provider/job/audit
metrics at /metrics. Nginx restricts that route to private addresses. Direct API access requires
a deployment network boundary.

CI includes Python/frontend gates, 95% quant branch coverage, browser/axe tests, k6 smoke,
dependency/history scans and Docker/Trivy jobs. Tag releases rerun CI before versioned GHCR
publication and GitHub release creation. Root pyproject.toml is the version authority.
Package/API/web mirrors are checked before release. Executed evidence is in PROGRESS.md.
