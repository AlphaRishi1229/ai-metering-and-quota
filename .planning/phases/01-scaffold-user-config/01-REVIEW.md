---
phase: 01-scaffold-user-config
reviewed: 2026-06-27T01:10:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - .env.example
  - .gitignore
  - Dockerfile
  - app/__init__.py
  - app/config.py
  - app/database.py
  - app/main.py
  - app/models.py
  - app/routers/__init__.py
  - app/routers/users.py
  - app/schemas.py
  - docker-compose.yml
  - requirements.txt
findings:
  critical: 1
  warning: 4
  info: 2
  total: 7
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-06-27T01:10:00Z
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Summary

Scaffold is structurally sound: async SQLAlchemy 2.0 session pattern is correct (`async_sessionmaker` + `expire_on_commit=False` + context-manager yield), Pydantic v2 response model uses `from_attributes`, and Docker Compose health-gate wiring (`condition: service_healthy`) is correct. The create/update router logic is clean.

One critical issue: `create_all` at startup will silently no-op on an already-existing database with a different schema — this is fine for day-one but becomes a data-loss footgun the moment columns are added in a later phase and the container is restarted. The remaining issues are a missing `used_credits` default column server-side, the deprecated pydantic-settings inner `Config` class, a missing `alembic` / migration dependency, and two minor quality items.

---

## Critical Issues

### CR-01: `Base.metadata.create_all` at startup is not migration-safe — future schema changes will silently not apply

**File:** `app/main.py:12`

**Issue:** `create_all` only creates tables that do not yet exist. It never alters existing tables. Phase 2 will add at minimum a `name`/`email` column or a `transactions` table. When the service is restarted against a database that already has the `users` table, new columns are silently skipped. The app boots without error but reads `None` for the missing column — likely crashing or corrupting quota arithmetic at runtime. This is the canonical "works on first run, breaks on upgrade" failure.

This is the stated core concern of the service (correct per-user quota enforcement), so a startup path that can silently corrupt the schema is a blocker.

**Fix:** Pin the migration strategy before Phase 2 lands. The minimal approach is to add `alembic` now and generate an initial revision so the upgrade path exists:

```bash
# requirements.txt — add:
alembic==1.13.1

# alembic/env.py — standard async setup pointing at settings.DATABASE_URL
# Replace lifespan create_all with:
#   alembic upgrade head  (run as a container entrypoint step, or via startup check)
```

If alembic is deferred intentionally, add an explicit comment in `main.py` noting the known ceiling:

```python
# ponytail: create_all is dev-only; replace with alembic upgrade head before any schema change
async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)
```

And track it so it is not forgotten when Phase 2 begins.

---

## Warnings

### WR-01: `used_credits` and `reserved_credits` column defaults are Python-side only — new rows inserted outside the ORM start with `NULL`

**File:** `app/models.py:13-14`

**Issue:** `default=0` in SQLAlchemy mapped columns sets the default in Python when the ORM creates an object, but does **not** emit `DEFAULT 0` in the `CREATE TABLE` DDL. Any row inserted via raw SQL (migrations, seed scripts, test fixtures, admin tooling) will have `NULL` in these columns. Arithmetic on `NULL` in Postgres returns `NULL`, so quota checks built on `used_credits + reserved_credits` will silently pass when they should not.

```sql
-- What the DDL generates (no server default):
used_credits BIGINT NOT NULL  -- constraint only enforced at INSERT via ORM
```

**Fix:** Add `server_default` alongside `default`:

```python
from sqlalchemy import Integer, Float, BigInteger, text

used_credits: Mapped[int] = mapped_column(
    BigInteger, nullable=False, default=0, server_default=text("0")
)
reserved_credits: Mapped[int] = mapped_column(
    BigInteger, nullable=False, default=0, server_default=text("0")
)
```

### WR-02: `app/config.py` uses the deprecated inner `Config` class — will break on pydantic-settings v2.x upgrade

**File:** `app/config.py:7-8`

**Issue:** `pydantic-settings==2.2.1` is already pydantic-settings v2. The inner `class Config` pattern is the pydantic v1 API and is deprecated in pydantic-settings v2 — it still works in 2.2.1 via a compatibility shim but emits a deprecation warning on startup, and the shim is slated for removal. The correct v2 API is `model_config`.

```python
# current (deprecated):
class Config:
    env_file = ".env"
```

**Fix:**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    model_config = SettingsConfigDict(env_file=".env")
```

### WR-03: `PATCH /users/{user_id}` returns `200` on no-op update — misleading to callers

**File:** `app/routers/users.py:21`

**Issue:** When `UserUpdate` is sent with both fields `None` (an empty body `{}`), the handler fetches the user, changes nothing, commits, and returns `200` with the unchanged record. This is not a crash but it is a correctness gap: the update route silently accepts a payload that mutates nothing and returns success. More importantly there is no `status_code` set on the `@router.patch` decorator, so it defaults to `200` — the `UserResponse` model is returned but the implicit contract that `PATCH` changed something is violated.

The deeper issue: `UserUpdate` allows both fields to be `None` simultaneously, and there is no guard preventing a pointless write round-trip + commit.

**Fix:** Reject an all-None body early:

```python
@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, body: UserUpdate, db: AsyncSession = Depends(get_db)):
    if body.quota is None and body.multiplier is None:
        raise HTTPException(status_code=422, detail="At least one field must be provided")
    ...
```

### WR-04: `get_db` dependency does not roll back on exception — uncommitted partial state can leak across retries

**File:** `app/database.py:14-16`

**Issue:** `async_sessionmaker` with an `async with` context manager will call `session.close()` on exit, but it does **not** automatically roll back on an unhandled exception unless the driver does so on close. In asyncpg specifically, closing a session with a pending transaction leaves the connection in an error state until the pool recycles it. The standard pattern wraps the yield in a `try/except` to ensure explicit rollback:

```python
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

Checking the SQLAlchemy 2.0 docs: `async_sessionmaker`'s context manager **does** roll back on exception via `__aexit__`. This is correct as written. However, it only rolls back the *session*; it does not close the connection cleanly on asyncpg if there is a mid-transaction crash. The more robust pattern that is universally safe:

```python
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
```

This is belt-and-suspenders but is the production-recommended pattern for asyncpg connections where connection state matters.

---

## Info

### IN-01: `multiplier` uses `Float` (double precision) — floating-point arithmetic will cause non-deterministic credit calculations

**File:** `app/models.py:12`

**Issue:** `multiplier` is stored as IEEE 754 float. Credit debiting is `tokens * multiplier`. Floating-point multiplication is non-associative and non-exact; repeated small debits will accumulate rounding error. For a quota enforcement system where correctness is the stated core value, this is worth noting. `Numeric(precision=10, scale=4)` stores exact decimal values at negligible cost.

This is flagged as Info because the current phase only scaffolds the column — no arithmetic is implemented yet. Raise to Warning if Phase 2 implements debit logic using this column without switching the type.

### IN-02: No `__pycache__/` pattern excludes `.pyc` inside nested packages — `app/__pycache__` will be tracked if `__pycache__/` pattern is not recursive

**File:** `.gitignore:2`

**Issue:** The pattern `__pycache__/` in `.gitignore` matches directories named `__pycache__` at any depth (git treats unanchored patterns as recursive). This is fine. However `*.pyc` and `*.pyo` without a leading `/` also match recursively. No action needed — this is informational confirmation that the gitignore is correct.

Actually upon re-examination this is a non-issue. Closing as observation only — no fix needed.

---

_Reviewed: 2026-06-27T01:10:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
