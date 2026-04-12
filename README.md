# Mission Control

Mission Control is an operational task-management system for property
operations teams: it ingests source documents (canon, threads, call
transcripts, email), extracts candidate tasks and recommendations, and
presents them through a kanban board, review queue, and metrics
dashboard. The goal is a single pane of glass for everything a property
operator needs to anticipate, track, and close the loop on.

## Tech Stack

| Layer           | Choice |
|-----------------|--------|
| API             | FastAPI (Python 3.12), SQLAlchemy 2, Alembic, gunicorn + uvicorn workers |
| Web             | Next.js 16 (App Router) + TypeScript, React 19 |
| Database        | PostgreSQL 16 (prod: Azure Database for PostgreSQL Flexible Server) |
| Vector search   | pgvector |
| Container build | Multi-stage Docker, pushed to Azure Container Registry |
| Runtime         | Azure Container Apps (prod + staging environments) |
| Secrets         | Azure Key Vault via user-assigned managed identity |
| Observability   | Structured JSON logs → Log Analytics workspace, metric alerts |
| CI/CD           | GitHub Actions (lint, typecheck, test, build, deploy) |

## Repo Layout

```
mission-control/
├── apps/
│   ├── api/                 # FastAPI backend
│   └── web/                 # Next.js frontend
├── infra/
│   ├── azure/               # Azure setup scripts (ACR, KV, Container Apps, monitoring, backups)
│   ├── scripts/             # Operational scripts (db-backup.sh, etc.)
│   └── postgres/            # Local Postgres init for docker-compose
├── .github/
│   ├── workflows/           # CI, deploy-staging, deploy-production
│   └── SECRETS.md           # Required GitHub Actions secrets
├── docker-compose.yml       # Local dev (db + api + web)
└── .env.example             # All tunable environment variables
```

## Local Development

Requirements: Docker, Docker Compose, Python 3.12+, Node.js 20+, pnpm.

```bash
# 1. Copy the environment template and fill in any local overrides.
cp .env.example .env

# 2. Bring up Postgres, API, and Web in one shot.
docker compose up --build

# 3. Health check once the API container is ready.
curl http://localhost:8000/health
curl http://localhost:8000/info
curl http://localhost:3000/
```

If you prefer running the API outside Docker (faster hot-reload):

```bash
docker compose up -d db
python -m venv apps/api/.venv
source apps/api/.venv/bin/activate
pip install -r apps/api/requirements.txt
PYTHONPATH=apps/api uvicorn app.main:app --reload --port 8000
```

And the web app:

```bash
cd apps/web
pnpm install
pnpm dev
```

## Environment Variables

The full reference lives in [.env.example](.env.example). Highlights:

| Variable                    | Purpose |
|-----------------------------|---------|
| `DATABASE_URL`              | Postgres connection string (API + Alembic). |
| `APP_ENV`                   | `local`, `staging`, or `production` — surfaced on `/info`. |
| `APP_VERSION`               | Git SHA or semantic version — surfaced on `/info`. |
| `LOG_LEVEL`                 | Default `INFO`. Structured JSON output. |
| `CORS_ORIGINS`              | Comma-separated allowed origins. Never use `*` in production. |
| `RATE_LIMIT_ENABLED`        | Master switch for the slowapi rate limiter. |
| `RATE_LIMIT_DEFAULT`        | Default per-IP limit (e.g. `100/minute`). |
| `RATE_LIMIT_RECOMMENDATION` | Stricter limit for LLM-backed endpoints (default `10/minute`). |
| `NEXT_PUBLIC_API_URL`       | API base URL baked into the Next.js client bundle at build time. |

## Branch Strategy

Three long-lived branches, each backed by its own deployed environment:

```
main ────► staging ────► production
  │           │               │
  │           │               └── Azure Container Apps: mc-api, mc-web
  │           └── Azure Container Apps: mc-api-staging, mc-web-staging
  └── working branch, CI runs on every push
```

- **main** — trunk. All feature work lands here via PR. Required status checks: `lint-and-typecheck`, `test`, `build`. One reviewer approval required. No direct push.
- **staging** — deployment branch. Merges from `main` auto-deploy to the staging Container Apps environment on every push. Direct push allowed for urgent hotfixes.
- **production** — deployment branch. Merges from `staging` go through a `deploy-production.yml` environment gate (required reviewer), then deploy to production Container Apps. The production image is always tagged `latest` in ACR.

Full protection rules are documented in [infra/README.md](infra/README.md#branch-protection-rules).

## Deployment

1. **Develop** on a feature branch off `main`. Push early, CI runs on every commit.
2. **Open a PR to `main`.** CI must be green and one reviewer must approve.
3. **Promote to staging.** Merge `main` into `staging` (or push the PR merge commit). `deploy-staging.yml` builds both images, pushes to ACR with tag `staging-<sha>`, updates the staging Container Apps, and runs health checks against `/health` and `/`.
4. **Promote to production.** Once staging is verified, merge `staging` into `production`. `deploy-production.yml` fires, **pauses at the `production` environment gate for an approver**, then builds images tagged `prod-<sha>` and `latest`, updates the production Container Apps, and runs health checks.

Rollback is a fast-forward revert: redeploy a previous image tag by either reverting the commit and letting CI redeploy, or pointing the container app at an earlier tag with `az containerapp update --image`.

## Infrastructure

All Azure resources are provisioned by idempotent shell scripts in
[`infra/azure/`](infra/azure/). Run them in order on a fresh subscription:

```bash
cd infra/azure
./acr-setup.sh              # Container Registry
./keyvault-setup.sh         # Key Vault + managed identity
./container-apps-setup.sh   # Production Container Apps (with health probes)
./staging-setup.sh          # Staging Container Apps (shares ACR + KV)
./monitoring-setup.sh       # Log Analytics + alert rules
./backup-setup.sh           # PostgreSQL backup retention + geo-redundancy
```

See [infra/README.md](infra/README.md) for prerequisites, required
permissions, verification commands, secret provisioning, and teardown.

Database backups are handled two ways:

- **Automated point-in-time restore** via Azure Database for PostgreSQL Flexible Server (14-day retention, geo-redundant). Configured by `infra/azure/backup-setup.sh`.
- **Manual logical dumps** to Azure Blob Storage via [`infra/scripts/db-backup.sh`](infra/scripts/db-backup.sh). Invoked ad-hoc or from a cron / Automation runbook; retains 30 days.

## CI/CD

Three GitHub Actions workflows:

| Workflow                | Trigger | Purpose |
|-------------------------|---------|---------|
| `ci.yml`                | push (any branch), PR (main/staging/production) | Lint, typecheck, test, Docker build verification |
| `deploy-staging.yml`    | push to `staging` | Build, push to ACR, update staging Container Apps, health check |
| `deploy-production.yml` | push to `production` | Same as staging, plus `environment: production` approval gate |

Required repository secrets are listed in [.github/SECRETS.md](.github/SECRETS.md).

## Health and Observability

- `GET /health` — liveness; returns 200 with a timestamp (no DB call).
- `GET /ready` — readiness; returns 200 if the database is reachable, 503 otherwise.
- `GET /info` — version, environment, and uptime.

All API logs are emitted as structured JSON with a `request_id` field
propagated via the `X-Request-ID` header. Container Apps streams both
API and Web logs to the `mc-logs` Log Analytics workspace; operational
alerts are configured by `infra/azure/monitoring-setup.sh`.
