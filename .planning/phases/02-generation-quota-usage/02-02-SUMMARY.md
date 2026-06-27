---
phase: 02-generation-quota-usage
plan: "02"
subsystem: database
tags: [sqlalchemy, pydantic, fastapi, postgres, orm]

requires:
  - phase: 02-generation-quota-usage
    provides: plan 01 established User ORM model and app structure

provides:
  - UsageLog ORM model (8 columns, FK to users, auto-created on startup)
  - GenerateRequest, UsageDetail, GenerateResponse Pydantic schemas

affects: [02-03-generate-router, 02-04-quota-logic, 03-usage-history]

tech-stack:
  added: []
  patterns:
    - "Nullable BIGINT columns for optional audit values (estimated_credits, actual_credits)"
    - "DateTime(timezone=True) with utcnow default for all timestamps"
    - "Nested Pydantic models (UsageDetail inside GenerateResponse)"

key-files:
  created: []
  modified:
    - app/models.py
    - app/schemas.py

key-decisions:
  - "estimated_credits and actual_credits are nullable BIGINT — NULL signals quota_exceeded or ai_error rows where no credits were consumed"
  - "UsageLog FK to users.id with default RESTRICT — audit rows must outlive user deletions"
  - "No remaining_credits in GenerateResponse — caller uses GET /users/{id}/usage (Phase 3)"
  - "GenerateRequest.prompt has min_length=1 only; no max_length — provider cost estimate bounds per-request cost before generation"

patterns-established:
  - "Append-only extension pattern: new ORM models appended after existing classes, imports extended not replaced"
  - "Pydantic nested model for structured response sub-objects (UsageDetail not flattened)"

requirements-completed: [GEN-01, USAGE-01, USAGE-02, USAGE-03]

duration: 8min
completed: 2026-06-27
---

# Phase 02 Plan 02: UsageLog ORM Model and Generate Schemas Summary

**UsageLog ORM table (8 columns, FK to users, nullable credits for error rows) and GenerateRequest/UsageDetail/GenerateResponse Pydantic contracts for the generate endpoint**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-06-27T00:00:00Z
- **Completed:** 2026-06-27
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- UsageLog ORM model appended to models.py — auto-created by lifespan `create_all` alongside users table
- Nullable BIGINT columns for estimated/actual credits correctly handle quota_exceeded and ai_error rows
- GenerateRequest with `min_length=1` validation, UsageDetail with 4 int fields, GenerateResponse with nested UsageDetail

## Task Commits

Each task was committed atomically:

1. **Task 1: Add UsageLog ORM model to models.py** - `9798be9` (feat)
2. **Task 2: Add generate schemas to schemas.py** - `f3d8482` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified
- `app/models.py` - Added UsageLog class with 8 columns (id, user_id FK, prompt_tokens, completion_tokens, estimated_credits, actual_credits, status, created_at)
- `app/schemas.py` - Added GenerateRequest, UsageDetail, GenerateResponse Pydantic models

## Decisions Made
- `estimated_credits` and `actual_credits` are nullable BIGINT: NULL for `quota_exceeded` / `ai_error` rows where no credits were consumed or calculated
- `created_at` uses `DateTime(timezone=True)` — tz-aware timestamps throughout the audit log
- FK `ondelete` left as default RESTRICT — audit rows must survive user lifecycle; no orphan rows allowed
- No `remaining_credits` in `GenerateResponse` — per D-03, callers use `GET /users/{id}/usage` (Phase 3)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

Verification command in plan (`python3 -c "from app.models import ..."`) could not run in the worktree environment — asyncpg not installed in available venvs, and module-level engine creation fires on import. Verified correctness via AST parse (both files parse cleanly) and grep checks confirming all required columns, class names, and FK patterns are present.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `app/models.py` exports `User` and `UsageLog` — ready for Plan 03 generate router to import both
- `app/schemas.py` exports `GenerateRequest`, `GenerateResponse`, `UsageDetail` — Plan 03 uses `response_model=GenerateResponse`
- No blockers; `create_all` on startup will create `usage_log` table alongside `users`

## Self-Check

Files:
- `app/models.py` — FOUND (contains class UsageLog, ForeignKey, estimated_credits, actual_credits, status, DateTime)
- `app/schemas.py` — FOUND (contains GenerateRequest, UsageDetail, GenerateResponse, usage: UsageDetail)

Commits:
- `9798be9` — FOUND (feat(02-02): add UsageLog ORM model)
- `f3d8482` — FOUND (feat(02-02): add GenerateRequest, UsageDetail, GenerateResponse schemas)

## Self-Check: PASSED

---
*Phase: 02-generation-quota-usage*
*Completed: 2026-06-27*
