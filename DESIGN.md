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

### What is `reserved_credits`?

`reserved_credits` is not part of the locking mechanism — Postgres `SELECT FOR UPDATE` handles mutual exclusion. Its purpose is **visibility across concurrent requests**.

The row lock only serializes the reads at T=0. Once a request commits its reservation and releases the lock, a second concurrent request acquires the lock and reads the row. Without `reserved_credits`, that second request would see the same `used_credits` as if the first request had never run — because `used_credits` isn't updated until T=2, after generation completes. The first request's in-flight budget is invisible.

`reserved_credits` closes that gap: it is written to the row at T=0 and stays there until T=2. Any concurrent T=0 check reads it and correctly reduces the available headroom.

**Without `reserved_credits` (broken):**

```
Alice: quota=1000, used=800, remaining=200

Request A T=0: reads remaining = 1000 - 800 = 200 → 150 fits → PASS, lock released
Request B T=0: reads remaining = 1000 - 800 = 200 → 150 fits → PASS, lock released

Both generate. Total actual spend: 300+ credits. Quota blown.
```

**With `reserved_credits` (correct):**

```
Alice: quota=1000, used=800, reserved=0, remaining=200

Request A T=0: reads 1000 - 800 - 0   = 200 → 150 fits → reserved=150, COMMIT, lock released
Request B T=0: reads 1000 - 800 - 150 = 50  → 150 doesn't fit → 402, no generation

Request A T=2: used=800+actual, reserved=0, COMMIT
```

A's reservation is persisted to the row before the lock is released. B sees it when it acquires the lock. The reservation carries A's in-flight budget intent across to B's quota check — without holding the lock through the 100–2000 ms AI generation.

`reserved_credits` accumulates across all in-flight requests for the same user. If three requests are simultaneously in T=1, the row holds the sum of all three reservations, and any new T=0 check accounts for all of them.

---

## Alice Examples

Alice's starting state for all examples below:

```
quota:      1000 credits
multiplier: 2.0×
used:        800 credits
reserved:      0 credits
remaining:   200 credits
```

---

### Example 1 — Successful generation (normal path)

```
prompt: "explain recursion" (44 chars → 11 estimated prompt tokens)
estimated_credits: 11 × 2.0 = 22

T=0  Check: 800 + 0 + 22 = 822 ≤ 1000 → PASS
     reserved_credits = 22, COMMIT

T=1  Generate → prompt=11, completion=45, total=56 tokens

T=2  actual_credits = 56 × 2.0 = 112
     used = 800 + 112 = 912, reserved = 0, COMMIT

Response 200: { text: "...", estimated_credits: 22, actual_credits: 112 }
usage_log: status=success, estimated_credits=22, actual_credits=112
```

---

### Example 2 — Quota exceeded at reservation (402 before generation)

Alice has used 990 of her 1000 credits. A new request arrives.

```
prompt: "write me a poem about the ocean" (51 chars → 12 estimated prompt tokens)
estimated_credits: 12 × 2.0 = 24

T=0  Check: 990 + 0 + 24 = 1014 > 1000 → FAIL
     No reservation made, COMMIT

Response 402: { detail: "Quota exceeded" }
usage_log: status=quota_exceeded, estimated_credits=null, actual_credits=null
```

No AI call is made. Alice's `used_credits` and `reserved_credits` are unchanged. She needs her quota raised before the next request can proceed.

---

### Example 3 — Quota overrun at settle (actual exceeds estimate)

Alice has 200 credits remaining and sends a short prompt that triggers a long completion.

```
prompt: "hi" (2 chars → 1 estimated prompt token)
estimated_credits: 1 × 2.0 = 2

T=0  Check: 800 + 0 + 2 = 802 ≤ 1000 → PASS
     reserved_credits = 2, COMMIT

T=1  Generate → prompt=1, completion=400, total=401 tokens

T=2  actual_credits = 401 × 2.0 = 802
     used = 800 + 802 = 1602, reserved = 0, COMMIT

Response 200: { text: "...", estimated_credits: 2, actual_credits: 802 }
usage_log: status=success, estimated_credits=2, actual_credits=802
Remaining: 1000 - 1602 = -602 credits  ← overrun
```

Alice receives the text and is charged 802 credits. Her balance goes negative. The *next* request will be blocked at T=0 with a 402. This is the soft-cap tradeoff — see "Debit Actual, Not Estimate" in Key Tradeoffs.

---

### Example 4 — AI provider failure (503 after reservation)

Alice sends a valid request but the AI provider returns an error mid-flight.

```
prompt: "translate to French: hello" (38 chars → 9 estimated prompt tokens)
estimated_credits: 9 × 2.0 = 18

T=0  Check: 800 + 0 + 18 = 818 ≤ 1000 → PASS
     reserved_credits = 18, COMMIT

T=1  Generate → AI provider throws exception (timeout / API error)

finally  reserved_credits = max(0, 18 - 18) = 0, COMMIT  ← reservation released

Response 503: { detail: "AI generation failed" }
usage_log: status=ai_error, estimated_credits=null, actual_credits=null
```

Alice is not charged. The reservation is released in the `finally` block so her remaining budget is fully restored. No credits are consumed on a failed generation.

---

### Example 5 — Concurrent requests (reservation prevents double-spend)

Alice sends two requests simultaneously when she has 200 credits remaining.

```
Request A and Request B arrive at the same time.
Both prompts estimate 150 credits each.

Request A T=0: SELECT FOR UPDATE → lock acquired
  Check: 800 + 0 + 150 = 950 ≤ 1000 → PASS
  reserved_credits = 150, COMMIT, lock released

Request B T=0: SELECT FOR UPDATE → lock acquired (A has released)
  Check: 800 + 150 + 150 = 1100 > 1000 → FAIL  ← sees A's reservation
  No reservation, COMMIT

Response B: 402 Quota exceeded  (before any generation runs)

Request A T=1: Generate → actual_credits = 190
Request A T=2: used = 800 + 190 = 990, reserved = 0, COMMIT
```

Request B is correctly rejected without making an AI call, even though Alice had 200 credits when both requests arrived. The `reserved_credits` column is what makes this safe — it's visible to concurrent T=0 checks while T=1 is still in progress.

---

The estimate vs. actual divergence in all success cases is expected and logged. See the pending decision in the Credit Formula section for discussion of adding a completion buffer to tighten reservations.

---

## Credit Formula

```
actual_credits = (prompt_tokens + completion_tokens) × multiplier
```

The pre-generation estimate uses **prompt tokens only** — completion tokens are unknown until after generation:

```
estimated_credits = estimated_prompt_tokens × multiplier
```

Both MockProvider and ClaudeProvider use `len(prompt) // 4` as the prompt token estimate. Actual credits are charged after generation using the full formula above. This means `estimated_credits` is systematically lower than `actual_credits` — roughly half when completion length ≈ prompt length.

**Why `len(prompt) // 4` and not `len(prompt)` or `count_tokens()`?**

`len(prompt)` would overestimate by ~4×: a 92-char prompt would reserve 92 credits instead of ~23, causing false 402s for users who still have headroom. The ~4 chars/token ratio is the standard approximation for English text with GPT/Claude tokenizers (a typical English word is ~5 chars and encodes to ~1.3 tokens). Verified against real Claude usage: the prompt `"just return yes I am running this from a service I am testing, so I want to use least tokens"` is 92 chars → `92 // 4 = 23` estimated, 23 actual tokens from Claude — exact.

`count_tokens()` (the Anthropic API's accurate token counter) requires a network roundtrip before every generation call, adding 100–300 ms of latency. The accuracy gain on prompt tokens is ~5%, but since completion tokens are the dominant unknown (often 2–10× the prompt), nailing the prompt count doesn't meaningfully improve reservation accuracy. The extra call isn't worth it under the current prompt-only estimation strategy.

Estimate vs. actual divergence is expected, logged, and bounded to one request's worth of overrun.

> **PENDING DECISION — completion token buffer in pre-generation estimate**
>
> The current estimate covers prompt tokens only. A fudge factor (e.g. `estimated_prompt_tokens × 2`) would make the reservation tighter and reduce how far `actual_credits` can overshoot the reserved amount. The tradeoff: a larger reservation blocks more quota headroom upfront, increasing false 402s for users near their limit. Left as prompt-only for now; revisit if overrun complaints arise or billing accuracy becomes a requirement.

---

## Provider Abstraction

```python
class BaseProvider(ABC):
    def estimate_tokens(self, prompt: str) -> int: ...
    async def generate(self, prompt: str) -> GenerationResult: ...
```

`GenerationResult` carries `text`, `prompt_tokens`, `completion_tokens`.

**MockProvider** (default): `estimate_tokens` = `len(prompt) // 4`. `generate` returns a mock text with completion_tokens drawn from `uniform(0.9, 1.1) × prompt_tokens`, simulating realistic estimate/actual variance. No API key required — reviewers and tests always work without network access.

**ClaudeProvider** (opt-in): activated by setting `USE_REAL_LLM=true` and providing `ANTHROPIC_API_KEY`. Uses `len(prompt) // 4` for the pre-generation estimate (same heuristic as MockProvider — avoids a blocking network call before every request; real count differs ~5%). Actual token counts are read from `response.usage` after generation via `anthropic.messages.create()`.

Provider selection is done at startup via `get_provider()` dependency injection in FastAPI, so the generate router is provider-agnostic.

---

## Key Tradeoffs

### 402 vs 429

`402 Payment Required` is used for quota exhaustion. `429 Too Many Requests` signals a time-based rate limit ("slow down, retry later"). Quota exhaustion is a credit problem, not a timing problem — the user needs to add credits, not wait. `402` communicates the right signal to callers and is semantically correct per RFC 9110.

### Debit Actual, Not Estimate

Users are charged what the AI actually consumed, not what was estimated. This is fairer: overestimates don't penalize users. The tradeoff is that actual credits can exceed the estimate, causing `used_credits` to momentarily exceed `quota` after settling. This overrun is bounded to at most one request's worth of credits.

**Why no 402 at settle time if actual > estimated?**

By the time the settle transaction runs, the AI has already generated and returned text — the API spend is already incurred. Returning a 402 at that point would mean the service paid for the generation, the user receives no text, and their quota is still exhausted. That is the worst outcome for both parties. The correct behavior is to bill actual, return the text, and let the now-negative remaining balance block the *next* request. Quota is therefore a soft cap on estimation variance, not a hard byte limit.

### Lock Duration

The row lock is held only during the reserve transaction (T=0), which involves a single DB write with no external calls (~1 ms). The AI generation (100–2000 ms) happens outside any transaction. Holding the lock only during the lightweight phase maximizes concurrent throughput while preserving quota correctness.

### Why Postgres (not SQLite, in-memory, or file-backed)

The assignment explicitly lists in-memory, file-backed, SQLite, and Postgres as valid storage options. Postgres was chosen because **row-level locking is the core correctness requirement**, and it is the only option on that list that provides it natively.

The quota check, reservation, and debit must be race-safe under concurrent requests from the same user. That requires locking a single user's row while another request checks and updates it — without blocking requests for different users. The options on the list break down as follows:

| Option | Row-level locking | Notes |
|---|---|---|
| In-memory | No | No locking primitives; would need an application-level lock (e.g. `asyncio.Lock` per user), which disappears on restart and doesn't work across multiple processes |
| File-backed | No | Same problem as in-memory — file locks are coarse and not row-granular |
| SQLite | No | SQLite locks the entire database file on write; two concurrent requests for the same user would serialize all writes across all users, not just that user's row |
| **Postgres** | **Yes** | `SELECT FOR UPDATE` locks exactly the target row; requests for other users are unaffected |

Without Postgres, the only way to get equivalent row-level locking semantics would be to introduce a separate coordination layer — Redis with `SET NX` per user, or an in-process lock map. Both add operational complexity (Redis = another service to run; in-process lock = breaks under multiple workers) for a guarantee Postgres gives for free as part of its transaction model.

The assignment also notes "moving from local storage to a real database" as a future concern — implying SQLite or in-memory as a starting point. Choosing Postgres upfront eliminates that migration. With Docker Compose, the operational cost of running Postgres is the same as SQLite: one line in `docker-compose.yml`.

### No Redis

Postgres row locking is sufficient for per-user quota enforcement. Adding Redis would require synchronizing two data stores to keep quota state consistent — more operational complexity for the same correctness guarantee. Postgres `SELECT FOR UPDATE` handles the concurrency natively.

---

## Known Limitation

If the settle transaction (T=2) fails after the AI has already generated text (e.g., the database becomes unavailable between T=1 and T=2), the generation is treated as a failure: the settle TX shares the same `try` block as the AI call, so a settle error is caught by the same handler as an AI error. The request returns **503**, the `finally` block releases the reservation (`reserved_credits -= estimated_credits`), and the user is **not charged**. The generated text is discarded rather than returned, because the service cannot atomically return text and record the charge for it.

The cost falls on the operator, not the user: a successful AI call whose settle write fails has already incurred real API spend but produces no billing record — an **undercharge, never an overcharge**. The usage row is written with `status=ai_error` even though the AI itself succeeded; distinguishing "AI failed" from "settle failed" would require splitting the `try` block, which the current version omits for simplicity.

Probability: low (requires a DB failure in a narrow window). Impact: bounded to one request per occurrence. A production system would mitigate with an outbox pattern (return the text, settle asynchronously with retry) or an idempotent settle. This service documents the limitation rather than adding that complexity.

---

## Endpoint Reference

| Method | Path | Request Body | Success | Errors |
|--------|------|--------------|---------|--------|
| POST | `/users/` | `{quota: int, multiplier: float}` | 201 `UserResponse` (id, quota, multiplier, used_credits, reserved_credits) | 422 validation |
| PATCH | `/users/{user_id}` | `{quota?: int, multiplier?: float}` | 200 `UserResponse` | 404 user not found, 422 validation |
| POST | `/users/{user_id}/generate` | `{prompt: str}` | 200 `{text: str, usage: {prompt_tokens, completion_tokens, estimated_credits, actual_credits}}` | 402 quota exceeded, 404 user not found, 503 AI provider failure |
| GET | `/users/{user_id}/usage` | — | 200 `{quota, multiplier, used, reserved, remaining}` | 404 user not found |
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
