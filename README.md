# Mission Control Monorepo

Minimal starter monorepo for local development.

## Structure

- `apps/api` - FastAPI backend
- `apps/web` - Next.js frontend
- `infra` - local infrastructure support files
- `docs` - architecture and runbook notes

## Prerequisites

- Docker + Docker Compose
- Python 3.12+
- Node.js 20+
- pnpm (or npm)

## Local Development

1. Start Postgres with pgvector:

   ```bash
   docker compose up -d db
   ```

2. API setup:

   ```bash
   cp apps/api/.env.example apps/api/.env
   python -m venv apps/api/.venv
   source apps/api/.venv/bin/activate
   pip install -e apps/api
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

   Health check:

   ```bash
   curl http://localhost:8000/health
   ```

3. Web setup:

   ```bash
   cp apps/web/.env.example apps/web/.env.local
   cd apps/web
   pnpm install
   pnpm dev
   ```

   Open <http://localhost:3000>.

## Notes

- This is intentionally minimal.
- No auth or feature implementation is included yet.
