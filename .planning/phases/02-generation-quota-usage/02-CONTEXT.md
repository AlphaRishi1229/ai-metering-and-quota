# Phase 2: Generation + Quota + Usage - Context

**Gathered:** 2026-06-27
**Status:** Ready for planning

<domain>
## Phase Boundary

The generate endpoint: accepts a prompt, estimates token cost, checks quota under a Postgres row lock, reserves the estimate, generates text via the active AI provider, debits actual token usage, and records the request in the usage log.

Deliverables:
- `POST /users/{user_id}/generate` — returns text + usage summary
- `app/providers/` package — abstract base + MockProvider + ClaudeProvider
- `UsageLog` ORM model and table
- Quota enforcement: SELECT FOR UPDATE, reserve → generate → settle
- Error responses: 402 (quota exceeded / no config), 503 (AI failure), 404 (user not found)

Not in this phase: GET inspection endpoints, pytest suite, design doc, Docker Compose — those are Phase 3.

</domain>

<decisions>
## Implementation Decisions

### Generate Response Schema
- **D-01:** Response shape: `{ text, usage: { prompt_tokens, completion_tokens, estimated_credits, actual_credits } }`. Nested `usage` object matches Anthropic/OpenAI convention.
- **D-02:** Root field is `text` (not `generated_text`, not `content`).
- **D-03:** No `remaining_credits` in the generate response — caller uses `GET /users/{id}/usage` (Phase 3) for that.

### Provider Abstraction
- **D-04:** Abstract base class in `app/providers/base.py` with two methods:
  - `estimate_tokens(prompt: str) -> int` — called before quota check (T=0)
  - `generate(prompt: str) -> GenerationResult` — called after reservation (T=1)
- **D-05:** `GenerationResult` is a `@dataclass` with `text: str`, `prompt_tokens: int`, `completion_tokens: int`. Internal type — no Pydantic overhead.
- **D-06:** File layout: `app/providers/__init__.py`, `app/providers/base.py` (ABC), `app/providers/mock.py`, `app/providers/claude.py`.
- **D-07:** Injected via FastAPI `Depends(get_provider)` — consistent with the `get_db()` pattern from Phase 1. `get_provider()` reads `settings.USE_REAL_LLM` to select the implementation.

### MockProvider Behavior
- **D-08:** `estimate_tokens(prompt)` → `len(prompt) // 4` (chars/4 heuristic, from PROJECT.md).
- **D-09:** `generate(prompt)` → returns a fixed string like `"Mock response for: {prompt[:50]}"`. Actual tokens: `prompt_tokens = len(prompt) // 4`, `completion_tokens` = random value ±10% of the prompt estimate to simulate estimate/actual gap.

### ClaudeProvider Behavior
- **D-10:** `estimate_tokens(prompt)` → `anthropic.messages.count_tokens(...)` API call (from PROJECT.md).
- **D-11:** `generate(prompt)` → `anthropic.messages.create(...)`. `prompt_tokens = response.usage.input_tokens`, `completion_tokens = response.usage.output_tokens`.
- **D-12:** `USE_REAL_LLM=true` env var activates ClaudeProvider. `ANTHROPIC_API_KEY` must also be set. Both read via `pydantic-settings` `BaseSettings`.

### Quota Enforcement Flow
- **D-13:** Concurrency model from PROJECT.md is locked:
  1. `BEGIN TX → SELECT user FOR UPDATE`
  2. Check `used_credits + estimated_credits ≤ quota` → else 402
  3. `reserved_credits += estimated_credits → COMMIT` (lock released)
  4. AI generates (outside any transaction)
  5. `BEGIN TX → SELECT user FOR UPDATE`
  6. `reserved_credits -= estimated_credits; used_credits += actual_credits → COMMIT`
  7. Write `UsageLog` row
- **D-14:** Credits formula: `credits = total_tokens × multiplier` (where `total_tokens = prompt_tokens + completion_tokens`). Already decided in PROJECT.md.
- **D-15:** 402 for quota exceeded (`used_credits + estimated_credits > quota`). 402 also for user with no quota config (no row found in users table). Messages must be distinct.

### Error Handling and Reservation Release
- **D-16:** Reservation always released in a `try/finally` block. Pattern:
  ```
  try:
      reserve()
      result = generate()
      settle(result)
  except AIError:
      # reservation released in finally; log actual tokens if available
      raise HTTPException(503)
  finally:
      if reserved and not settled:
          release_reservation()
  ```
- **D-17:** If settle TX fails after successful generation: log the actual token counts at ERROR level, release the reservation (finally block), return 503. Document in DESIGN.md as known limitation: "AI generates but credits not debited (undercharge)". No retry, no dead-letter queue.
- **D-18:** GEN-05 (AI failure before generation) and GEN-06 (mid-request) are both handled by the same finally path — no credits debited.

### usage_log Schema
- **D-19:** `UsageLog` table columns: `id` (PK), `user_id` (FK → users), `prompt_tokens`, `completion_tokens`, `estimated_credits` (nullable BIGINT), `actual_credits` (nullable BIGINT), `status` (string: `success` / `quota_exceeded` / `ai_error`), `created_at` (timestamp with timezone, default now).
- **D-20:** No prompt text stored — credit ledger only.
- **D-21:** `estimated_credits` and `actual_credits` are NULL for failed rows (`quota_exceeded`, `ai_error`). Semantically clean — no credits were involved.
- **D-22:** `UsageLog` rows are written after settle completes for `success` rows. For `quota_exceeded` and `ai_error` rows, write before returning the error response.

### Claude's Discretion
- Exact model name for ClaudeProvider (e.g., `claude-haiku-4-5-20251001` — cheapest available for a demo)
- MockProvider completion length range (e.g., ±10% of prompt_tokens, minimum 10 tokens)
- Error message wording for 402 quota exceeded vs. 402 no config
- Whether `user_id` foreign key has `ON DELETE CASCADE` or `RESTRICT`

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project decisions and constraints
- `.planning/PROJECT.md` — Key Decisions table (SELECT FOR UPDATE pattern, credit formula, provider abstraction, 402 semantics, concurrency model diagram). MUST read before implementing the generate flow.
- `.planning/REQUIREMENTS.md` — GEN-01 through GEN-06, QUOTA-01 through QUOTA-05, USAGE-01 through USAGE-03 (exact wording and acceptance criteria).

### Phase scope
- `.planning/ROADMAP.md` — Phase 2 success criteria and boundaries.

### Prior phase context
- `.planning/phases/01-scaffold-user-config/01-CONTEXT.md` — Established patterns: project layout (D-01 through D-04), PATCH semantics (D-05 through D-07), DB bootstrap (D-08 through D-10), validation rules (D-11 through D-13), Claude's discretion items.

### Existing code
- `app/models.py` — `User` ORM model. `used_credits` and `reserved_credits` columns already exist. `UsageLog` model must be added here.
- `app/database.py` — `get_db()` session factory. `Depends(get_provider)` follows the same pattern.
- `app/routers/users.py` — Router pattern to follow for `app/routers/generate.py`.
- `app/config.py` — `BaseSettings` subclass. Add `USE_REAL_LLM: bool = False` and `ANTHROPIC_API_KEY: str = ""` here.

No external specs — requirements fully captured in decisions above and referenced planning files.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/database.py:get_db()` — `AsyncSession` via `Depends(get_db)`. `get_provider()` follows identical pattern.
- `app/models.py:User` — Already has `used_credits: BigInteger` and `reserved_credits: BigInteger` with `default=0`. No schema migration needed for Phase 2 user columns.
- `app/config.py:Settings` — Add `USE_REAL_LLM: bool = False` and `ANTHROPIC_API_KEY: str = ""` fields. Reads from env or `.env` automatically.
- `app/routers/users.py` — Router structure to mirror in `app/routers/generate.py` (`APIRouter`, `Depends(get_db)`, `HTTPException` pattern).

### Established Patterns
- `SELECT ... WHERE User.id == user_id` + `scalar_one_or_none()` → 404 if None. Same in generate router.
- `db.commit()` + `db.refresh(obj)` for writes. Settle step follows same pattern.
- Pydantic `Field(gt=0)` for validated inputs. Prompt body can be `class GenerateRequest(BaseModel): prompt: str = Field(min_length=1)`.

### Integration Points
- `app/main.py` — Include `generate.router` alongside `users.router`. `Base.metadata.create_all` in lifespan will auto-create `usage_log` table once `UsageLog` model is imported.
- `app/models.py` — Add `UsageLog` model here (not a separate file — follows Phase 1 pattern).

</code_context>

<specifics>
## Specific Ideas

- The `usage` nesting in the response mirrors Anthropic's own API response structure — deliberately chosen for familiarity.
- The `finally` reservation release is the key correctness property: no stuck reservations under any failure path.
- MockProvider should return deterministic enough output that tests can assert on it (e.g., fixed prefix "Mock response for: ..." makes response text predictable).

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 2-Generation + Quota + Usage*
*Context gathered: 2026-06-27*
