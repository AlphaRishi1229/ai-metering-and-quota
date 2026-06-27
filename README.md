# AI Metering and Quota Service

A FastAPI service that enforces per-user credit quotas with race-safe Postgres row locking.

---

## Quick Start

```bash
make up
```

Service available at http://localhost:8000.
Interactive API docs at http://localhost:8000/docs.

---

## All Commands

```
make up          Start all services (build if needed)
make down        Stop all services
make restart     Restart the app container only (faster than full rebuild)
make build       Rebuild images without starting
make install     Install Python test dependencies into the active venv
make test        Run the full pytest suite (starts db automatically)
make logs        Follow logs for all services
make logs-app    Follow app logs only
make logs-db     Follow db logs only
make ps          Show running service status
make clean       Stop services and delete all volumes (full reset)
make demo        Smoke test: create user, generate, check usage
make real-llm    Start with real Claude API
make help        Show all targets with descriptions
```

---

## Running Tests

```bash
# One-time: install test dependencies (activate your venv first)
python3 -m venv venv && source venv/bin/activate
make install

# Then any time you want to run tests:
make test
```

`make test` starts the database container, waits for it to be healthy, then runs all 9 pytest scenarios against the `metering_test` database (separate from the dev database so the running service is not affected).

---

## Using the Real Claude API

```bash
make real-llm ANTHROPIC_API_KEY=sk-ant-...
```

Or export the key first:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
make real-llm
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | Postgres async URL. Set automatically by docker-compose. |
| `USE_REAL_LLM` | No | `false` | Set to `true` to use ClaudeProvider instead of MockProvider. |
| `ANTHROPIC_API_KEY` | No | `""` | Required when `USE_REAL_LLM=true`. |

For local (non-Docker) development, create a `.env` file at the repo root. `pydantic-settings` reads it automatically.

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

Or just run `make demo` to execute all of the above in one shot.

---

## Design Document

See [DESIGN.md](DESIGN.md) for architecture, concurrency model, Alice example, provider abstraction, and tradeoff decisions.
