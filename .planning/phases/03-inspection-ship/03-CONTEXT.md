# Phase 3: Inspection + Ship - Context

**Gathered:** 2026-06-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver the inspection endpoints, the full pytest suite, and all shipping artifacts so a reviewer can run, inspect, and understand the project end-to-end.

Deliverables:
- `GET /users/{user_id}/usage` — returns current quota state (used, reserved, remaining, quota, multiplier)
- `GET /users/{user_id}/usage/history` — returns paginated usage log rows
- `tests/` — pytest suite covering all 9 required scenarios from spec
- `DESIGN.md` — comprehensive design doc (concurrency model, tradeoffs, example walkthrough, endpoint reference, ASCII diagram)
- `README.md` — setup + test instructions
- Docker Compose already done (docker-compose.yml + Dockerfile both exist and are functional)

Not in this phase: new endpoints beyond inspection, new ORM models, changes to the generate flow.

</domain>

<decisions>
## Implementation Decisions

### GET /usage Response Schema
- **D-01:** New `UsageResponse` schema — dedicated, not extending `UserResponse`. Fields: `quota`, `multiplier`, `used`, `reserved`, `remaining`. Drops the `_credits` suffix (redundant in context) and `id`. Matches REQUIREMENTS.md INSPECT-01 wording exactly.
- **D-02:** `remaining` is computed server-side: `quota - used_credits - reserved_credits`. Not stored — always fresh from the row.

### GET /usage/history Response Schema
- **D-03:** Returns a flat list of `UsageLogEntry` objects — no envelope wrapper (`{items, total}` not needed). Fields per row: `id`, `prompt_tokens`, `completion_tokens`, `estimated_credits`, `actual_credits`, `status`, `created_at`. Excludes `user_id` (redundant — user is already in the path).
- **D-04:** Pagination via query params `?limit=20&offset=0`. Default limit 20, max 100. FastAPI `Query(20, ge=1, le=100)` and `Query(0, ge=0)`.

### The 9 Required Test Scenarios
- **D-05:** The 9 required scenarios from the assignment spec (used verbatim as test names):
  1. Successful generation and usage recording
  2. Credit calculation using a per-user multiplier
  3. Different users receiving different quota or multiplier behavior
  4. Quota enforcement when a user has enough remaining credits
  5. Quota-exceeded behavior when a user does not have enough remaining credits
  6. Behavior when the AI generation layer fails
  7. Retrieval of current usage and remaining allowance
  8. Behavior when actual usage differs from the pre-request estimate
  9. Behavior for near-simultaneous requests from the same user

### Test Infrastructure
- **D-06:** Test setup: `pytest-asyncio` + `httpx.AsyncClient` + `app.dependency_overrides[get_db]` pointing at a separate `metering_test` Postgres DB. Session-scoped fixture creates tables at start, drops them after. No SQLite — `SELECT FOR UPDATE` must be exercised against real Postgres (the core value prop).
- **D-07:** Concurrent test (scenario 9) uses `asyncio.gather` to fire two generate requests simultaneously. Assert combined `used` ≤ user quota after both settle (one may 402, neither should overrun). MockProvider used — deterministic, fast.

### DESIGN.md
- **D-08:** Comprehensive design doc — not a terse memo. Must include:
  - Concurrency model: SELECT FOR UPDATE flow with T=0/T=1/T=2 sequence, reserve/generate/settle pattern
  - Credit formula: `(prompt_tokens + completion_tokens) × multiplier`
  - Provider abstraction: ABC, MockProvider default, ClaudeProvider opt-in via `USE_REAL_LLM=true`
  - Key tradeoffs: 402 vs 429, debit actual not estimate, quota overrun bound (QUOTA-05)
  - Known limitation: settle-TX failure → AI generates but credits not debited (undercharge) — from D-17, Phase 2
  - Alice quota example (the full walkthrough from PROJECT.md)
  - ASCII architecture diagram: Client → FastAPI → Postgres + AI Provider
  - Per-endpoint reference table (method, path, success response, error responses)

### Claude's Discretion
- `user_id` excluded from history rows (redundant — queried by user)
- Exact conftest.py fixture structure (session-scoped engine, function-scoped db + override)
- Test DATABASE_URL (e.g., `postgresql+asyncpg://postgres:postgres@localhost:5432/metering_test`)
- README structure (setup, env vars table, running tests, sample curl commands)
- DESIGN.md word count and exact formatting

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project decisions and constraints
- `.planning/PROJECT.md` — Key Decisions table (credit formula, concurrency model diagram with Alice example, SELECT FOR UPDATE pattern, 402 semantics). Must read before writing DESIGN.md or any test assertions.
- `.planning/REQUIREMENTS.md` — INSPECT-01, INSPECT-02, INFRA-01, INFRA-02, INFRA-03, INFRA-04 (exact wording and traceability). The 9 scenarios in D-05 above are the authoritative list for INFRA-02.

### Phase scope
- `.planning/ROADMAP.md` — Phase 3 success criteria and boundaries.

### Prior phase context
- `.planning/phases/02-generation-quota-usage/02-CONTEXT.md` — D-17 (settle-TX failure known limitation for DESIGN.md), D-19 through D-22 (UsageLog schema), D-03 (remaining_credits lives in GET /usage not generate response).
- `.planning/phases/01-scaffold-user-config/01-CONTEXT.md` — D-01 through D-04 (project layout), D-08/D-09 (Docker Compose + healthcheck pattern — already done).

### Existing code
- `app/models.py` — `User` and `UsageLog` ORM models. All columns already exist; no new models needed.
- `app/schemas.py` — `UserResponse` and `UsageDetail` exist. Add `UsageResponse` and `UsageLogEntry` here.
- `app/routers/users.py` — Router pattern to follow for `app/routers/inspection.py` (or add to users.py).
- `app/database.py` — `get_db()` — the override point for test DB injection.
- `app/main.py` — Include inspection router here.
- `docker-compose.yml` — Already functional, no changes needed.
- `Dockerfile` — Already functional, no changes needed.

No external specs — requirements and the 9 test scenarios fully captured in decisions above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/database.py:get_db()` — `AsyncSession` via `Depends(get_db)`. Override in conftest: `app.dependency_overrides[get_db] = override_get_db`.
- `app/models.py:User` — All fields needed for `UsageResponse` exist (`quota`, `multiplier`, `used_credits`, `reserved_credits`). `remaining` is computed.
- `app/models.py:UsageLog` — All fields for history rows already exist.
- `app/routers/users.py` — `select(User).where(User.id == user_id)` + `scalar_one_or_none()` → 404 pattern to reuse verbatim.

### Established Patterns
- 404: `result.scalar_one_or_none()` → `if user is None: raise HTTPException(status_code=404, ...)`.
- All routers: `APIRouter(prefix="/users", tags=[...])`, `Depends(get_db)`.
- Schemas: `model_config = {"from_attributes": True}` for ORM-backed responses.

### Integration Points
- `app/main.py` — `app.include_router(inspection.router)` alongside existing routers.
- `app/schemas.py` — Add `UsageResponse` and `UsageLogEntry` here (follow existing schema pattern).
- `tests/conftest.py` — New file. Session-scoped engine pointing at `metering_test`, function-scoped `db` session + `app.dependency_overrides` injection.

</code_context>

<specifics>
## Specific Ideas

- The 9 test scenario names from D-05 should be used verbatim as pytest test function docstrings or test names — the spec uses these exact phrases.
- Scenario 8 (actual differs from estimate): MockProvider's `±10%` completion variance (D-09, Phase 2) guarantees this naturally — use it in the test to show `actual_credits != estimated_credits` in the log.
- Scenario 3 (different users): create two users with different quotas/multipliers and assert their usage rows are independent.
- The Alice example in PROJECT.md (1000-credit quota, 44-char prompt, 402 then quota raise + success) should be reproduced verbatim in DESIGN.md for concreteness.
- DESIGN.md should be in the repo root, not in a docs/ subdir — simpler for reviewer to find.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 3-Inspection + Ship*
*Context gathered: 2026-06-27*
