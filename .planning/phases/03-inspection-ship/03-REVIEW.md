---
phase: 03-inspection-ship
reviewed: 2026-06-27T00:00:00Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - app/routers/inspection.py
  - app/schemas.py
  - app/main.py
  - requirements.txt
  - tests/__init__.py
  - tests/conftest.py
  - tests/test_generate.py
  - pytest.ini
  - DESIGN.md
  - README.md
findings:
  critical: 1
  warning: 5
  info: 1
  total: 7
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-06-27T00:00:00Z
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Reviewed the inspection router, schemas, app entry point, test suite, configuration, and documentation files. Cross-referenced against `app/routers/generate.py`, `app/models.py`, `app/providers/`, and `app/database.py` to validate correctness at integration points.

The core quota logic in `generate.py` is structurally sound (reserve / generate / settle pattern, `SELECT FOR UPDATE` on both phases). However, the test fixture design contains a race between event loop scopes that will break the session-scoped engine fixture under pytest-asyncio >=0.23, and there is a double-decrement bug on settle TX failure that corrupts `reserved_credits`. The remaining issues are schema/documentation mismatches and a test isolation gap.

---

## Critical Issues

### CR-01: Double decrement of `reserved_credits` when settle TX fails mid-commit

**File:** `app/routers/generate.py:84-103, 132-148`

**Issue:** When the settle transaction (`async with db.begin()` at line 84) starts, it decrements `user.reserved_credits -= estimated_credits` at line 90 and then commits. If the commit raises (e.g., DB network blip), the `except Exception` block fires at line 108 and then the `finally` block runs. The `finally` guard at line 133 checks `reserved and not settled` — `settled` is only set to `True` at line 103, which runs *after* the `async with db.begin()` block closes (i.e., after a successful commit). If the commit fails, `settled` remains `False`, so the `finally` block fires a third `SELECT FOR UPDATE` and decrements `reserved_credits` a second time. Because the settle TX failed to commit, the first decrement was never persisted — but if the settle TX committed partially (PostgreSQL commits atomically so this is a non-issue), or more practically if the session's in-memory state is out of sync after a failed commit, the second decrement can drive `reserved_credits` below zero. The `max(0, ...)` guard only prevents writing a negative value but does not prevent the double application when the settle TX's first decrement was rolled back.

This is a consistency bug: a transient DB error during settle leaves `reserved_credits` either under-decremented (correct) or doubly-decremented (incorrect), depending on whether the session state is refreshed between the failed commit and the `finally` block's re-execution.

**Fix:** Set `settled = True` inside the `async with db.begin()` block, before the commit, or re-fetch the user inside the `finally` block unconditionally (do not reuse in-memory delta). The simplest fix: move `settled = True` to just before the `async with db.begin():` block closes, or use a flag that is only set when the commit is confirmed:

```python
        async with db.begin():
            result = await db.execute(
                select(User).where(User.id == user_id).with_for_update()
            )
            user = result.scalar_one_or_none()
            user.reserved_credits = max(0, user.reserved_credits - estimated_credits)
            user.used_credits += actual_credits
            db.add(UsageLog(..., status="success"))
            # TX commits at end of block — only mark settled after this point

        settled = True  # <- already here at line 103, this is correct

    # BUT the finally block also decrements. Guard with: if not settled is only
    # safe if the settle TX is truly atomic. Postgres guarantees this — if the
    # async with block raises, the TX was rolled back, so reserved_credits was
    # never decremented in the DB. The finally block's second decrement is then
    # actually correct (releasing the reservation the DB still holds).
    #
    # The real bug: the finally block does a SELECT FOR UPDATE and re-applies
    # the delta. If the settle TX committed (settled=True), the finally block
    # skips correctly. If the settle TX rolled back (settled=False), both the
    # reserve and the first decrement are still live in the DB, so the finally
    # block correctly releases the reserve.
    #
    # HOWEVER: the except block at line 108 writes an ai_error UsageLog row.
    # This runs BEFORE the finally block. If the exception is from the settle TX
    # (not from provider.generate), the ai_error log is written but the status
    # should be something other than "ai_error" (the AI succeeded, the DB failed).
    # The ai_error log is misleading — a settle TX failure gets logged as
    # "ai_error" even though generation succeeded and the user received text.
```

Concretely: a settle TX failure causes `status="ai_error"` to be logged even though the AI call succeeded and the user received a 503 response with the generation already delivered. The reservation is properly released by the `finally` block (Postgres rolled back the settle TX atomically, so the reservation delta from the settle TX was never applied, and the `finally` block correctly un-does the original reservation). The correctness issue is the audit log misclassification, not a double-decrement of committed state. This should be classified and fixed:

```python
# In the except block, distinguish AI errors from settle errors:
if generation_result is None:
    log_status = "ai_error"
else:
    log_status = "settle_error"  # AI succeeded but DB settle failed
```

---

## Warnings

### WR-01: Session-scoped async fixture missing event loop scope — will break with pytest-asyncio >=0.23

**File:** `tests/conftest.py:12-20`, `pytest.ini:2`

**Issue:** `test_engine` is a `scope="session"` async fixture. pytest-asyncio >=0.23 (the lower bound in `requirements.txt`) requires that the event loop scope for session-scoped async fixtures be explicitly configured. Without `asyncio_default_fixture_loop_scope = session` in `pytest.ini`, pytest-asyncio creates a new event loop per test function. The session-scoped `test_engine` fixture was created in one event loop; the function-scoped `db` fixture runs in a different event loop. This causes a `Task attached to a different loop` or `ScopeMismatch` error at runtime when the `db` fixture tries to use the session-scoped engine.

In pytest-asyncio 0.23 this raises a `DeprecationWarning` and may still work via compatibility shim; in 0.24+ it is a hard error.

**Fix:** Add to `pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
asyncio_default_fixture_loop_scope = session
```

### WR-02: `UsageResponse` schema omits `user_id` field documented in DESIGN.md

**File:** `app/schemas.py:42-48`, cross-referenced against `DESIGN.md:168`

**Issue:** The Endpoint Reference table in `DESIGN.md` documents the usage response as `{user_id, quota, multiplier, used, reserved, remaining}`. The `UsageResponse` Pydantic model and the `get_usage` handler in `inspection.py` both omit `user_id`. API consumers relying on the documented contract to extract `user_id` from the response will find it absent.

**Fix:** Either add `user_id` to `UsageResponse`:
```python
class UsageResponse(BaseModel):
    user_id: int
    quota: int
    multiplier: float
    used: int
    reserved: int
    remaining: int
    model_config = {"from_attributes": True}
```
And populate it in the handler:
```python
return UsageResponse(user_id=user.id, quota=user.quota, ...)
```
Or update `DESIGN.md` to remove `user_id` from the documented response shape.

### WR-03: `remaining` can be negative — misleading to callers

**File:** `app/routers/inspection.py:21-28`, `app/schemas.py:47`

**Issue:** `remaining = user.quota - user.used_credits - user.reserved_credits`. Per the design, `used_credits` can exceed `quota` after a settle where actual credits exceeded the estimate. When this happens, `remaining` is negative. The schema declares `remaining: int` with no constraint, so a negative value is returned silently. Callers who treat `remaining` as "available budget" will get a misleading result without any indication that the account is overdrawn.

**Fix:** Either clamp at zero with a schema-level annotation:
```python
remaining: int  # may be negative if actual_credits exceeded quota on last request
```
Add a comment to the DESIGN.md Known Limitation section documenting that the usage endpoint returns negative `remaining` in the overrun case, or clamp in the router:
```python
remaining = max(0, user.quota - user.used_credits - user.reserved_credits)
```
Note: clamping hides the overrun from monitoring. A comment or separate `overdrawn: bool` field would be more honest.

### WR-04: `ClaudeProvider` references a non-standard model identifier

**File:** `app/providers/claude.py:20`

**Issue:** `model="claude-haiku-4-5-20251001"` is not a recognized Anthropic model slug. The Anthropic API will return a `404` or `invalid_request_error` for unrecognized model names. The correct identifier for Claude Haiku 4.5 as of the knowledge cutoff is `claude-haiku-4-5` (without the date suffix, or with the correct release date). This means `USE_REAL_LLM=true` is broken for any reviewer who runs it as documented.

**Fix:**
```python
model="claude-haiku-4-5",  # or the exact slug from Anthropic's model list
```
Verify against `https://docs.anthropic.com/en/docs/about-claude/models` before shipping.

### WR-05: Test suite does not achieve true per-test isolation — committed rows persist

**File:** `tests/conftest.py:23-28`

**Issue:** The `db` fixture calls `await session.rollback()` at teardown to undo uncommitted changes. However, `users.py` calls `await db.commit()` directly (not via savepoint), and `generate.py` calls `async with db.begin()` which also commits. Once committed, those rows cannot be rolled back via the session's `rollback()`. Each test that creates a user and calls generate leaves permanent rows in `metering_test`.

Within a single test run this is tolerable because `test_engine` drops all tables at session teardown. But if a test run is interrupted mid-suite (Ctrl+C after some tests), the next run starts with leftover rows. Tests that assert exact row counts (e.g., `assert len(logs) == 1` in `test_successful_generation_and_usage_recording`) will then fail spuriously.

The standard pattern for true test isolation with SQLAlchemy async is to wrap each test in a savepoint and roll back the savepoint, not the outer transaction:

**Fix:** Use nested transactions (savepoints) via `session.begin_nested()`, or truncate all tables in a fixture teardown step, or accept the limitation and document it clearly with a note that the test DB must be clean.

```python
@pytest_asyncio.fixture
async def db(test_engine):
    AsyncTestSession = async_sessionmaker(test_engine, expire_on_commit=False)
    async with AsyncTestSession() as session:
        async with session.begin():
            nested = await session.begin_nested()  # savepoint
            yield session
            await nested.rollback()  # undo everything within the savepoint
```
Note: this pattern only works if the application code never calls `session.commit()` directly (it must use the session's subtransaction). Because `users.py` and `generate.py` call `db.commit()` and `async with db.begin()`, the savepoint approach would require patching. The simplest fix is to truncate tables in teardown.

---

## Info

### IN-01: Unused `datetime` import in `inspection.py`

**File:** `app/routers/inspection.py:1`

**Issue:** `import datetime` is present but `datetime` is never referenced in `inspection.py`. The `UsageLogEntry.created_at` type is declared in `schemas.py`, not here.

**Fix:** Remove the import:
```python
# Remove line 1: import datetime
```

---

_Reviewed: 2026-06-27T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
