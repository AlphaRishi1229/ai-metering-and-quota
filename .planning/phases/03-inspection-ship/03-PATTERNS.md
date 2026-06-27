# Phase 3: Inspection + Ship - Pattern Map

**Mapped:** 2026-06-27
**Files analyzed:** 7 new/modified files
**Analogs found:** 6 / 7 (DESIGN.md and README.md have no code analog)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `app/schemas.py` (extend) | model | transform | `app/schemas.py` itself | exact — add to existing file |
| `app/routers/inspection.py` | controller | request-response | `app/routers/users.py` | exact — same router style, same 404 pattern |
| `app/main.py` (extend) | config | request-response | `app/main.py` itself | exact — add one include_router line |
| `tests/conftest.py` | utility | CRUD | none (no tests exist yet) | no analog — use RESEARCH.md pattern |
| `tests/test_generate.py` | test | request-response | none (no tests exist yet) | no analog — use RESEARCH.md pattern |
| `DESIGN.md` | doc | — | none | doc, no code analog |
| `README.md` | doc | — | none | doc, no code analog |

---

## Pattern Assignments

### `app/schemas.py` — add `UsageResponse` and `UsageLogEntry`

**Analog:** `app/schemas.py` lines 14-37 (existing `UserResponse` and `GenerateResponse`)

**Existing schema pattern** (lines 14-37):
```python
class UserResponse(BaseModel):
    id: int
    quota: int
    multiplier: float
    used_credits: int
    reserved_credits: int

    model_config = {"from_attributes": True}


class UsageDetail(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    estimated_credits: int
    actual_credits: int
```

**What to copy:**
- `model_config = {"from_attributes": True}` is required on every ORM-backed response schema. `UsageResponse` is ORM-backed (from `User` model). `UsageLogEntry` is ORM-backed (from `UsageLog` model). Both need it.
- `int | None` typing for nullable columns — see `UserUpdate` lines 10-11 for the pattern. `UsageLogEntry.estimated_credits` and `actual_credits` are `BigInteger, nullable=True` in the model, so they must be `int | None` here.
- All imports already present at line 1: `from pydantic import BaseModel, Field`. No new imports needed.

**Fields to add — `UsageResponse`** (computed from `User` model, D-01/D-02):
```python
class UsageResponse(BaseModel):
    quota: int
    multiplier: float
    used: int          # maps to User.used_credits
    reserved: int      # maps to User.reserved_credits
    remaining: int     # computed: quota - used_credits - reserved_credits (server-side)

    model_config = {"from_attributes": True}
```
Note: `remaining` is NOT a column — it must be set in the endpoint before returning, not auto-mapped from ORM. Either use a `@computed_field` or construct the response manually in the router.

**Fields to add — `UsageLogEntry`** (from `UsageLog` model, D-03/D-04):
```python
class UsageLogEntry(BaseModel):
    id: int
    prompt_tokens: int
    completion_tokens: int
    estimated_credits: int | None
    actual_credits: int | None
    status: str
    created_at: datetime.datetime

    model_config = {"from_attributes": True}
```
Note: `datetime` import must be added at top of schemas.py — it is not currently imported there (it is only in `models.py`).

---

### `app/routers/inspection.py` — GET /users/{id}/usage and GET /users/{id}/usage/history

**Analog:** `app/routers/users.py` (entire file, 40 lines)

**Imports pattern** (lines 1-8 of users.py):
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserUpdate, UserResponse
```

**Router declaration pattern** (line 9):
```python
router = APIRouter(prefix="/users", tags=["users"])
```
Inspection router: `router = APIRouter(prefix="/users", tags=["inspection"])`

**404 pattern** (lines 27-30 of users.py) — copy verbatim:
```python
result = await db.execute(select(User).where(User.id == user_id))
user = result.scalar_one_or_none()
if user is None:
    raise HTTPException(status_code=404, detail=f"User {user_id} not found")
```

**History query additional pattern** — extend the base select with ordering and pagination (from D-04):
```python
from sqlalchemy import select, desc
from app.models import User, UsageLog
from fastapi import Query

# in the handler:
result = await db.execute(
    select(UsageLog)
    .where(UsageLog.user_id == user_id)
    .order_by(desc(UsageLog.created_at))
    .limit(limit)
    .offset(offset)
)
rows = result.scalars().all()
```

**Query param pattern** (D-04):
```python
async def get_usage_history(
    user_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
```

**`remaining` computation** — inline before return, not stored:
```python
remaining = user.quota - user.used_credits - user.reserved_credits
```
Then either construct `UsageResponse` manually with `remaining=remaining`, or set it as an attribute before returning.

---

### `app/main.py` — include inspection router

**Analog:** `app/main.py` lines 6-18 (existing router include pattern)

**Existing pattern** (lines 6, 17-18):
```python
from app.routers import users, generate

app.include_router(users.router)
app.include_router(generate.router)
```

**What to add** — one import line and one include line:
```python
from app.routers import users, generate, inspection   # add inspection

app.include_router(users.router)
app.include_router(generate.router)
app.include_router(inspection.router)                 # add this
```

---

### `tests/conftest.py` — test DB fixture (no analog exists)

No existing test files in the codebase. Pattern comes from D-06 and the established `get_db` override point in `app/database.py`.

**Key anchor from `app/database.py`** (lines 1-16):
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

**conftest.py structure to implement** (D-06 pattern):
```python
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.database import get_db, Base

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/metering_test"

# Session-scoped: create tables once, drop after all tests
@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

# Function-scoped: fresh session + override per test
@pytest_asyncio.fixture
async def db(test_engine):
    AsyncTestSession = async_sessionmaker(test_engine, expire_on_commit=False)
    async with AsyncTestSession() as session:
        yield session

@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
```

Note: `pytest-asyncio`, `httpx`, and `anyio` must be added to `requirements.txt` (not currently present).

---

### `tests/test_generate.py` — 9 test scenarios (no analog exists)

No existing tests. Pattern is `pytest-asyncio` + `httpx.AsyncClient` via conftest fixtures.

**Test file structure** (scenario names from D-05 verbatim):
```python
import asyncio
import pytest

# Each test receives `client` fixture (AsyncClient with test DB injection)
# and `db` fixture for direct DB assertions

pytestmark = pytest.mark.anyio

async def test_successful_generation_and_usage_recording(client, db): ...
async def test_credit_calculation_using_per_user_multiplier(client, db): ...
async def test_different_users_receive_different_quota_or_multiplier_behavior(client, db): ...
async def test_quota_enforcement_when_user_has_enough_remaining_credits(client, db): ...
async def test_quota_exceeded_behavior_when_user_does_not_have_enough_remaining_credits(client, db): ...
async def test_behavior_when_ai_generation_layer_fails(client, db): ...
async def test_retrieval_of_current_usage_and_remaining_allowance(client, db): ...
async def test_behavior_when_actual_usage_differs_from_estimate(client, db): ...
async def test_behavior_for_near_simultaneous_requests_from_same_user(client, db): ...
```

**Scenario 9 concurrent pattern** (D-07 — `asyncio.gather`):
```python
results = await asyncio.gather(
    client.post(f"/users/{user_id}/generate", json={"prompt": "hello"}),
    client.post(f"/users/{user_id}/generate", json={"prompt": "hello"}),
    return_exceptions=True,
)
# Assert combined used <= quota; one may 402, neither should overrun
```

**Provider override for AI-error scenario** (scenario 6):
The `get_provider` dependency from `app/providers/claude.py` can be overridden the same way `get_db` is — `app.dependency_overrides[get_provider] = lambda: ErrorProvider()` where `ErrorProvider.generate()` raises an exception.

**DB assertion pattern** (for checking UsageLog rows):
```python
from sqlalchemy import select
from app.models import UsageLog, User

result = await db.execute(select(UsageLog).where(UsageLog.user_id == user_id))
logs = result.scalars().all()
assert logs[-1].status == "success"
```

---

## Shared Patterns

### 404 Lookup
**Source:** `app/routers/users.py` lines 27-30
**Apply to:** Both inspection endpoints
```python
result = await db.execute(select(User).where(User.id == user_id))
user = result.scalar_one_or_none()
if user is None:
    raise HTTPException(status_code=404, detail=f"User {user_id} not found")
```

### ORM-Backed Schema
**Source:** `app/schemas.py` line 21
**Apply to:** `UsageResponse`, `UsageLogEntry`
```python
model_config = {"from_attributes": True}
```

### Dependency Injection (DB session)
**Source:** `app/database.py` lines 14-16
**Apply to:** All new endpoint handlers, all test fixtures
```python
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```
Override point in tests: `app.dependency_overrides[get_db] = override_get_db`

### Router Prefix Convention
**Source:** `app/routers/users.py` line 9, `app/routers/generate.py` line 15
**Apply to:** `app/routers/inspection.py`
Both existing routers use `prefix="/users"`. Inspection endpoints are also under `/users/{user_id}/...` so the same prefix applies. Tags differ per router.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `tests/conftest.py` | utility | CRUD | No test infrastructure exists yet |
| `tests/test_generate.py` | test | request-response | No test files exist in the project |
| `DESIGN.md` | doc | — | Documentation, no code analog |
| `README.md` | doc | — | Documentation, no code analog |

For these, use D-06 and D-07 patterns from CONTEXT.md plus standard `pytest-asyncio` + `httpx` conventions.

---

## Dependency Gap

`requirements.txt` currently contains: `fastapi`, `uvicorn`, `sqlalchemy`, `asyncpg`, `pydantic-settings`, `anthropic`.

Tests need additions:
- `pytest`
- `pytest-asyncio`
- `httpx`
- `anyio[asyncio]`

These must be added (likely in a `requirements-dev.txt` or appended to `requirements.txt`) before conftest.py will work.

---

## Metadata

**Analog search scope:** `app/routers/`, `app/schemas.py`, `app/models.py`, `app/database.py`, `app/providers/`
**Files scanned:** 10 Python source files
**Pattern extraction date:** 2026-06-27
