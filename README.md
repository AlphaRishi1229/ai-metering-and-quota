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

`make test` starts the database container, waits for it to be healthy, then runs all 11 pytest scenarios against the `metering_test` database (separate from the dev database so the running service is not affected).

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

## Testing AI Error Paths (Mock Provider)

The mock provider supports trigger words in the prompt to simulate AI-side failures without a real API key. Include any of these anywhere in your prompt:

| Trigger word | Simulates |
|---|---|
| `MOCK_ERROR` | Generic provider error |
| `MOCK_TIMEOUT` | Request timeout |
| `MOCK_RATE_LIMIT` | Rate limit exceeded |
| `MOCK_OVERLOAD` | Provider overload / service unavailable |

All triggers result in a `503` response, a released credit reservation, and a `status=ai_error` row in `usage_log`.

```bash
# Trigger a generic AI error
curl -s -X POST http://localhost:8000/users/1/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "MOCK_ERROR summarize this article"}' | python3 -m json.tool

# Trigger a timeout
curl -s -X POST http://localhost:8000/users/1/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "MOCK_TIMEOUT translate this to French"}' | python3 -m json.tool

# Confirm the reservation was released and credits were not charged
curl -s http://localhost:8000/users/1/usage | python3 -m json.tool

# Confirm ai_error appears in usage history
curl -s "http://localhost:8000/users/1/usage/history?limit=5" | python3 -m json.tool
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
