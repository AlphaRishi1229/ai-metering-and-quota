# Phase 3: Inspection + Ship - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-27
**Phase:** 3-Inspection + Ship
**Areas discussed:** Usage endpoint schemas, The 9 test scenarios, DESIGN.md scope

---

## Usage Endpoint Schemas

### GET /usage schema

| Option | Description | Selected |
|--------|-------------|----------|
| New UsageResponse schema | Dedicated schema with clean names: used, reserved, remaining, quota, multiplier. Drops id and _credits suffix. | ✓ |
| Extend UserResponse | Add remaining as computed property on UserResponse. Keeps _credits suffix. | |

**User's choice:** New UsageResponse schema
**Notes:** Matches REQUIREMENTS.md wording exactly; cleaner API surface.

### GET /usage/history response shape

| Option | Description | Selected |
|--------|-------------|----------|
| Flat list, all log fields | [{id, prompt_tokens, completion_tokens, estimated_credits, actual_credits, status, created_at}, ...]. No envelope. | ✓ |
| Wrapped with total count | {items: [...], total: N}. Enables client-side pagination math without a second query. | |

**User's choice:** Flat list, all log fields
**Notes:** Simpler to consume and test; ponytail — no premature pagination wrapper.

### Pagination style

| Option | Description | Selected |
|--------|-------------|----------|
| ?limit=20&offset=0 | Standard limit/offset. Default 20, max 100. | ✓ |
| ?page=1&page_size=20 | Page-based. Equivalent under the hood. | |

**User's choice:** ?limit=20&offset=0
**Notes:** Standard, reviewer-expected pattern.

---

## The 9 Test Scenarios

### Scenario list confirmation

| Option | Description | Selected |
|--------|-------------|----------|
| Claude's guessed list | Create user, update quota, generate success, 402 quota exceeded, 402 no config, 503 AI failure, concurrent serializes, GET usage, GET history | |
| User-provided spec list | Exact 9 scenarios from the original assignment spec | ✓ |

**User's choice:** Provided the exact 9 scenarios from the spec:
1. Successful generation and usage recording
2. Credit calculation using a per-user multiplier
3. Different users receiving different quota or multiplier behavior
4. Quota enforcement when a user has enough remaining credits
5. Quota-exceeded behavior when a user does not have enough remaining credits
6. Behavior when the AI generation layer fails
7. Retrieval of current usage and remaining allowance
8. Behavior when actual usage differs from the pre-request estimate
9. Behavior for near-simultaneous requests from the same user

**Notes:** These differ from Claude's initial guess — notably scenario 2 (multiplier math explicitly), scenario 3 (user isolation), and scenario 8 (estimate/actual gap). User said "make sure we add these too."

### Test DB strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Separate test DB, same asyncpg stack | pytest-asyncio + httpx.AsyncClient + dependency_overrides + metering_test Postgres DB | ✓ |
| Mock DB with SQLite in-memory | No Postgres needed, but SELECT FOR UPDATE won't be exercised | |

**User's choice:** Separate test DB, same asyncpg stack
**Notes:** SELECT FOR UPDATE is the core value prop — must be tested against real Postgres.

### Concurrent request test approach

| Option | Description | Selected |
|--------|-------------|----------|
| asyncio.gather two requests | Fire two requests simultaneously. Assert combined credits ≤ quota. | ✓ |
| Only test lock mechanism in code | Code inspection, skip real concurrency test | |

**User's choice:** asyncio.gather two requests
**Notes:** Proves the SELECT FOR UPDATE path actually runs end-to-end.

---

## DESIGN.md Scope

### Depth

| Option | Description | Selected |
|--------|-------------|----------|
| Technical memo, focused | ~300-500 words. Concurrency model, tradeoffs, known limitation. | |
| More comprehensive | Architecture diagram, full quota example, per-endpoint reference. | ✓ |

**User's choice:** More comprehensive
**Notes:** Interview submission — worth the extra depth.

### Additional content

| Option | Description | Selected |
|--------|-------------|----------|
| Alice quota example | Full walkthrough from PROJECT.md | ✓ |
| ASCII architecture diagram | Client → FastAPI → Postgres + AI Provider | ✓ |
| Per-endpoint reference | Table of endpoints with responses | ✓ |

**User's choice:** All three included
**Notes:** All three selected simultaneously.

---

## Claude's Discretion

- `user_id` excluded from history rows (redundant in path context)
- Exact conftest.py fixture structure (session-scoped engine, function-scoped db + override)
- Test DATABASE_URL value
- README structure (setup, env vars, sample curl commands)
- DESIGN.md exact word count and formatting

## Deferred Ideas

None — discussion stayed within phase scope.
