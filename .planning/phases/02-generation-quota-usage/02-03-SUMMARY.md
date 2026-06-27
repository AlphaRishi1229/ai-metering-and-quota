---
phase: "02-generation-quota-usage"
plan: "03"
subsystem: "generate-endpoint"
tags: ["quota", "generation", "fastapi", "postgres", "select-for-update"]
dependency_graph:
  requires:
    - "02-01"  # providers package (BaseProvider, get_provider, MockProvider, ClaudeProvider)
    - "02-02"  # UsageLog model + generate schemas
  provides:
    - "POST /users/{user_id}/generate with full quota enforcement flow"
    - "UsageLog rows for success, quota_exceeded, ai_error"
  affects:
    - "app/main.py"
tech_stack:
  added: []
  patterns:
    - "async with db.begin() for isolated transactions (reserve TX + settle TX)"
    - "SELECT FOR UPDATE on User row to serialize concurrent quota checks"
    - "try/finally reservation release pattern"
key_files:
  created:
    - "app/routers/generate.py"
  modified:
    - "app/main.py"
decisions:
  - "quota_exceeded UsageLog written in separate TX outside reserve block — raise inside async with db.begin() triggers rollback, not commit"
  - "multiplier captured from reserve TX result; settle TX re-fetches user for fresh reserved_credits/used_credits"
  - "ai_error log and reservation release are best-effort (try/except) — DB-down path still returns 503"
metrics:
  duration: "69 seconds"
  completed: "2026-06-27"
  tasks_completed: 2
  tasks_total: 2
---

# Phase 2 Plan 03: Generate Endpoint Summary

**One-liner:** Race-safe POST /users/{id}/generate with SELECT FOR UPDATE reserve-generate-settle flow, three-state UsageLog (success/quota_exceeded/ai_error), and finally-block reservation release.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Implement generate router with full quota enforcement flow | 242d14a | app/routers/generate.py (created) |
| 2 | Wire generate router into main.py | 55c924d | app/main.py (modified) |

## What Was Built

`app/routers/generate.py` implements `POST /users/{user_id}/generate` with:

**Reserve TX (SELECT FOR UPDATE):** Fetches user with row lock, computes `estimated_credits = int(estimated_tokens * multiplier)`, checks `remaining = quota - used_credits - reserved_credits`. Returns 404 for unknown user, 402 for quota exceeded. On pass, increments `reserved_credits` and commits (lock released). Generation runs outside any transaction.

**Settle TX (SELECT FOR UPDATE):** Re-fetches user with row lock, decrements `reserved_credits`, increments `used_credits` by actual credits, writes success UsageLog, commits.

**Error paths:**
- 402 quota_exceeded: log written in a separate TX after the reserve block exits (see deviation below)
- 503 ai_error: log written best-effort, then reservation released in finally
- 503 settle failure: same — reservation released in finally, logged at ERROR

**`app/main.py`:** Two-line change — `generate` added to router import, `app.include_router(generate.router)` added after users. `Base.metadata.create_all` in lifespan auto-creates `usage_log` table via `UsageLog` imported transitively through generate.py.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] quota_exceeded UsageLog separated from reserve TX**
- **Found during:** Task 1 implementation review
- **Issue:** Plan code called `db.add(UsageLog(... status="quota_exceeded"))` then `raise HTTPException(402)` inside `async with db.begin()`. Raising inside `async with db.begin()` triggers rollback — the UsageLog row would be lost, violating the must-have: "UsageLog row written for every request: success, quota_exceeded, ai_error".
- **Fix:** Set `quota_exceeded = True` flag inside the reserve TX (no log write there), then after the `async with db.begin()` block exits, write the quota_exceeded log in its own `async with db.begin()` block, then raise HTTPException(402).
- **Files modified:** app/routers/generate.py
- **Commit:** 242d14a

## Known Stubs

None — all paths fully wired.

## Threat Surface Scan

All threat-model items from the plan (T-02-03-01 through T-02-03-08) are addressed or accepted per plan. No new surface introduced beyond what the plan specified.

| Threat ID | Status |
|-----------|--------|
| T-02-03-01 | Mitigated: 404 for unknown user_id |
| T-02-03-02 | Mitigated: min_length=1 on prompt (Pydantic), cost checked pre-generation |
| T-02-03-03 | Mitigated: UsageLog written for all 3 terminal states |
| T-02-03-04 | Mitigated: generic "AI generation failed" detail; exc_info=True to logger only |
| T-02-03-05 | Accepted: by design, lock held only during reserve check |
| T-02-03-06 | Mitigated: int() cast + BigInteger column + Python arbitrary-precision int |
| T-02-03-07 | Accepted: demo scope |
| T-02-03-08 | Accepted: documented D-17 known limitation |

## Self-Check: PASSED

- [x] app/routers/generate.py exists: `242d14a` in git log
- [x] app/main.py modified: `55c924d` in git log
- [x] .with_for_update() appears 3 times (reserve, settle, release)
- [x] db.add(UsageLog(...)) appears 3 times (quota_exceeded, success, ai_error)
- [x] finally: if reserved and not settled: releases reservation
- [x] 402 for quota exceeded, 503 for AI failure, 404 for unknown user
