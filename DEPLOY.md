# Deployment

The MVP runs as five containers via `docker-compose.yml`:

| Service | Image / build | Port | Role |
|---------|---------------|------|------|
| `db` | `postgres:16` | — | Product database |
| `engine` | `../changeorder-recovery/backend` | 8088 | Detection engine + v1.2 adapter |
| `api` | `./backend` | 8000 | Product API (runs migrations on start) |
| `worker` | `./backend` (`python -m app.worker`) | — | Drives the engine per contract v1.2 |
| `web` | `./frontend` | 3000 | Next.js UI |

## Prerequisites
1. Clone the engine repo as a **sibling** of this one and check out the adapter branch:
   ```
   git clone https://github.com/nochatom/changeorder-recovery.git ../changeorder-recovery
   git -C ../changeorder-recovery checkout feat/v1.2-engine-adapter
   ```
2. Have an Anthropic API key (the engine calls `claude-opus-4-8`).

## Run
```bash
ANTHROPIC_API_KEY=sk-ant-...  JWT_SECRET=$(openssl rand -hex 32)  docker compose up --build
```
- Web UI: http://localhost:3000
- API docs: http://localhost:8000/docs
- Engine: http://localhost:8088/health

The `api` container applies Alembic migrations (`alembic upgrade head`) before serving, so the schema is created on first boot. Uploaded documents are stored on a shared `docdata` volume (`VA_LOCAL_DOC_DIR=/data/docs`) so the API and worker see the same files; swap to S3 by setting `VA_S3_BUCKET`/region instead.

## Configuration (product, `VA_` prefix)
| Env | Purpose | Compose default |
|-----|---------|-----------------|
| `VA_DATABASE_URL` | Postgres URL | `postgresql+psycopg://va:va@db:5432/variation_audit` |
| `VA_ENGINE_BASE_URL` | Engine v1.2 endpoint | `http://engine:8088` |
| `VA_JWT_SECRET` | JWT signing key (**set a real 32+ byte secret in prod**) | dev placeholder |
| `VA_LOCAL_DOC_DIR` | Local document store (dev) | `/data/docs` |

## CI
`.github/workflows/ci.yml` runs on push/PR: backend `pytest` (+ Alembic schema render) and `npm run build` for the frontend.

> Note: Docker images were authored but not built in the dev environment (no Docker daemon there); CI builds the frontend and runs backend tests. Validate `docker compose up --build` on a host with Docker before a production cutover.
