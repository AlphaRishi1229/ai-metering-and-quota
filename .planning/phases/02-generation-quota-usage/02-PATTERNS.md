# Phase 2: Generation + Quota + Usage - Pattern Map

**Mapped:** 2026-06-27
**Files analyzed:** 8 (5 new, 3 modified)
**Analogs found:** 8 / 8

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/providers/__init__.py` | package init | — | `app/routers/__init__.py` (empty) | exact |
| `app/providers/base.py` | abstract base | transform | `app/models.py` (class shape) | partial |
| `app/providers/mock.py` | service | transform | `app/models.py` (class shape) | partial |
| `app/providers/claude.py` | service | request-response | `app/models.py` (class shape) | partial |
| `app/routers/generate.py` | controller | request-response | `app/routers/users.py` | exact |
| `app/models.py` (modify) | model | CRUD | `app/models.py:User` | exact |
| `app/config.py` (modify) | config | — | `app/config.py:Settings` | exact |
| `app/main.py` (modify) | entrypoint | — | `app/main.py` | exact |

---

## Pattern Assignments

### `app/providers/__init__.py` (package init)

**Analog:** `app/routers/__init__.py`

Empty file. No imports needed — consumers import directly from submodules.

```python
# empty
```

---

### `app/providers/base.py` (abstract base, transform)

**Analog:** `app/models.py` (class definition shape) + Python stdlib `abc`

**Imports pattern:**
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
```

**Core pattern** — `GenerationResult` dataclass (D-05) + ABC with two abstract methods (D-04):
```python
@dataclass
class GenerationResult:
    text: str
    prompt_tokens: int
    completion_tokens: int


class BaseProvider(ABC):
    @abstractmethod
    def estimate_tokens(self, prompt: str) -> int: ...

    @abstractmethod
    async def generate(self, prompt: str) -> GenerationResult: ...
```

Note: `estimate_tokens` is sync (cheap local math or a sync SDK call); `generate` is async (network I/O). ABC enforces the contract for both concrete providers.

---

### `app/providers/mock.py` (service, transform)

**Analog:** `app/providers/base.py` (implements BaseProvider)

**Imports pattern:**
```python
import random
from app.providers.base import BaseProvider, GenerationResult
```

**Core pattern** (D-08, D-09):
```python
class MockProvider(BaseProvider):
    def estimate_tokens(self, prompt: str) -> int:
        return max(1, len(prompt) // 4)

    async def generate(self, prompt: str) -> GenerationResult:
        prompt_tokens = max(1, len(prompt) // 4)
        completion_tokens = max(10, int(prompt_tokens * random.uniform(0.9, 1.1)))
        return GenerationResult(
            text=f"Mock response for: {prompt[:50]}",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
```

---

### `app/providers/claude.py` (service, request-response)

**Analog:** `app/providers/base.py` (implements BaseProvider)

**Imports pattern:**
```python
import anthropic
from app.providers.base import BaseProvider, GenerationResult
from app.config import settings
```

**Core pattern** (D-10, D-11, D-12):
```python
class ClaudeProvider(BaseProvider):
    def __init__(self):
        self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def estimate_tokens(self, prompt: str) -> int:
        response = self._client.messages.count_tokens(
            model="claude-haiku-4-5-20251001",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.input_tokens

    async def generate(self, prompt: str) -> GenerationResult:
        response = self._client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return GenerationResult(
            text=response.content[0].text,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
        )
```

Note: `anthropic.Anthropic` is the sync client. `count_tokens` and `messages.create` are both sync SDK calls — wrapping in `asyncio.to_thread` is discretionary; for a demo with low concurrency this is acceptable. Flag with `# ponytail: sync client, switch to AsyncAnthropic if throughput matters`.

---

### `app/routers/generate.py` (controller, request-response)

**Analog:** `app/routers/users.py` (lines 1-39) — exact role + data flow match

**Imports pattern** (mirrors `users.py` lines 1-8, extended):
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, UsageLog
from app.schemas import GenerateRequest, GenerateResponse
from app.providers.base import BaseProvider
```

**Router declaration** (mirrors `users.py` line 9):
```python
router = APIRouter(prefix="/users", tags=["generate"])
```

**User lookup pattern** (copy from `users.py` lines 27-30):
```python
result = await db.execute(select(User).where(User.id == user_id).with_for_update())
user = result.scalar_one_or_none()
if user is None:
    raise HTTPException(status_code=404, detail=f"User {user_id} not found")
```

Note: add `.with_for_update()` to the SELECT — this is the Phase 2 addition over the plain SELECT in `users.py`.

**Core quota enforcement pattern** (D-13, D-16):
```python
@router.post("/{user_id}/generate", response_model=GenerateResponse, status_code=200)
async def generate(
    user_id: int,
    body: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    provider: BaseProvider = Depends(get_provider),
):
    estimated_tokens = provider.estimate_tokens(body.prompt)
    estimated_credits = int(estimated_tokens * user.multiplier)  # set after user lookup

    # --- reserve ---
    # (inside first SELECT FOR UPDATE tx — see quota flow below)

    reserved = False
    settled = False
    try:
        # reserve block
        reserved = True
        result = await provider.generate(body.prompt)
        # settle block
        settled = True
    except Exception:
        raise HTTPException(status_code=503, detail="AI generation failed")
    finally:
        if reserved and not settled:
            # release reservation tx
            pass
```

**Error handling pattern** (mirrors `users.py` lines 29-31 for 404; adds 402, 503):
```python
raise HTTPException(status_code=404, detail=f"User {user_id} not found")
raise HTTPException(status_code=402, detail="Quota exceeded")
raise HTTPException(status_code=402, detail="User has no quota configured")
raise HTTPException(status_code=503, detail="AI generation failed")
```

**UsageLog write pattern** (mirrors `users.py` lines 14-18 for db.add/commit):
```python
log = UsageLog(
    user_id=user_id,
    prompt_tokens=result.prompt_tokens,
    completion_tokens=result.completion_tokens,
    estimated_credits=estimated_credits,
    actual_credits=actual_credits,
    status="success",
)
db.add(log)
await db.commit()
```

---

### `app/models.py` — add `UsageLog` (model, CRUD)

**Analog:** `app/models.py:User` (lines 1-14) — exact same file, same ORM pattern

**Imports** — no new imports needed; `BigInteger`, `Integer`, `Mapped`, `mapped_column`, `Base` already present. Add `String`, `DateTime`, `ForeignKey` from `sqlalchemy`:

```python
from sqlalchemy import Integer, Float, BigInteger, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
import datetime
```

**UsageLog model** (D-19, D-20, D-21) — follows `User` column declaration style exactly:
```python
class UsageLog(Base):
    __tablename__ = "usage_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_credits: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actual_credits: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.datetime.utcnow
    )
```

---

### `app/config.py` — add two fields (config)

**Analog:** `app/config.py:Settings` (lines 1-11) — same file

**Current shape** (lines 4-8):
```python
class Settings(BaseSettings):
    DATABASE_URL: str

    class Config:
        env_file = ".env"
```

**Add** (D-12) — insert after `DATABASE_URL`:
```python
    USE_REAL_LLM: bool = False
    ANTHROPIC_API_KEY: str = ""
```

`pydantic-settings` reads these from env / `.env` automatically — no other change needed.

---

### `app/main.py` — include generate router (entrypoint)

**Analog:** `app/main.py` (lines 1-17) — same file

**Current shape** (lines 6-7, 17):
```python
from app.routers import users
# ...
app.include_router(users.router)
```

**Add** (mirrors exact pattern):
```python
from app.routers import users, generate
# ...
app.include_router(users.router)
app.include_router(generate.router)
```

`Base.metadata.create_all` in lifespan auto-creates `usage_log` table once `UsageLog` is imported anywhere in the import chain (via `app/routers/generate.py` → `app/models.py`).

---

## Shared Patterns

### SELECT FOR UPDATE (quota enforcement)
**Source:** `app/routers/users.py` lines 27-28 (base SELECT) + SQLAlchemy `.with_for_update()`
**Apply to:** `app/routers/generate.py` — both reserve and settle transactions
```python
result = await db.execute(select(User).where(User.id == user_id).with_for_update())
user = result.scalar_one_or_none()
```

### DB write pattern
**Source:** `app/routers/users.py` lines 14-18
**Apply to:** `app/routers/generate.py` (UsageLog write), settlement step
```python
db.add(obj)
await db.commit()
await db.refresh(obj)   # omit for UsageLog — response doesn't echo it back
```

### 404 guard
**Source:** `app/routers/users.py` lines 29-30
**Apply to:** `app/routers/generate.py` user lookup
```python
if user is None:
    raise HTTPException(status_code=404, detail=f"User {user_id} not found")
```

### Pydantic schema shape
**Source:** `app/schemas.py` lines 14-21 (UserResponse with `model_config`)
**Apply to:** `GenerateRequest`, `GenerateResponse`, `UsageDetail` in `app/schemas.py`
```python
class GenerateResponse(BaseModel):
    text: str
    usage: UsageDetail
    model_config = {"from_attributes": True}   # only if reading from ORM; skip if pure dict
```

### get_provider() dependency
**Source:** `app/database.py` lines 14-16 (`get_db` pattern)
**Apply to:** `app/routers/generate.py` + a new `app/providers/__init__.py` or inline in `generate.py`
```python
# mirrors get_db() — no yield needed since provider is stateless per-request
def get_provider() -> BaseProvider:
    if settings.USE_REAL_LLM:
        return ClaudeProvider()
    return MockProvider()
```

---

## No Analog Found

All files have analogs from the existing codebase. No external pattern references needed.

---

## Metadata

**Analog search scope:** `app/` directory (models, database, routers, config, schemas, main)
**Files scanned:** 7
**Pattern extraction date:** 2026-06-27
