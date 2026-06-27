# AI Metering and Quota Service

A FastAPI service that enforces per-user credit quotas with race-safe Postgres row locking.

---

## Quick Start

```bash
docker-compose up --build
```

Service available at http://localhost:8000.
Interactive API docs at http://localhost:8000/docs.

The Docker Compose setup starts Postgres (port 5432) and the app (port 8000). The `DATABASE_URL` environment variable is set automatically inside Docker.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | Postgres async URL. Example: `postgresql+asyncpg://postgres:postgres@localhost:5432/metering`. Set automatically by docker-compose. |
| `USE_REAL_LLM` | No | `false` | Set to `true` to use ClaudeProvider instead of MockProvider. |
| `ANTHROPIC_API_KEY` | No | `""` | Required when `USE_REAL_LLM=true`. |

For local (non-Docker) development, create a `.env` file at the repo root with the variables above. `pydantic-settings` reads it automatically.

---

## Running Tests

```bash
# Start the database container only
docker-compose up db -d

# Install dependencies
pip install -r requirements.txt

# Create the test database (separate from the dev database)
PGPASSWORD=postgres psql -h localhost -U postgres -c "CREATE DATABASE metering_test;"

# Run tests
pytest tests/ -v
```

Tests use `metering_test` (not `metering`) to avoid interfering with the running service. The test suite sets `DATABASE_URL` to point at `metering_test` automatically.

---

## Sample curl Commands

```bash
# Create a user
curl -s -X POST http://localhost:8000/users/ \
  -H "Content-Type: application/json" \
  -d '{"quota": 10000, "multiplier": 2.0}' | python3 -m json.tool

# Update quota
curl -s -X PATCH http://localhost:8000/users/1 \
  -H "Content-Type: application/json" \
  -d '{"quota": 20000}' | python3 -m json.tool

# Generate text (deducts credits)
curl -s -X POST http://localhost:8000/users/1/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Explain the difference between a process and a thread."}' | python3 -m json.tool

# Check current usage
curl -s http://localhost:8000/users/1/usage | python3 -m json.tool

# Usage history (paginated)
curl -s "http://localhost:8000/users/1/usage/history?limit=10&offset=0" | python3 -m json.tool
```

---

## Design Document

See [DESIGN.md](DESIGN.md) for architecture, concurrency model, Alice example, provider abstraction, and tradeoff decisions.
