# AI Metering and Quota Service

## What This Is

A FastAPI service that wraps an AI text generation layer and enforces per-user credit quotas. Users submit prompts, the service estimates cost, checks quota, generates text, then debits actual token usage converted to credits via a per-user multiplier. Built as a Terrabase interview submission due 2026-06-29 9PM IST.

## Core Value

Correct per-user quota enforcement with Postgres row locking — the quota check, reservation, and debit must be race-safe even under concurrent requests from the same user.

## Requirements

### Validated

- [x] FastAPI app with clean route separation — Validated in Phase 1: Scaffold + User Config
- [x] Per-user quota and multiplier configuration (create/update) — Validated in Phase 1: Scaffold + User Config

### Active

- [ ] FastAPI app with clean route separation
- [ ] Per-user quota and multiplier configuration (create/update)
- [ ] Text generation endpoint (POST /users/{user_id}/generate)
- [ ] Provider abstraction: MockProvider (default) + ClaudeProvider (USE_REAL_LLM=true)
- [ ] Credit model: (prompt_tokens + completion_tokens) × multiplier
- [ ] Pre-generation token estimate (chars/4 heuristic for mock; count_tokens API for Claude)
- [ ] Postgres row lock (SELECT FOR UPDATE) during quota check + reservation
- [ ] Actual debit after generation settles
- [ ] Usage history table (one row per request, stores estimate vs actual)
- [ ] GET endpoint for current usage, remaining credits, config
- [ ] GET endpoint for usage history per user
- [ ] Clear error responses: 402 quota exceeded, 503 AI layer failure, 404 user not found
- [ ] Docker Compose: Postgres + app, single `docker-compose up` to run
- [ ] pytest suite covering all 9 required test scenarios
- [ ] Design document (Markdown in repo)

### Out of Scope

- Multi-tenant auth / API keys — single service, user_id in path
- Rate limiting beyond quota — not asked for
- Quota period reset (monthly rollover) — not in v1, noted in design doc
- Async generation / webhooks — synchronous only
- Redis or any second data store — Postgres row lock is sufficient
- Admin UI — API only

## Context

- Interview assignment from Terrabase; evaluated on clarity of tradeoffs, not feature breadth
- Deadline: 2026-06-29 9PM IST (~58 hours from project start)
- Ponytail mode active: minimum complexity, no over-engineering
- Postgres chosen for row-lock concurrency — makes SELECT FOR UPDATE native and clean
- Mock AI uses char/4 token heuristic + random ±10% completion variance to simulate estimate/actual gap
- Real Claude AI uses `anthropic.messages.count_tokens()` for estimate; actual from `response.usage`

## Constraints

- **Language/Framework**: Python + FastAPI — specified by assignment
- **Storage**: Postgres via Docker Compose — reviewer must be able to `docker-compose up` and run
- **Complexity**: Ponytail full — no abstractions beyond what's tested
- **Timeline**: ~58 hours total, ~10-15 hrs available

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Postgres row lock (SELECT FOR UPDATE) | Eliminates concurrent quota overrun race without Redis | — Pending |
| Provider abstraction via ABC | Assignment explicitly lists "changing AI provider" as future-change scenario | — Pending |
| Mock default, Claude opt-in via env | Reviewer can run without API key; shows abstraction | — Pending |
| Credits = total_tokens × multiplier | Simplest deterministic model; explicit and auditable | — Pending |
| Debit actual, not estimate | Fairest to user; overrun possible but bounded by single request | — Pending |
| SQLAlchemy ORM + asyncpg | Standard, async-native, easy to swap to another DB | — Pending |
| 402 for quota exceeded | More semantically correct than 429 (rate limit); design doc explains | — Pending |

## Concurrency Model

```
T=0  Request arrives → BEGIN TX → SELECT user FOR UPDATE
T=0  Check: used_credits + estimated_credits ≤ quota  → else 402
T=0  reserved_credits += estimated_credits → COMMIT (lock released)
T=1  AI layer generates → returns actual token counts
T=2  BEGIN TX → SELECT user FOR UPDATE
T=2  reserved_credits -= estimated_credits
T=2  used_credits += actual_credits → COMMIT
T=2  Write usage_log row (estimate, actual, credits_debited)
```

Concurrent requests for same user queue at the DB lock. Lock held only during the lightweight check+reserve — not during generation. Generation is outside the transaction.

## Concrete Quota Example (for design doc)

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

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-27 — Phase 1 complete (scaffold, user CRUD endpoints, Docker Compose)*
