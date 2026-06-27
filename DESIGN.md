# AI Metering and Quota Service — Design Document

## Overview

A FastAPI service that sits in front of an AI text generation layer and enforces per-user credit quotas. Clients submit prompts to a generation endpoint; the service estimates token cost, checks that the user's remaining quota covers the estimate, reserves the estimate, calls the AI provider, and then debits the actual token count converted to credits via a per-user multiplier. The core design constraint is race-safety: concurrent requests from the same user must never collectively overdraw the quota. This is achieved with Postgres `SELECT FOR UPDATE` row locking — no Redis, no application-level locks.

---

## Architecture Diagram

```
Client
  │
  ▼
FastAPI (uvicorn :8000)
  ├── POST   /users/                        ─┐
  ├── PATCH  /users/{id}                    ─┤─► users router
  ├── GET    /users/{id}/usage              ─┤─► inspection router
  ├── GET    /users/{id}/usage/history      ─┘
  └── POST   /users/{id}/generate ──────────────► AI Provider
                                                  ├── MockProvider  (default)
                                                  └── ClaudeProvider (USE_REAL_LLM=true)
         │
         ▼
     PostgreSQL
     ┌──────────────────────────────────────────────┐
     │ users     (id, quota, multiplier,            │
     │            used_credits, reserved_credits)   │
     │ usage_log (id, user_id, prompt_tokens,       │
     │            completion_tokens,                │
     │            estimated_credits, actual_credits,│
     │            status, created_at)              │
     └──────────────────────────────────────────────┘
```

---

## Concurrency Model

### Reserve / Generate / Settle Pattern

The generate endpoint uses a three-phase pattern to keep the row lock out of the critical AI generation path while still preventing quota overrun:

```
T=0  Request arrives → BEGIN TX → SELECT user FOR UPDATE
T=0  Check: used_credits + reserved_credits + estimated_credits ≤ quota  → else 402
T=0  reserved_credits += estimated_credits → COMMIT (lock released)

T=1  AI layer generates → returns actual token counts (outside any TX)

T=2  BEGIN TX → SELECT user FOR UPDATE
T=2  reserved_credits -= estimated_credits
T=2  used_credits += actual_credits → COMMIT
T=2  Write usage_log row (stores prompt_tokens, completion_tokens, estimated_credits, actual_credits, status)
```

The reserve transaction (T=0) holds the lock for only a lightweight DB roundtrip (~1 ms). Generation (T=1) happens entirely outside any transaction and takes 100–2000 ms depending on the AI provider. Concurrent requests from the same user queue at the DB lock during T=0 only; they do not serialize generation. This gives correctness without sacrificing throughput.

The `reserved_credits` column accumulates pending reservations across in-flight requests. The quota check at T=0 accounts for reservations: `used_credits + reserved_credits + estimated_credits ≤ quota`. If a second concurrent request for the same user arrives while T=1 is in progress, its T=0 check sees the reservation already in place and correctly reduces the available budget.

---

## Alice Example

```
User: alice
  quota:      1000 credits
  multiplier: 2.0×
  used:        800 credits
  remaining:   200 credits

Incoming request:
  prompt: "explain recursion" (44 chars → ~11 tokens estimated)
  estimated_completion: 150 tokens
  estimated_total: 161 tokens
  estimated_credits: 161 × 2.0 = 322

Check: 800 + 322 = 1122 > 1000 → 402 Quota Exceeded

(Alice pays, quota raised to 1200)

Second attempt:
  Check: 800 + 322 = 1122 ≤ 1200 → PASS
  Reserve 322 credits (used_reserved = 322)
  Generate → actual: prompt=11, completion=178, total=189
  actual_credits = 189 × 2.0 = 378
  Settle: used = 800 + 378 = 1178, reserved = 0
  Remaining: 1200 - 1178 = 22 credits
```

The estimate (322) differs from the actual debit (378) because completion tokens are not known until after generation. Both values are logged per row in `usage_log` for auditability.

---

## Credit Formula

```
actual_credits = (prompt_tokens + completion_tokens) × multiplier
```

The same formula is used for the estimate, substituting estimated token counts:

```
estimated_credits = (estimated_prompt_tokens + estimated_completion_tokens) × multiplier
```

**MockProvider estimate:** `chars / 4` for the prompt; completion estimated as `prompt_tokens × 1.0` (center of the ±10% variance range).

**ClaudeProvider estimate:** Uses Anthropic's `messages.count_tokens()` API for the prompt token count; estimates completion as `prompt_tokens × 1.0` (same heuristic). The actual is read from `response.usage` after generation.

Estimate vs. actual divergence is expected, logged, and bounded to one request's worth of overrun.

---

## Provider Abstraction

```python
class BaseProvider(ABC):
    def estimate_tokens(self, prompt: str) -> int: ...
    async def generate(self, prompt: str) -> GenerationResult: ...
```

`GenerationResult` carries `text`, `prompt_tokens`, `completion_tokens`.

**MockProvider** (default): `estimate_tokens` = `len(prompt) // 4`. `generate` returns a mock text with completion_tokens drawn from `uniform(0.9, 1.1) × prompt_tokens`, simulating realistic estimate/actual variance. No API key required — reviewers and tests always work without network access.

**ClaudeProvider** (opt-in): activated by setting `USE_REAL_LLM=true` and providing `ANTHROPIC_API_KEY`. Uses `anthropic.messages.count_tokens()` for estimates and `anthropic.messages.create()` for generation, reading actual token counts from `response.usage`.

Provider selection is done at startup via `get_provider()` dependency injection in FastAPI, so the generate router is provider-agnostic.

---

## Key Tradeoffs

### 402 vs 429

`402 Payment Required` is used for quota exhaustion. `429 Too Many Requests` signals a time-based rate limit ("slow down, retry later"). Quota exhaustion is a credit problem, not a timing problem — the user needs to add credits, not wait. `402` communicates the right signal to callers and is semantically correct per RFC 9110.

### Debit Actual, Not Estimate

Users are charged what the AI actually consumed, not what was estimated. This is fairer: overestimates don't penalize users. The tradeoff is that actual credits can exceed the estimate, causing `used_credits` to momentarily exceed `quota` after settling. This overrun is bounded to at most one request's worth of credits and is documented in `QUOTA-05`.

### Lock Duration

The row lock is held only during the reserve transaction (T=0), which involves a single DB write with no external calls (~1 ms). The AI generation (100–2000 ms) happens outside any transaction. Holding the lock only during the lightweight phase maximizes concurrent throughput while preserving quota correctness.

### No Redis

Postgres row locking is sufficient for per-user quota enforcement. Adding Redis would require synchronizing two data stores to keep quota state consistent — more operational complexity for the same correctness guarantee. Postgres `SELECT FOR UPDATE` handles the concurrency natively.

---

## Known Limitation

If the settle transaction (T=2) fails after the AI has already generated text (e.g., the database crashes between T=1 and T=2), the user receives the generated text but their credits are not debited. This is an undercharge, not an overcharge. The `finally` block in the generate handler releases the reservation (`reserved_credits -= estimated_credits`) so subsequent requests are not blocked by a dangling reservation. The generation text has already been returned to the client.

Probability: low (requires a DB failure in a narrow window). Impact: bounded to one request per occurrence. A production system would mitigate with an outbox pattern or idempotent settle retry. This service documents the limitation rather than adding that complexity.

---

## Endpoint Reference

| Method | Path | Request Body | Success | Errors |
|--------|------|--------------|---------|--------|
| POST | `/users/` | `{quota: int, multiplier: float}` | 201 `UserResponse` (id, quota, multiplier, used_credits, reserved_credits) | 422 validation |
| PATCH | `/users/{user_id}` | `{quota?: int, multiplier?: float}` | 200 `UserResponse` | 404 user not found, 422 validation |
| POST | `/users/{user_id}/generate` | `{prompt: str}` | 200 `{text: str, usage: {prompt_tokens, completion_tokens, estimated_credits, actual_credits}}` | 402 quota exceeded, 404 user not found, 503 AI provider failure |
| GET | `/users/{user_id}/usage` | — | 200 `{user_id, quota, multiplier, used, reserved, remaining}` | 404 user not found |
| GET | `/users/{user_id}/usage/history` | `?limit=20&offset=0` | 200 `list[{id, prompt_tokens, completion_tokens, estimated_credits, actual_credits, status, created_at}]` | 404 user not found |

`remaining` in the usage response is computed server-side as `quota - used_credits - reserved_credits` and is never stored.

---

## Out of Scope / Future Work

- **Quota period reset**: monthly credit rollover; not in v1.
- **Multi-tenant auth / API keys**: `user_id` is in the path; no authentication layer.
- **Rate limiting beyond quota**: no per-second or per-minute limits.
- **Async generation / webhooks**: generation is synchronous; client blocks until text is returned.
- **Admin UI**: API only.
- **Outbox / settle retry**: would eliminate the undercharge known limitation.
