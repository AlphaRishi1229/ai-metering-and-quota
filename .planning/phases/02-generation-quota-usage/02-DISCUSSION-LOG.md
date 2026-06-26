# Phase 2: Generation + Quota + Usage - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-27
**Phase:** 02-Generation + Quota + Usage
**Areas discussed:** Generate response shape, Provider ABC structure, usage_log schema, Error handling on settle failure

---

## Generate Response Shape

| Option | Description | Selected |
|--------|-------------|----------|
| Tokens + credits only | `{ text, usage: { prompt_tokens, completion_tokens, estimated_credits, actual_credits } }` | ✓ |
| Add remaining_credits | Same + `remaining_credits` — caller knows balance without separate GET | |
| Just credits_debited | `{ text, credits_debited }` — minimal, hides token detail | |

**User's choice:** Tokens + credits only (recommended)

| Option | Description | Selected |
|--------|-------------|----------|
| Flat | All fields at root level | |
| Nested usage object | `{ text, usage: { ... } }` — matches Anthropic/OpenAI structure | ✓ |

**User's choice:** Nested `usage` object

| Option | Description | Selected |
|--------|-------------|----------|
| text | Short, unambiguous | ✓ |
| generated_text | More explicit | |
| content | Matches Anthropic messages.content | |

**User's choice:** `text`

---

## Provider ABC Structure

| Option | Description | Selected |
|--------|-------------|----------|
| Two methods | `estimate_tokens(prompt) -> int` + `generate(prompt) -> GenerationResult` | ✓ |
| One method + inline estimate | `generate` returns result; chars/4 estimate lives in router | |
| One method that does both | `generate` internally estimates then generates | |

**User's choice:** Two methods (matches concurrency model — called at different times)

| Option | Description | Selected |
|--------|-------------|----------|
| app/providers/ package | `base.py`, `mock.py`, `claude.py` | ✓ |
| app/ai/ package | Same structure, different name | |
| Flat app/providers.py | Single file with all three classes | |

**User's choice:** `app/providers/` package

| Option | Description | Selected |
|--------|-------------|----------|
| FastAPI dependency | `Depends(get_provider)` — consistent with `get_db()` | ✓ |
| Module-level singleton | Import directly, instantiated at module load | |
| App state | `request.app.state.provider` via lifespan | |

**User's choice:** FastAPI dependency `Depends(get_provider)`

| Option | Description | Selected |
|--------|-------------|----------|
| Simple dataclass | `@dataclass GenerationResult` | ✓ |
| Named tuple | `namedtuple('GenerationResult', ...)` | |
| Pydantic model | `class GenerationResult(BaseModel)` | |

**User's choice:** `@dataclass`

---

## usage_log Schema

| Option | Description | Selected |
|--------|-------------|----------|
| No — tokens only | Minimum spec; prompt text adds storage, reviewer cares about accounting | ✓ |
| Yes — store prompt | Useful for debugging; TEXT column, nullable | |
| Truncated prompt | First 500 chars | |

**User's choice:** No prompt text stored

| Option | Description | Selected |
|--------|-------------|----------|
| No — log successful only | Failed requests don't debit; history is a credit ledger | |
| Yes — log all with status | `status` column: success/quota_exceeded/ai_error | ✓ |

**User's choice:** Log all attempts with status column

| Option | Description | Selected |
|--------|-------------|----------|
| Nullable — NULL for failed rows | Semantically clean: no credits were involved | ✓ |
| Zero for failed rows | Simpler queries, less accurate semantics | |
| Estimate present, actual NULL | Store attempted estimate; actual NULL when generation never completed | |

**User's choice:** NULL for failed rows

---

## Error Handling on Settle Failure

| Option | Description | Selected |
|--------|-------------|----------|
| Log + re-raise 503, document in DESIGN.md | Log actual tokens at ERROR level; release reservation; 503; document undercharge | ✓ |
| Best-effort retry (1 attempt) | Sleep briefly, retry once, then log + 503 | |
| Write to dead-letter table | Background task picks up settle_retry rows; strong guarantee but out of scope | |

**User's choice:** Log + re-raise 503, document in DESIGN.md

| Option | Description | Selected |
|--------|-------------|----------|
| Always release in finally | `try/finally` covers all failure paths | ✓ |
| Release only on known error paths | Explicit `except` blocks | |

**User's choice:** Always release in `finally` block

---

## Claude's Discretion

- Exact Claude model name for ClaudeProvider (cheapest available for demo)
- MockProvider completion length range (±10% of prompt_tokens, minimum 10 tokens)
- Error message wording for 402 quota exceeded vs. 402 no config
- `user_id` FK constraint type (CASCADE vs RESTRICT)

## Deferred Ideas

None — discussion stayed within phase scope.
