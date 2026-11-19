# Security

The 0.1.x development line receives fixes on main. A published release has not been verified
in this work. Report vulnerabilities privately through GitHub private vulnerability reporting
for anmoliot/AnalystForge when enabled, or contact the repository owner privately to arrange
a secure channel. Include affected revision, reproduction steps and impact. Exclude credentials
and financial/customer data. No response-time SLA is established.

The threat model includes hostile API clients, stolen bearer tokens, cross-tenant access,
malicious custom strategies, compromised providers, dependency vulnerabilities and operational
failures. Review current limitations before using the platform with sensitive tenant data.

Implemented controls include Argon2 password hashes, expiring signed access JWTs, hashed rotating
refresh tokens, Fernet-encrypted TOTP secrets, SHA-256 hashes of high-entropy API keys,
request IDs, security headers, configurable request quotas, and independent mutation audit writes.
Audit rows contain actor, tenant, action, resource identity where available, request ID, response
status and UTC time. Bodies and credentials are excluded. Audit failures preserve responses and
increment a Prometheus counter. Database administrators retain direct access to audit records.

The role dependency supports ADMIN, PORTFOLIO_MANAGER, ANALYST and READ_ONLY. Authentication
and ownership checks are present on user-resource routes. Role enforcement is incomplete across
mutating endpoints. Registration can currently join an existing tenant by name and assigns ADMIN.
Self-service registration therefore requires an external restriction before a multi-tenant deployment.
Refresh-family reuse revocation is incomplete. API keys inherit user permissions and lack scopes.
The browser persists access tokens in localStorage, exposing them to successful same-origin XSS.

Quotas use atomic Redis increments with expiration. During outages, counters operate per process.
That mode can increase aggregate allowance across workers. Authentication writes use a stricter IP
quota. Resource failures return the ordinary envelope. Configure trusted proxy boundaries to retain
accurate client addresses. HSTS is emitted only for HTTPS responses. The current Compose ingress
uses HTTP and requires deployment TLS configuration.

Custom Python strategies require Linux, libseccomp and a kernel that supports thread-synchronized
seccomp filters. The child applies CPU, address-space, data and file-size limits. A syscall allowlist
permits in-memory computation and anonymous allocation. File I/O, sockets, process creation and
new file-backed mappings are denied. The child reports JSON through a bounded shared buffer.
Strategy execution is refused if either the filter or the resource limits cannot be installed.
The isolation controls have functional tests. An independent sandbox security audit remains outstanding.

Never commit .env files. Rotate any actual exposed credentials. CI scans dependencies, history and
images. Exact public-placeholder history exceptions are documented in .gitleaksignore.
