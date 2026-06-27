---
phase: 03-inspection-ship
plan: 02
subsystem: tests
tags: [pytest, pytest-asyncio, httpx, sqlalchemy, postgres, concurrency]

# Dependency graph
requires:
  - phase: 03-inspection-ship
    plan: 01
    provides: inspection endpoints, requirements.txt test deps
  - phase: 02-generate-quota
    provides: generate router with SELECT FOR UPDATE, UsageLog model, get_db, get_provider
provides:
  - tests/conftest.py: session-scoped test_engine creating metering_test tables once; function-scoped db and client fixtures
  - tests/test_generate.py: 9 async test scenarios covering quota enforcement, credits, concurrency, error handling, and inspection
  - pytest.ini: asyncio_mode=auto
affects: [03-ship]

# Tech tracking
tech-stack:
  added: []
  patterns: [session-scoped engine for real Postgres schema creation/teardown, function-scoped db via async_sessionmaker, app.dependency_overrides for both get_db and get_provider injection, asyncio.gather for concurrent test]

key-files:
  created: [tests/__init__.py, tests/conftest.py, tests/test_generate.py, pytest.ini]
  modified: []

key-decisions:
  - "Isolation via fresh user IDs per test (not rollback), because app handlers commit their own transactions"
  - "ErrorProvider override uses app.dependency_overrides[get_provider] with finally cleanup — same mechanism as get_db override, no new pattern needed"
  - "Concurrent test uses quota=50 so both requests fit; invariant is used_credits <= quota, not that both succeed"
  - "Divergence test iterates up to 20 requests to find estimated != actual given MockProvider ±10% random variance"

requirements-completed: [INFRA-02]

# Metrics
duration: 6min
completed: 2026-06-27
---

# Phase 03 Plan 02: Test Suite Summary

**9-scenario pytest suite against real Postgres metering_test DB — session-scoped schema setup, per-test user isolation, asyncio.gather concurrency test, provider dependency override for error path**

## Performance

- **Duration:** ~6 min
- **Completed:** 2026-06-27
- **Tasks:** 2
- **Files created:** 4

## Accomplishments

- tests/__init__.py: makes tests a package for import verification
- tests/conftest.py: session-scoped test_engine (creates metering_test tables once, drops after all tests); function-scoped db via async_sessionmaker; function-scoped AsyncClient with app.dependency_overrides[get_db] injection; pytest.ini asyncio_mode=auto
- tests/test_generate.py: all 9 async test functions with exact names from D-05
  - Scenario 1: successful generation + DB UsageLog row with status=success
  - Scenario 2: credit = total_tokens * multiplier verified in response and DB
  - Scenario 3: two users with multiplier=1 vs multiplier=5, credits_b > credits_a
  - Scenario 4: large quota, 200 response, used > 0 after
  - Scenario 5: quota=1, 402 + DB quota_exceeded row
  - Scenario 6: ErrorProvider via dependency_overrides[get_provider], 503, zero credit debit, ai_error log
  - Scenario 7: usage endpoint fields before/after generation, remaining = quota - used - reserved
  - Scenario 8: up to 20 iterations to find actual_credits != estimated_credits (MockProvider ±10% variance)
  - Scenario 9: asyncio.gather two concurrent requests, used_credits <= quota invariant

## Task Commits

1. **Task 1: conftest.py + pytest.ini** - `9633bf4` (feat)
2. **Task 2: test_generate.py with 9 scenarios** - `a87f607` (feat)

## Deviations from Plan

None - plan executed exactly as written. The plan code was used verbatim except: removed duplicate `from app.providers.base import BaseProvider, GenerationResult` import inside test_behavior_when_ai_generation_layer_fails (already imported at module level), and removed the unused `app_dependency_overrides_backup = None` variable. The `app` import was moved to module level (from `app.main import app`) instead of `_app` alias inside the test, which is cleaner and equivalent.

## Known Stubs

None. Test file does not render UI; no hardcoded empty values that affect test correctness.

## Threat Flags

None. Tests run against a local Docker Postgres with test-only credentials. No new network endpoints or auth paths introduced.

## Self-Check

Files created:
- tests/__init__.py: FOUND
- tests/conftest.py: FOUND
- tests/test_generate.py: FOUND
- pytest.ini: FOUND

Commits:
- 9633bf4: FOUND
- a87f607: FOUND

## Self-Check: PASSED
